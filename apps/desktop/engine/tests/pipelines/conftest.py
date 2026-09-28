"""Lightweight local tokenizer for ingestion tests, without downloading assets."""

from __future__ import annotations

import pytest
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import WhitespaceSplit
from tokenizers.processors import TemplateProcessing

from engine.pipelines.knowledge.ingestion.processing import chunker


@pytest.fixture
def embedding_tokenizer(monkeypatch: pytest.MonkeyPatch) -> Tokenizer:
    tokenizer = Tokenizer(
        WordLevel(
            {"[UNK]": 0, "[CLS]": 1, "[SEP]": 2},
            unk_token="[UNK]",  # noqa: S106 - tokenizer marker, not a credential
        ),
    )
    tokenizer.pre_tokenizer = WhitespaceSplit()
    tokenizer.post_processor = TemplateProcessing(
        single="[CLS] $A [SEP]",
        special_tokens=[("[CLS]", 1), ("[SEP]", 2)],
    )
    monkeypatch.setattr(chunker, "_embedding_tokenizer", lambda: (tokenizer, 256))
    return tokenizer
