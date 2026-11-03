"""Safe NIfTI persistence for derived segmentation masks."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import nibabel as nib
import numpy as np

from cerebrachain_ml.errors import InferenceError


def save_segmentation_mask(
    segmentation_mask: np.ndarray,
    reference: nib.spatialimages.SpatialImage,
    output_path: Path,
) -> None:
    """Atomically write a uint8 NIfTI mask with the reference spatial metadata."""

    if output_path.exists():
        raise InferenceError("Refusing to overwrite an existing segmentation result.")
    if tuple(segmentation_mask.shape) != tuple(reference.shape):
        raise InferenceError("Segmentation mask dimensions do not match the input MRI.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.{uuid4().hex}.tmp.nii.gz")
    header = reference.header.copy()
    header.set_data_dtype(np.uint8)
    result = nib.Nifti1Image(segmentation_mask.astype(np.uint8), reference.affine, header)

    try:
        nib.save(result, str(temporary_path))
        os.replace(temporary_path, output_path)
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        raise InferenceError("Segmentation artifact could not be written.") from exc
