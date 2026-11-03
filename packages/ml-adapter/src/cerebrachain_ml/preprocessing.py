"""Validated MRI preprocessing matching the original real-inference pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import nibabel as nib
import numpy as np
import torch
from monai.transforms import Compose, EnsureChannelFirstd, EnsureTyped, LoadImaged, NormalizeIntensityd

from cerebrachain_ml.architecture import MODALITY_ORDER
from cerebrachain_ml.errors import MriValidationError


@dataclass(frozen=True)
class PreparedMri:
    """A normalized model tensor paired with its reference NIfTI metadata."""

    input_tensor: torch.Tensor
    reference: nib.spatialimages.SpatialImage
    original_shape: tuple[int, int, int]


def _ordered_paths(modality_paths: Mapping[str, Path]) -> list[Path]:
    if set(modality_paths) != set(MODALITY_ORDER):
        raise MriValidationError("Exactly FLAIR, T1, T1CE, and T2 MRI files are required.")

    paths = [Path(modality_paths[modality]) for modality in MODALITY_ORDER]
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise MriValidationError("An uploaded MRI file is unavailable.")
        if not path.name.lower().endswith(".nii.gz"):
            raise MriValidationError("MRI uploads must use the .nii.gz format.")
    return paths


def _load_reference(paths: list[Path]) -> nib.spatialimages.SpatialImage:
    try:
        reference = nib.load(str(paths[0]))
    except Exception as exc:
        raise MriValidationError("The FLAIR MRI file cannot be decoded.") from exc

    if len(reference.shape) != 3:
        raise MriValidationError("MRI volumes must be three-dimensional.")

    expected_shape = tuple(int(value) for value in reference.shape)
    for path in paths[1:]:
        try:
            image = nib.load(str(path))
        except Exception as exc:
            raise MriValidationError("An MRI modality cannot be decoded.") from exc

        if len(image.shape) != 3 or tuple(image.shape) != expected_shape:
            raise MriValidationError("MRI modality dimensions do not match.")
        if not np.allclose(image.affine, reference.affine):
            raise MriValidationError("MRI modality spatial alignment does not match.")

    return reference


def preprocess_mri(modality_paths: Mapping[str, Path]) -> PreparedMri:
    """Validate and normalize four aligned MRI modalities using the original MONAI transforms."""

    paths = _ordered_paths(modality_paths)
    reference = _load_reference(paths)
    transforms = Compose(
        [
            LoadImaged(keys="image"),
            EnsureChannelFirstd(keys="image"),
            NormalizeIntensityd(keys="image", nonzero=True, channel_wise=True),
            EnsureTyped(keys="image"),
        ]
    )

    try:
        processed = transforms({"image": [str(path) for path in paths]})
        tensor = processed["image"].unsqueeze(0)
    except Exception as exc:
        raise MriValidationError("MRI preprocessing failed.") from exc

    expected_shape = (1, len(MODALITY_ORDER), *reference.shape)
    if tuple(tensor.shape) != expected_shape:
        raise MriValidationError("Preprocessed MRI tensor has an unexpected shape.")
    if not bool(torch.isfinite(tensor).all().item()):
        raise MriValidationError("MRI preprocessing produced non-finite values.")

    return PreparedMri(
        input_tensor=tensor,
        reference=reference,
        original_shape=tuple(int(value) for value in reference.shape),
    )
