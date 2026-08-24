"""Access OpenAI APIs using application configuration."""

from __future__ import annotations

from openai import OpenAI

from ntk.models.settings import SETTINGS

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIService:
    """Provide application-level access to the OpenAI API."""

    def __init__(
        self,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        client: OpenAI | None = None,
    ) -> None:
        """Initialize an OpenAI client from an injected or environment API key."""
        self.embedding_model = embedding_model
        self.client = client or OpenAI(api_key=SETTINGS.open_ai_api_key)

    def get_embedding(self, content: str) -> list[float]:
        """Create an embedding vector for one content string."""
        response = self.client.embeddings.create(
            input=content,
            model=self.embedding_model,
        )
        if not response.data:
            msg = "OpenAI returned no embedding vector"
            raise RuntimeError(msg)
        return response.data[0].embedding
