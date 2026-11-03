"""Memory-conscious CPU inference and legacy-compatible postprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np
import torch
from monai.inferers import SlidingWindowInferer
from torch import nn

from cerebrachain_ml.errors import InferenceError
from cerebrachain_ml.preprocessing import PreparedMri


@dataclass(frozen=True)
class SegmentationPrediction:
    """A postprocessed multiclass segmentation mask and its runtime metadata."""

    mask: np.ndarray
    labels: list[int]
    duration_seconds: float


def run_segmentation(
    model: nn.Module,
    prepared_mri: PreparedMri,
    *,
    device: str = "cpu",
    overlap: float = 0.5,
) -> SegmentationPrediction:
    """Run CPU inference and restore BraTS label 4.

    The default overlap reproduces the legacy inference window configuration.
    Set ``overlap=0.0`` for the explicit CPU-safe bounded profile.
    Neither profile changes model architecture, input preprocessing, or label
    postprocessing.
    """

    if device != "cpu":
        raise InferenceError("This Phase 2 service supports CPU inference only.")
    if not 0 <= overlap < 1:
        raise InferenceError(
            "Sliding-window overlap must be from 0 (inclusive) to 1 (exclusive)."
        )

    input_tensor = prepared_mri.input_tensor
    expected_input_shape = (1, 4, *prepared_mri.original_shape)
    if tuple(input_tensor.shape) != expected_input_shape:
        raise InferenceError("MRI tensor does not match the expected model input shape.")

    inferer = SlidingWindowInferer(
        roi_size=(96, 96, 96),
        sw_batch_size=1,
        overlap=overlap,
        mode="gaussian",
    )
    start = perf_counter()
    model.eval()
    try:
        with torch.inference_mode():
            logits = inferer(input_tensor.to(device), model)
    except Exception as exc:
        raise InferenceError("3D U-Net inference failed.") from exc
    duration_seconds = perf_counter() - start

    expected_output_shape = (1, 4, *prepared_mri.original_shape)
    if tuple(logits.shape) != expected_output_shape:
        raise InferenceError("3D U-Net output has an unexpected shape.")
    if not bool(torch.isfinite(logits).all().item()):
        raise InferenceError("3D U-Net produced non-finite output values.")

    prediction = torch.argmax(logits, dim=1).squeeze(0).cpu().numpy().astype(np.uint8)
    flair = np.asanyarray(prepared_mri.reference.dataobj)
    prediction[flair == 0] = 0
    prediction[prediction == 3] = 4

    return SegmentationPrediction(
        mask=prediction,
        labels=[int(value) for value in np.unique(prediction).tolist()],
        duration_seconds=duration_seconds,
    )
