"""Checkpoint selection must fail before MRI uploads are persisted."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.core.config import Settings
from app.core.errors import MriInferenceUnavailableError
from app.services.mri_segmentation import MriSegmentationService
from cerebrachain_ml.errors import ModelLoadError


def _uploads() -> dict[str, UploadFile]:
    return {
        modality: UploadFile(
            filename=f"research-case_{modality}.nii.gz",
            file=BytesIO(b"not-read-before-model-preflight"),
        )
        for modality in ("flair", "t1", "t1ce", "t2")
    }


def test_incompatible_global_model_rejects_before_upload_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No protected job directory is created for an incompatible global checkpoint."""

    result_root = tmp_path / "protected-results"
    service = MriSegmentationService(
        Settings(
            model_checkpoint_path=tmp_path / "local.pth",
            model_sha256="a" * 64,
            global_model_checkpoint_path=tmp_path / "global.pth",
            global_model_sha256="b" * 64,
            result_storage_dir=result_root,
            inference_device="cpu",
        )
    )

    def fail_strict_load(*_: object, **__: object) -> object:
        raise ModelLoadError("incompatible")

    monkeypatch.setattr(
        "app.services.mri_segmentation.load_verified_model",
        fail_strict_load,
    )

    with pytest.raises(
        MriInferenceUnavailableError,
        match="incompatible with the approved 3D U-Net",
    ):
        service.submit(_uploads(), model_source="global_fedavg_abc")

    assert result_root.is_dir()
    assert list(result_root.iterdir()) == []
