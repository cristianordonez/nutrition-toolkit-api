"""Keep package-relative model and data assets when freezing the engine."""

# ruff: noqa: N999 - PyInstaller's required hook naming convention

from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

from engine.paths import bundled_embedding_model_dir, bundled_reference_database

# Abort frozen builds with incomplete assets, as wheel builds do.
bundled_embedding_model_dir()
if bundled_reference_database() is None:
    msg = (
        "Bundled reference database is missing. Run "
        "apps/desktop/engine/scripts/build_reference_database.py first."
    )
    raise RuntimeError(msg)
datas = collect_data_files(
    "engine",
    includes=["assets/models/**/*", "assets/reference/facts.db"],
)
datas += copy_metadata("engine")

# The pinned modules.json and transformers' AutoModel use dynamic imports.
# Sentence Transformers 6 registers the old `sentence_transformers.models`
# name as a runtime alias of this real package.
hiddenimports = [
    "sentence_transformers.sentence_transformer.modules",
    "transformers.models.bert.modeling_bert",
    "transformers.models.bert.tokenization_bert",
]
