"""RAG document ingestion endpoints."""

from __future__ import annotations

import pathlib
import typing
from importlib import import_module
from tempfile import TemporaryDirectory

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import ValidationError

from ntk.controllers.rag.ingest import (
    IngestController,
    IngestOptions,
    IngestResponse,
)
from ntk.models.document import StoredDocumentType
from ntk.models.rag import RagSearchMatch
from ntk.models.settings import SETTINGS
from ntk.presentation.api.middleware import rate_limit
from ntk.services.open_ai_service import OpenAIService

if typing.TYPE_CHECKING:
    from psycopg import Connection

router = APIRouter()
_OPEN_AI_SERVICE = OpenAIService()
_SEARCH_SQL = """
    SELECT d.id, d.filename, c.content,
           1 - (e.embedding_vector <=> %s::vector) AS similarity
    FROM document_embeddings e
    JOIN document_chunks c ON c.id = e.document_chunk_id
    JOIN document d ON d.id = c.document_id
    WHERE d.document_type = %s
    ORDER BY e.embedding_vector <=> %s::vector
    LIMIT %s
"""


def _database_dsn() -> str:
    """Convert the SQLAlchemy database URL into a psycopg2 DSN."""
    return str(SETTINGS.database_url).replace(
        "postgresql+psycopg://",
        "postgresql://",
        1,
    )


def _connect() -> Connection[tuple[object, ...]]:
    """Open a psycopg2 connection for a vector search."""
    connect = import_module("psycopg2").connect
    return connect(_database_dsn())


@router.get(
    "/rag/search",
    response_model=list[RagSearchMatch],
    dependencies=[Depends(rate_limit(limit=50, window=3600))],
)
def search_documents(
    text: typing.Annotated[str, Query(description="Text to search for")],
    top_k: typing.Annotated[
        int,
        Query(description="Number of closest chunks to return (clamped to 1-20)"),
    ] = 5,
) -> list[RagSearchMatch]:
    """Return document chunks closest to the embedded query text."""
    query = text.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search text must not be empty",
        )
    limit = max(1, min(top_k, 20))
    embedding = _OPEN_AI_SERVICE.create_embedding(query)
    vector = "[" + ",".join(str(value) for value in embedding) + "]"
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            _SEARCH_SQL,
            (
                vector,
                StoredDocumentType.NUTRITION_CARE_MANUAL.value,
                vector,
                limit,
            ),
        )
        rows = cursor.fetchall()
    return [
        RagSearchMatch(
            document_id=row[0],
            filename=row[1],
            chunk_text=row[2],
            similarity=float(row[3]),
        )
        for row in rows
    ]


@router.post(
    "/rag/ingest",
    response_model=IngestResponse,
    dependencies=[Depends(rate_limit(100, window=3600))],
)
async def ingest_pdfs(
    files: typing.Annotated[
        list[UploadFile],
        File(description="One or more PDF or text files"),
    ],
    document_type: typing.Annotated[
        StoredDocumentType,
        Form(description="Document category"),
    ],
    *,
    overwrite: typing.Annotated[
        bool,
        Form(description="Replace and re-embed an existing document"),
    ] = False,
) -> IngestResponse:
    """Ingest one or more uploaded PDF or text files."""
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one PDF or text file is required",
        )
    with TemporaryDirectory(prefix="ntk-rag-") as directory:
        folder = pathlib.Path(directory)
        for index, upload in enumerate(files):
            filename = upload.filename or f"upload-{index}.pdf"
            if pathlib.Path(filename).suffix.lower() not in {".pdf", ".txt"}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"'{filename}' is not a PDF or text file",
                )
            (folder / f"{filename}").write_bytes(await upload.read())
        try:
            options = IngestOptions(
                path=folder,
                document_type=document_type,
                overwrite=overwrite,
            )
        except ValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err.errors(),
            ) from err
        output = IngestController().run(options)
        for document, upload in zip(output.result.documents, files, strict=True):
            document.filename = upload.filename or document.filename
        return output.result
