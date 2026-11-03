"""Tests for the bounded local training engine.

Uses synthetic tensors and a lightweight 3D model only.
No real MRI, checkpoint writes, database, or network access.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest
import torch
from torch import nn

from cerebrachain_ml.local_training import (
    LocalTrainingError,
    train_local_single_step,
)
from cerebrachain_ml.training_data import PreparedTrainingCase


@pytest.fixture
def synthetic_case() -> PreparedTrainingCase:
    generator = torch.Generator().manual_seed(42)

    image = torch.randn(
        (1, 4, 32, 32, 32),
        generator=generator,
    )

    target = torch.zeros(
        (1, 32, 32, 32),
        dtype=torch.int64,
    )

    target[:, 8:16, 8:16, 8:16] = 3

    return PreparedTrainingCase(
        case_reference="BraTS2021_00495",
        image=image,
        target=target,
        original_shape=(32, 32, 32),
    )


@pytest.fixture
def synthetic_model() -> nn.Module:
    torch.manual_seed(42)

    return nn.Conv3d(
        in_channels=4,
        out_channels=4,
        kernel_size=1,
    )


def test_training_requires_authorization(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    with pytest.raises(
        LocalTrainingError,
        match="authorization",
    ):
        train_local_single_step(
            synthetic_model,
            synthetic_case,
        )


def test_training_requires_both_flags(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    for enabled, authorized in [
        (False, True),
        (True, False),
    ]:
        with pytest.raises(LocalTrainingError):
            train_local_single_step(
                synthetic_model,
                synthetic_case,
                execution_enabled=enabled,
                execution_authorized=authorized,
            )


def test_training_updates_weights_without_changing_original(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    original_weights = OrderedDict(
        (
            name,
            tensor.detach().clone(),
        )
        for name, tensor in synthetic_model.state_dict().items()
    )

    result = train_local_single_step(
        synthetic_model,
        synthetic_case,
        execution_enabled=True,
        execution_authorized=True,
        learning_rate=0.0001,
    )

    assert result.optimizer_steps == 1
    assert result.sample_count == 1
    assert result.patch_shape == (32, 32, 32)

    assert len(result.loss_history) == 1
    assert 0 < result.loss_history[0] < float("inf")

    # Caller-owned original model must remain unchanged.
    for name, original in original_weights.items():
        assert torch.equal(
            synthetic_model.state_dict()[name],
            original,
        )

    # At least one trained tensor must differ.
    changed = [
        not torch.equal(
            result.trained_state_dict[name],
            original,
        )
        for name, original in original_weights.items()
    ]

    assert any(changed)

    assert all(
        torch.isfinite(tensor).all().item()
        for tensor in result.trained_state_dict.values()
    )


def test_invalid_learning_rate_rejected(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    with pytest.raises(LocalTrainingError):
        train_local_single_step(
            synthetic_model,
            synthetic_case,
            execution_enabled=True,
            execution_authorized=True,
            learning_rate=float("nan"),
        )


def test_invalid_patch_size_rejected(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    with pytest.raises(LocalTrainingError):
        train_local_single_step(
            synthetic_model,
            synthetic_case,
            execution_enabled=True,
            execution_authorized=True,
            patch_size=(64, 64, 64),
        )


def test_multiple_steps_rejected(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    with pytest.raises(LocalTrainingError):
        train_local_single_step(
            synthetic_model,
            synthetic_case,
            execution_enabled=True,
            execution_authorized=True,
            max_steps=2,
        )


def test_invalid_segmentation_target_rejected(
    synthetic_model: nn.Module,
    synthetic_case: PreparedTrainingCase,
) -> None:
    invalid_target = synthetic_case.target.clone()
    invalid_target[0, 0, 0, 0] = 4

    invalid_case = PreparedTrainingCase(
        case_reference=synthetic_case.case_reference,
        image=synthetic_case.image,
        target=invalid_target,
        original_shape=synthetic_case.original_shape,
    )

    with pytest.raises(LocalTrainingError):
        train_local_single_step(
            synthetic_model,
            invalid_case,
            execution_enabled=True,
            execution_authorized=True,
        )
