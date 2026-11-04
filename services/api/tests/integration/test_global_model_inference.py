"""Regression coverage for real inference through the FedAvg model-selection path.

The MRI fixture is generated at test time, contains no patient data, and is
discarded by pytest.  It exercises the committed experimental checkpoint without
requiring an external research-data directory.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from fastapi import UploadFile
import nibabel as nib
import numpy as np
import pytest

from app.core.config import Settings
from app.services.mri_segmentation import MriSegmentationService
from app.services.mri_viewer import render_mri_slice


GLOBAL_MODEL_SHA256 = "796779c9a046e22c9360ac2fb2283a9066a6f250fc8e480fe6b645df7eaa1941"


@pytest.fixture
def synthetic_mri_paths(tmp_path: Path) -> dict[str, Path]:
    """Create four aligned, non-clinical NIfTI volumes for one CPU inference."""

    shape = (32, 32, 32)
    affine = np.diag((1.0, 1.1, 1.2, 1.0))
    coordinate = np.linspace(0.0, 1.0, shape[0], dtype=np.float32)
    gradient = coordinate[:, None, None] + coordinate[None, :, None]
    paths: dict[str, Path] = {}
    for index, modality in enumerate(("flair", "t1", "t1ce", "t2"), start=1):
        volume = np.zeros(shape, dtype=np.float32)
        volume[4:28, 4:28, 4:28] = gradient[4:28, 4:28, :] + float(index)
        path = tmp_path / f"synthetic_{modality}.nii.gz"
        nib.save(nib.Nifti1Image(volume, affine), str(path))
        paths[modality] = path
    return paths


def test_global_fedavg_selection_runs_real_inference_and_records_provenance(
    tmp_path: Path,
    synthetic_mri_paths: dict[str, Path],
) -> None:
    """The committed FedAvg checkpoint runs and records its exact provenance."""

    model_path = (
        Path(__file__).resolve().parents[4]
        / "ml_models"
        / "fedavg_round1_ABC_global_model.pth"
    )
    assert model_path.is_file(), "Committed global FedAvg checkpoint is unavailable."
    global_settings = Settings(
        model_checkpoint_path=None,
        model_sha256=None,
        global_model_checkpoint_path=model_path,
        global_model_sha256=GLOBAL_MODEL_SHA256,
        result_storage_dir=tmp_path / "protected-results",
        inference_device="cpu",
        cpu_threads=1,
        sliding_window_overlap=0.0,
    )
    service = MriSegmentationService(global_settings)
    model_info = service.model_info("global_fedavg_abc")
    assert model_info["configured"] is True
    assert model_info["integrity_status"] == "verified"
    assert model_info["checkpoint"] == {
        "sha256": GLOBAL_MODEL_SHA256,
        "size_bytes": model_path.stat().st_size,
    }
    with ExitStack() as stack:
        uploads = {
            modality: UploadFile(
                filename=path.name,
                file=stack.enter_context(path.open("rb")),
                headers={"content-type": "application/gzip"},
            )
            for modality, path in synthetic_mri_paths.items()
        }
        submitted = service.submit(uploads, model_source="global_fedavg_abc")

    assert submitted.status.value == "completed"
    assert submitted.model_source == "global_fedavg_abc"
    assert submitted.model_sha256 == GLOBAL_MODEL_SHA256
    assert submitted.input_shape == (1, 4, 32, 32, 32)
    assert submitted.segmentation_shape == (32, 32, 32)
    assert set(submitted.labels).issubset({0, 1, 2, 4})

    result = service.get_completed_result(submitted.job_id)
    assert result.model_source == "global_fedavg_abc"
    assert result.model_sha256 == GLOBAL_MODEL_SHA256
    assert result.statistics is not None

    modality_paths, segmentation_path = service.viewer_artifact_paths(
        submitted.job_id
    )
    preview = render_mri_slice(
        modality_paths["flair"],
        segmentation_path,
        plane="axial",
        position=0.5,
        overlay=True,
    )
    assert preview.startswith(b"\x89PNG\r\n\x1a\n")
