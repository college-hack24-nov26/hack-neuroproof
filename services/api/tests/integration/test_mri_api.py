"""Phase 2 regression test that performs exactly one real CPU MRI inference.

Authenticated HTTP coverage belongs to the PostgreSQL-backed Phase 3 test path.
This regression test verifies that the MRI service itself remains independent of
HTTP and authentication implementation details.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import nibabel as nib
from fastapi import UploadFile

from app.core.config import Settings
from app.services.mri_segmentation import MriSegmentationService


def test_real_mri_segmentation_service_regression(
    configured_settings: Settings,
    external_mri_paths: dict[str, Path],
) -> None:
    """Exercise real inference, protected persistence, and saved-mask dimensions."""

    service = MriSegmentationService(configured_settings)
    with ExitStack() as stack:
        uploads = {
            modality: UploadFile(
                filename=path.name,
                file=stack.enter_context(path.open("rb")),
                headers={"content-type": "application/gzip"},
            )
            for modality, path in external_mri_paths.items()
        }
        submitted = service.submit(uploads)

    assert submitted.status.value == "completed"
    job_status = service.get_job(submitted.job_id)
    assert job_status.status.value == "completed"

    result = service.get_completed_result(submitted.job_id)
    assert result.status.value == "completed"
    assert result.input_shape is not None
    assert result.segmentation_shape is not None
    assert result.statistics is not None
    assert result.input_shape[0:2] == (1, 4)
    assert result.segmentation_shape == result.input_shape[2:]
    assert result.statistics.tumor_voxels >= 0
    assert result.statistics.tumor_volume_ml >= 0

    artifact_path = configured_settings.result_storage_dir / submitted.job_id / "segmentation.nii.gz"
    assert artifact_path.is_file()
    saved_mask = nib.load(str(artifact_path))
    assert tuple(saved_mask.shape) == result.segmentation_shape
    assert service.result_artifact_path(submitted.job_id) == artifact_path
