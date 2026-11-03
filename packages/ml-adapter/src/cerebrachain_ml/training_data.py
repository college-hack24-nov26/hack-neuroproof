"""Hospital-local BraTS training data preparation.

Reuses the existing inference MRI normalization.
Does not train models, modify MRI files, or upload patient data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import nibabel as nib
import numpy as np
import torch

from cerebrachain_ml.architecture import MODALITY_ORDER
from cerebrachain_ml.preprocessing import preprocess_mri


BRATS_LABEL_MAPPING = {
    0: 0,
    1: 1,
    2: 2,
    4: 3,
}

ALLOWED_LABELS = frozenset(BRATS_LABEL_MAPPING)


class TrainingDataError(RuntimeError):
    """Training dataset validation failed."""


@dataclass(frozen=True)
class PreparedTrainingCase:
    """Normalized MRI and aligned segmentation target."""

    case_reference: str
    image: torch.Tensor
    target: torch.Tensor
    original_shape: tuple[int, int, int]


def load_training_case(
    case_directory: Path,
    case_reference: str,
) -> PreparedTrainingCase:
    """Load one explicitly selected local BraTS case.

    Image shape:  (1, 4, H, W, D)
    Target shape: (1, H, W, D)

    Target values: 0, 1, 2, 3.
    """

    directory = Path(case_directory)

    if not re.fullmatch(r"BraTS2021_[0-9]{5}", case_reference):
        raise TrainingDataError(
            "Invalid BraTS case reference."
        )

    if (
        not directory.is_dir()
        or directory.is_symlink()
        or directory.name != case_reference
    ):
        raise TrainingDataError(
            "Invalid local training case directory."
        )

    modality_paths = {
        modality: (
            directory / f"{case_reference}_{modality}.nii.gz"
        )
        for modality in MODALITY_ORDER
    }

    segmentation_path = (
        directory / f"{case_reference}_seg.nii.gz"
    )

    all_paths = [
        *modality_paths.values(),
        segmentation_path,
    ]

    if any(
        not path.is_file() or path.is_symlink()
        for path in all_paths
    ):
        raise TrainingDataError(
            "Required MRI or segmentation file is missing."
        )

    # Reuse inference preprocessing exactly.
    try:
        prepared = preprocess_mri(modality_paths)
    except Exception as exc:
        raise TrainingDataError(
            "MRI preprocessing failed."
        ) from exc

    try:
        segmentation_image = nib.load(
            str(segmentation_path)
        )

        if (
            len(segmentation_image.shape) != 3
            or tuple(segmentation_image.shape)
            != prepared.original_shape
        ):
            raise TrainingDataError(
                "Segmentation dimensions do not match MRI."
            )

        if not np.allclose(
            segmentation_image.affine,
            prepared.reference.affine,
            rtol=0,
            atol=1e-4,
        ):
            raise TrainingDataError(
                "Segmentation spatial alignment mismatch."
            )

        labels = np.asanyarray(
            segmentation_image.dataobj
        )

        unique_labels = np.unique(labels)

        if not np.all(np.isfinite(unique_labels)):
            raise TrainingDataError(
                "Segmentation contains non-finite labels."
            )

        if not all(
            label in ALLOWED_LABELS
            for label in unique_labels
        ):
            raise TrainingDataError(
                "Segmentation contains invalid BraTS labels."
            )

        if not np.any(labels != 0):
            raise TrainingDataError(
                "Segmentation contains no tumour labels."
            )

        # Create a separate target array.
        # Original segmentation file remains unchanged.
        mapped = np.zeros(
            labels.shape,
            dtype=np.uint8,
        )

        for original, training_class in (
            BRATS_LABEL_MAPPING.items()
        ):
            mapped[labels == original] = training_class

        target = (
            torch.from_numpy(mapped)
            .long()
            .unsqueeze(0)
        )

        expected_image_shape = (
            1,
            4,
            *prepared.original_shape,
        )

        expected_target_shape = (
            1,
            *prepared.original_shape,
        )

        if tuple(prepared.input_tensor.shape) != expected_image_shape:
            raise TrainingDataError(
                "Training image tensor shape is invalid."
            )

        if tuple(target.shape) != expected_target_shape:
            raise TrainingDataError(
                "Training target tensor shape is invalid."
            )

        return PreparedTrainingCase(
            case_reference=case_reference,
            image=prepared.input_tensor,
            target=target,
            original_shape=prepared.original_shape,
        )

    except TrainingDataError:
        raise

    except Exception as exc:
        raise TrainingDataError(
            "Segmentation loading failed."
        ) from exc
