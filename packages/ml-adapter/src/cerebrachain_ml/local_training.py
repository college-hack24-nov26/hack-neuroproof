"""Bounded hospital-local 3D segmentation training.

This module performs no automatic execution, network requests,
database operations, or checkpoint writes.

The caller must enforce hospital identity, dataset authorization,
and checkpoint provenance before requesting training.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite

import torch
from torch import nn
from torch.nn import functional as F

from cerebrachain_ml.training_data import PreparedTrainingCase


class LocalTrainingError(RuntimeError):
    """Local training was rejected or failed validation."""


@dataclass(frozen=True)
class LocalTrainingResult:
    """CPU model weights and auditable training statistics."""

    trained_state_dict: OrderedDict[str, torch.Tensor]
    loss_history: tuple[float, ...]
    optimizer_steps: int
    sample_count: int
    patch_shape: tuple[int, int, int]


def _validate_inputs(
    model: nn.Module,
    case: PreparedTrainingCase,
    *,
    execution_enabled: bool,
    execution_authorized: bool,
    learning_rate: float,
    patch_size: tuple[int, int, int],
    max_steps: int,
) -> None:
    if not execution_enabled or not execution_authorized:
        raise LocalTrainingError(
            "Training execution requires explicit authorization."
        )

    if not isinstance(model, nn.Module):
        raise LocalTrainingError("Invalid training model.")

    if not isinstance(case, PreparedTrainingCase):
        raise LocalTrainingError("Invalid prepared training case.")

    if not isfinite(learning_rate) or not 0 < learning_rate <= 0.001:
        raise LocalTrainingError(
            "Learning rate must be finite and in (0, 0.001]."
        )

    if max_steps != 1:
        raise LocalTrainingError(
            "This bounded development profile permits exactly one step."
        )

    if (
        len(patch_size) != 3
        or any(
            not isinstance(size, int)
            or isinstance(size, bool)
            or size != 32
            for size in patch_size
        )
    ):
        raise LocalTrainingError(
            "This development profile requires a 32x32x32 patch."
        )

    if (
        case.image.ndim != 5
        or case.image.shape[0:2] != (1, 4)
    ):
        raise LocalTrainingError(
            "Training image must have shape (1, 4, H, W, D)."
        )

    if case.target.shape != (
        1,
        *case.image.shape[2:]
    ):
        raise LocalTrainingError(
            "Training target geometry does not match MRI."
        )

    if case.target.dtype != torch.int64:
        raise LocalTrainingError(
            "Training target must contain int64 class indices."
        )

    if any(
        dimension < size
        for dimension, size in zip(
            case.image.shape[2:], patch_size
        )
    ):
        raise LocalTrainingError(
            "MRI is smaller than the required training patch."
        )

    if not bool(torch.isfinite(case.image).all().item()):
        raise LocalTrainingError(
            "Training MRI contains non-finite values."
        )

    if not bool(
        ((case.target >= 0) & (case.target <= 3))
        .all()
        .item()
    ):
        raise LocalTrainingError(
            "Training target contains invalid class indices."
        )

    if not bool((case.target > 0).any().item()):
        raise LocalTrainingError(
            "Training target contains no tumour voxels."
        )


def _extract_patch(
    case: PreparedTrainingCase,
    patch_size: tuple[int, int, int],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Choose a deterministic patch containing a tumour voxel."""

    tumour_positions = torch.nonzero(
        case.target[0] > 0,
        as_tuple=False,
    )

    centre = tumour_positions[
        len(tumour_positions) // 2
    ].tolist()

    starts = tuple(
        max(
            0,
            min(
                coordinate - size // 2,
                dimension - size,
            ),
        )
        for coordinate, size, dimension in zip(
            centre,
            patch_size,
            case.image.shape[2:],
        )
    )

    slices = tuple(
        slice(start, start + size)
        for start, size in zip(starts, patch_size)
    )

    image_patch = case.image[
        (slice(None), slice(None), *slices)
    ]

    target_patch = case.target[
        (slice(None), *slices)
    ]

    return (
        image_patch.contiguous(),
        target_patch.contiguous(),
    )


def train_local_single_step(
    model: nn.Module,
    case: PreparedTrainingCase,
    *,
    execution_enabled: bool = False,
    execution_authorized: bool = False,
    learning_rate: float = 0.0001,
    patch_size: tuple[int, int, int] = (32, 32, 32),
    max_steps: int = 1,
) -> LocalTrainingResult:
    """Perform one explicitly authorized CPU training step.

    This is a development-only primitive, not a complete
    hospital training workflow.

    It clones the supplied model, so original weights are unchanged.
    No trained checkpoint is written automatically.
    """

    _validate_inputs(
        model,
        case,
        execution_enabled=execution_enabled,
        execution_authorized=execution_authorized,
        learning_rate=learning_rate,
        patch_size=patch_size,
        max_steps=max_steps,
    )

    image_patch, target_patch = _extract_patch(
        case,
        patch_size,
    )

    # Never modify the caller's verified base model.
    local_model = deepcopy(model).to("cpu")
    local_model.train()

    trainable_parameters = [
        parameter
        for parameter in local_model.parameters()
        if parameter.requires_grad
    ]

    if not trainable_parameters:
        raise LocalTrainingError(
            "Model contains no trainable parameters."
        )

    optimizer = torch.optim.Adam(
        trainable_parameters,
        lr=learning_rate,
    )

    optimizer.zero_grad(set_to_none=True)

    logits = local_model(
        image_patch.detach().to(
            device="cpu",
            dtype=torch.float32,
        )
    )

    expected_shape = (
        1,
        4,
        *patch_size,
    )

    if tuple(logits.shape) != expected_shape:
        raise LocalTrainingError(
            "3D segmentation model output shape is invalid."
        )

    if not bool(torch.isfinite(logits).all().item()):
        raise LocalTrainingError(
            "Model produced non-finite logits."
        )

    loss = F.cross_entropy(
        logits,
        target_patch.to(
            device="cpu",
            dtype=torch.int64,
        ),
    )

    if not bool(torch.isfinite(loss).item()):
        raise LocalTrainingError(
            "Segmentation loss is non-finite."
        )

    loss.backward()

    if any(
        parameter.grad is not None
        and not bool(torch.isfinite(parameter.grad).all().item())
        for parameter in trainable_parameters
    ):
        raise LocalTrainingError(
            "Training produced non-finite gradients."
        )

    optimizer.step()

    if any(
        not bool(torch.isfinite(parameter).all().item())
        for parameter in local_model.parameters()
    ):
        raise LocalTrainingError(
            "Training produced non-finite model weights."
        )

    updated_state = OrderedDict(
        (
            name,
            tensor.detach().cpu().clone(),
        )
        for name, tensor in local_model.state_dict().items()
    )

    return LocalTrainingResult(
        trained_state_dict=updated_state,
        loss_history=(float(loss.detach().item()),),
        optimizer_steps=1,
        sample_count=1,
        patch_shape=patch_size,
    )
