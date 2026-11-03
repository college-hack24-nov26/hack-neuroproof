"""Synthetic training-data tests; no patient MRI or model training."""

from __future__ import annotations

import hashlib
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
import torch

from cerebrachain_ml.training_data import (
    TrainingDataError,
    load_training_case,
)


CASE_ID = "BraTS2021_00495"
MODALITIES = ("flair", "t1", "t1ce", "t2")


@pytest.fixture
def synthetic_case(tmp_path: Path) -> Path:
    directory = tmp_path / CASE_ID
    directory.mkdir()

    shape = (8, 8, 8)
    affine = np.eye(4)

    base = np.indices(shape).sum(axis=0).astype(np.float32) + 1

    for index, modality in enumerate(MODALITIES):
        image = nib.Nifti1Image(base + index, affine)
        nib.save(
            image,
            directory / f"{CASE_ID}_{modality}.nii.gz",
        )

    labels = np.zeros(shape, dtype=np.uint8)
    labels[1, 1, 1] = 1
    labels[2, 2, 2] = 2
    labels[3, 3, 3] = 4

    nib.save(
        nib.Nifti1Image(labels, affine),
        directory / f"{CASE_ID}_seg.nii.gz",
    )

    return directory


def test_valid_training_case_and_label_mapping(
    synthetic_case: Path,
) -> None:
    segmentation_path = synthetic_case / f"{CASE_ID}_seg.nii.gz"

    original_sha = hashlib.sha256(
        segmentation_path.read_bytes()
    ).hexdigest()

    result = load_training_case(synthetic_case, CASE_ID)

    assert result.image.shape == (1, 4, 8, 8, 8)
    assert result.target.shape == (1, 8, 8, 8)
    assert result.target.dtype == torch.int64

    assert torch.isfinite(result.image).all()

    assert result.target[0, 1, 1, 1].item() == 1
    assert result.target[0, 2, 2, 2].item() == 2
    assert result.target[0, 3, 3, 3].item() == 3

    assert set(torch.unique(result.target).tolist()) == {
        0, 1, 2, 3
    }

    assert hashlib.sha256(
        segmentation_path.read_bytes()
    ).hexdigest() == original_sha


def test_invalid_label_rejected(synthetic_case: Path) -> None:
    path = synthetic_case / f"{CASE_ID}_seg.nii.gz"

    labels = np.zeros((8, 8, 8), dtype=np.uint8)
    labels[1, 1, 1] = 3

    nib.save(nib.Nifti1Image(labels, np.eye(4)), path)

    with pytest.raises(TrainingDataError):
        load_training_case(synthetic_case, CASE_ID)


def test_affine_mismatch_rejected(synthetic_case: Path) -> None:
    path = synthetic_case / f"{CASE_ID}_seg.nii.gz"

    labels = np.zeros((8, 8, 8), dtype=np.uint8)
    labels[1, 1, 1] = 4

    affine = np.eye(4)
    affine[0, 3] = 10

    nib.save(nib.Nifti1Image(labels, affine), path)

    with pytest.raises(TrainingDataError):
        load_training_case(synthetic_case, CASE_ID)


def test_missing_segmentation_rejected(
    synthetic_case: Path,
) -> None:
    (synthetic_case / f"{CASE_ID}_seg.nii.gz").unlink()

    with pytest.raises(TrainingDataError):
        load_training_case(synthetic_case, CASE_ID)


def test_empty_tumour_rejected(synthetic_case: Path) -> None:
    path = synthetic_case / f"{CASE_ID}_seg.nii.gz"

    labels = np.zeros((8, 8, 8), dtype=np.uint8)

    nib.save(
        nib.Nifti1Image(labels, np.eye(4)),
        path,
    )

    with pytest.raises(TrainingDataError):
        load_training_case(synthetic_case, CASE_ID)


def test_invalid_case_reference_rejected(
    synthetic_case: Path,
) -> None:
    with pytest.raises(TrainingDataError):
        load_training_case(
            synthetic_case,
            "../unauthorized-case",
        )
