"""Segmentation statistics derived from an actual generated mask."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import nibabel as nib
import numpy as np

from cerebrachain_ml.errors import InferenceError

BRATS_LABELS: Mapping[int, str] = {
    1: "necrotic_or_non_enhancing_core",
    2: "edema",
    4: "enhancing_tumor",
}


@dataclass(frozen=True)
class TumorStatistics:
    """Voxel and physical-volume statistics for a segmentation mask."""

    tumor_voxels: int
    label_voxels: dict[str, int]
    voxel_volume_mm3: float
    tumor_volume_mm3: float
    tumor_volume_ml: float


def calculate_tumor_statistics(
    segmentation_mask: np.ndarray,
    header: nib.nifti1.Nifti1Header,
) -> TumorStatistics:
    """Calculate physical tumor volume from a generated NIfTI mask."""

    if segmentation_mask.ndim != 3:
        raise InferenceError("Segmentation mask must be three-dimensional.")

    zooms = header.get_zooms()[:3]
    if len(zooms) != 3 or any(float(value) <= 0 for value in zooms):
        raise InferenceError("MRI voxel spacing is invalid.")

    voxel_volume_mm3 = float(np.prod(np.abs(zooms)))
    tumor_voxels = int(np.count_nonzero(segmentation_mask))
    label_voxels = {
        label_name: int(np.count_nonzero(segmentation_mask == label_value))
        for label_value, label_name in BRATS_LABELS.items()
    }
    tumor_volume_mm3 = tumor_voxels * voxel_volume_mm3

    return TumorStatistics(
        tumor_voxels=tumor_voxels,
        label_voxels=label_voxels,
        voxel_volume_mm3=voxel_volume_mm3,
        tumor_volume_mm3=tumor_volume_mm3,
        tumor_volume_ml=tumor_volume_mm3 / 1000.0,
    )
