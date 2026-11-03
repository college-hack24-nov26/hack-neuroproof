"""Unit tests for custom-coordinator weighted FedAvg safety checks."""

from __future__ import annotations

from collections import OrderedDict
from uuid import uuid4

import pytest
import torch

from app.modules.federation.fedavg import (
    FedAvgAggregator,
    FedAvgValidationError,
    ModelUpdate,
    state_dict_sha256,
)


def _state(*, weight: list[float] | None = None, counter: int = 7) -> OrderedDict[str, torch.Tensor]:
    return OrderedDict(
        weight=torch.tensor(weight or [1.0, 3.0], dtype=torch.float32),
        batch_counter=torch.tensor(counter, dtype=torch.int64),
    )


def _update(
    *,
    state: OrderedDict[str, torch.Tensor],
    samples: int,
    hospital_id=None,
) -> ModelUpdate:
    return ModelUpdate(
        hospital_id=hospital_id or uuid4(),
        training_node_id=uuid4(),
        sample_count=samples,
        state_dict=state,
        model_version_commitment="a" * 64,
        hospital_update_commitment=state_dict_sha256(state),
    )


def test_weighted_fedavg_uses_stable_sample_weighting_and_preserves_dtype() -> None:
    first_hospital = uuid4()
    second_hospital = uuid4()
    first = _update(state=_state(weight=[1.0, 5.0]), samples=1, hospital_id=first_hospital)
    second = _update(state=_state(weight=[5.0, 1.0]), samples=3, hospital_id=second_hospital)

    result = FedAvgAggregator().aggregate([second, first])

    assert result.total_sample_count == 4
    assert result.participant_hospital_ids == tuple(sorted((first_hospital, second_hospital), key=str))
    assert result.state_dict["weight"].dtype is torch.float32
    assert torch.allclose(result.state_dict["weight"], torch.tensor([4.0, 2.0]))
    assert result.state_dict["batch_counter"].dtype is torch.int64
    assert torch.equal(result.state_dict["batch_counter"], torch.tensor(7, dtype=torch.int64))


@pytest.mark.parametrize(
    ("first", "second", "expected_code"),
    [
        (
            _update(state=_state(weight=[1.0, 2.0]), samples=1),
            _update(state=_state(weight=[1.0]), samples=1),
            "parameter_shape_mismatch",
        ),
        (
            _update(state=_state(weight=[1.0, 2.0]), samples=1),
            _update(state=_state(weight=[float("nan"), 2.0]), samples=1),
            "non_finite_tensor",
        ),
        (
            _update(state=_state(weight=[1.0, 2.0]), samples=1),
            _update(state=_state(weight=[1.0, 2.0], counter=8), samples=1),
            "invariant_tensor_mismatch",
        ),
    ],
)
def test_fedavg_rejects_incompatible_or_invalid_updates(
    first: ModelUpdate,
    second: ModelUpdate,
    expected_code: str,
) -> None:
    with pytest.raises(FedAvgValidationError) as error:
        FedAvgAggregator().aggregate([first, second])

    assert error.value.code == expected_code


def test_fedavg_rejects_invalid_sample_counts_and_duplicate_hospitals() -> None:
    hospital_id = uuid4()
    valid = _update(state=_state(), samples=1, hospital_id=hospital_id)
    invalid_samples = _update(state=_state(), samples=0)
    duplicate = _update(state=_state(), samples=1, hospital_id=hospital_id)

    with pytest.raises(FedAvgValidationError, match="sample_count") as invalid_error:
        FedAvgAggregator().aggregate([valid, invalid_samples])
    assert invalid_error.value.code == "invalid_sample_count"

    with pytest.raises(FedAvgValidationError) as duplicate_error:
        FedAvgAggregator().aggregate([valid, duplicate])
    assert duplicate_error.value.code == "duplicate_hospital_update"
