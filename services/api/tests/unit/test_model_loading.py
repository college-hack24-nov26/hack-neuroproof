"""Strict loading tests for the configured external MONAI checkpoint."""

from __future__ import annotations

from pathlib import Path

from cerebrachain_ml.architecture import MODEL_PARAMETER_COUNT, MODALITY_ORDER
from cerebrachain_ml.checkpoint import load_verified_model, verify_checkpoint


def test_checkpoint_hash_and_strict_model_load(
    external_model_path: Path,
    external_model_sha256: str,
) -> None:
    """The configured weights must hash correctly and load into the exact architecture."""

    checkpoint = verify_checkpoint(external_model_path, external_model_sha256)
    loaded = load_verified_model(external_model_path, external_model_sha256)

    assert checkpoint.sha256 == external_model_sha256
    assert checkpoint.size_bytes > 0
    assert sum(parameter.numel() for parameter in loaded.model.parameters()) == MODEL_PARAMETER_COUNT
    assert MODALITY_ORDER == ("flair", "t1", "t1ce", "t2")
