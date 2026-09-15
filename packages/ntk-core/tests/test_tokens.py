from __future__ import annotations

import pytest

from ntk.utils.tokens import truncate_to_tokens

ESTIMATED_BYTES_PER_TOKEN = 3


def test_truncate_to_tokens_preserves_short_text() -> None:
    assert truncate_to_tokens("short text", 10) == "short text"


def test_truncate_to_tokens_obeys_limit_and_marks_truncation() -> None:
    max_tokens = 10
    result = truncate_to_tokens("nutrition " * 100, max_tokens)

    assert result.endswith("[truncated]")
    assert len(result.encode()) <= max_tokens * ESTIMATED_BYTES_PER_TOKEN


def test_truncate_to_tokens_rejects_nonpositive_limit() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        truncate_to_tokens("nutrition", 0)
