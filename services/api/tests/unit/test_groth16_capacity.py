"""Groth16 early capacity and resource-safety tests."""

import pytest
import torch

from app.modules.federation.groth16 import (
    Groth16VerificationError,
    _enforce_chunk_capacity,
)


def test_exact_capacity_accepted():
    state = {
        "weight": torch.zeros(1024),
    }

    _enforce_chunk_capacity(state, max_chunks=128)


def test_capacity_exceeded_rejected():
    state = {
        "weight": torch.zeros(1025),
    }

    with pytest.raises(
        Groth16VerificationError,
        match="more proofs",
    ):
        _enforce_chunk_capacity(state, max_chunks=128)


def test_capacity_across_multiple_tensors():
    state = {
        "layer1": torch.zeros(600),
        "layer2": torch.zeros(425),
    }

    with pytest.raises(Groth16VerificationError):
        _enforce_chunk_capacity(state, max_chunks=128)


def test_full_monai_size_rejected_without_loading_values():
    # Meta tensors occupy no real model-weight storage.
    state = {
        "model": torch.empty(
            2_453_636,
            device="meta",
        ),
    }

    with pytest.raises(
        Groth16VerificationError,
        match="more proofs",
    ):
        _enforce_chunk_capacity(state, max_chunks=128)


def test_invalid_tensor_rejected():
    with pytest.raises(Groth16VerificationError):
        _enforce_chunk_capacity(
            {"weight": object()},
            max_chunks=128,
        )


def test_invalid_capacity_configuration_rejected():
    for max_chunks in (0, -1, True):
        with pytest.raises(Groth16VerificationError):
            _enforce_chunk_capacity(
                {"weight": torch.zeros(8)},
                max_chunks=max_chunks,
            )
