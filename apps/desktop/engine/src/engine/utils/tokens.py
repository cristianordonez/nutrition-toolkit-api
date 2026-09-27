from __future__ import annotations

import tiktoken

_ESTIMATED_BYTES_PER_TOKEN = 3
_TRUNCATION_MARKER = "\n[truncated]"


def count_tokens(text: str) -> int:
    """Return the same conservative, network-free estimate used for truncation."""
    byte_count = len(text.encode())
    return (byte_count + _ESTIMATED_BYTES_PER_TOKEN - 1) // (_ESTIMATED_BYTES_PER_TOKEN)


def truncate_to_tokens(
    text: str,
    max_tokens: int,
) -> str:
    """Bound text using a conservative, network-free token estimate."""
    if max_tokens <= 0:
        msg = "Maximum tokens must be greater than 0"
        raise ValueError(msg)
    max_bytes = max_tokens * _ESTIMATED_BYTES_PER_TOKEN
    encoded = text.encode()
    if len(encoded) <= max_bytes:
        return text
    marker = _TRUNCATION_MARKER.encode()
    content_limit = max(0, max_bytes - len(marker))
    content = encoded[:content_limit].decode(errors="ignore")
    return content + _TRUNCATION_MARKER


def sliding_window(
    text: str,
    chunk_size: int = 600,
    overlap: int = 100,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """Create overlapping chunks of text based on token size.

    :param text: text to chunk
    :param chunk_size: chunk size
    :param overlap: overlapping number of tokens
    :param encoding_name: token encoding name, defaults to "cl100k_base"
    :raises ValueError: overlap is too large
    :return: chunked list
    """
    if chunk_size <= 0:
        msg = "Chunk size must be greater than 0"
        raise ValueError(msg)
    if overlap < 0:
        msg = "Overlap cannot be negative"
        raise ValueError(msg)
    if overlap >= chunk_size:
        msg = "Overlap must be smaller than chunk size."
        raise ValueError(msg)
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk = tokens[start:end]
        chunk_text = encoding.decode(chunk)
        chunks.append(chunk_text)
        if end == len(tokens):
            break
        start = end - overlap
    return chunks
