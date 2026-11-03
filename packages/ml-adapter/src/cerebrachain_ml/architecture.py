"""The exact MONAI 3D U-Net architecture used by the verified legacy checkpoint."""

from __future__ import annotations

from typing import Final

import torch
from monai.networks.nets import UNet

MODALITY_ORDER: Final[tuple[str, str, str, str]] = ("flair", "t1", "t1ce", "t2")
MODEL_PARAMETER_COUNT: Final[int] = 2_453_636
MODEL_ARCHITECTURE: Final[dict[str, object]] = {
    "name": "monai.UNet",
    "spatial_dims": 3,
    "in_channels": 4,
    "out_channels": 4,
    "channels": (16, 32, 64, 128, 256),
    "strides": (2, 2, 2, 2),
    "num_res_units": 1,
    "norm": "instance",
}


def build_model() -> UNet:
    """Create the architecture that must strictly match the approved checkpoint."""

    return UNet(
        spatial_dims=3,
        in_channels=4,
        out_channels=4,
        channels=(16, 32, 64, 128, 256),
        strides=(2, 2, 2, 2),
        num_res_units=1,
        norm="instance",
    )


def parameter_count(model: torch.nn.Module) -> int:
    """Return the number of trainable and non-trainable model parameters."""

    return sum(parameter.numel() for parameter in model.parameters())
