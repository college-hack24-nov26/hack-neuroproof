"""Unit coverage for the accepted NIfTI upload extensions."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi import UploadFile

from app.core.errors import MriInputError
from app.models.mri import MriJob
from app.repositories.mri_jobs import FileSystemMriJobRepository
from app.services.mri_segmentation import MriSegmentationService
from cerebrachain_ml.preprocessing import preprocess_mri


def _uploads(extension: str) -> dict[str, UploadFile]:
    return {
        modality: UploadFile(filename=f"example_{modality}{extension}", file=BytesIO(b"data"))
        for modality in ("flair", "t1", "t1ce", "t2")
    }


@pytest.mark.parametrize("extension", [".nii", ".nii.gz"])
def test_upload_validation_accepts_supported_nifti_extensions(extension: str) -> None:
    """The HTTP contract accepts compressed and uncompressed NIfTI names."""

    assert MriSegmentationService._validate_uploads(_uploads(extension)) == {
        "flair": extension,
        "t1": extension,
        "t1ce": extension,
        "t2": extension,
    }


def test_upload_validation_rejects_non_nifti_extension() -> None:
    """Unsupported names fail before data is written to protected storage."""

    with pytest.raises(MriInputError, match="must be a .nii or .nii.gz MRI file"):
        MriSegmentationService._validate_uploads(_uploads(".dcm"))


def test_repository_resolves_generated_uncompressed_nifti_paths(tmp_path: Path) -> None:
    """Generated upload filenames retain only a vetted extension, never a client path."""

    repository = FileSystemMriJobRepository(tmp_path / "protected-results")
    job = MriJob.create()
    repository.create(job)
    for modality in ("flair", "t1", "t1ce", "t2"):
        repository.save_upload(
            job.job_id,
            modality,
            BytesIO(b"nifti"),
            extension=".nii",
            max_bytes=100,
        )

    assert all(path.suffix == ".nii" for path in repository.modality_paths(job.job_id).values())


def test_preprocessing_accepts_uncompressed_nifti_modalities(tmp_path: Path) -> None:
    """Accepted ``.nii`` uploads reach the same four-channel preprocessing path."""

    paths: dict[str, Path] = {}
    affine = np.diag((1.0, 1.0, 1.0, 1.0))
    for index, modality in enumerate(("flair", "t1", "t1ce", "t2"), start=1):
        path = tmp_path / f"synthetic_{modality}.nii"
        volume = np.zeros((16, 16, 16), dtype=np.float32)
        volume[2:14, 2:14, 2:14] = float(index)
        nib.save(nib.Nifti1Image(volume, affine), str(path))
        paths[modality] = path

    prepared = preprocess_mri(paths)

    assert tuple(prepared.input_tensor.shape) == (1, 4, 16, 16, 16)
