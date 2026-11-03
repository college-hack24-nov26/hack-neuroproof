"""Validation tests using an explicitly configured local research MRI case."""

from __future__ import annotations

from pathlib import Path

import torch

from cerebrachain_ml.preprocessing import preprocess_mri


def test_original_preprocessing_returns_four_channel_tensor(
    external_mri_paths: dict[str, Path],
) -> None:
    """The original MONAI pipeline must produce one finite four-modal MRI tensor."""

    prepared = preprocess_mri(external_mri_paths)

    assert tuple(prepared.input_tensor.shape) == (1, 4, *prepared.original_shape)
    assert prepared.original_shape == tuple(int(value) for value in prepared.reference.shape)
    assert bool(torch.isfinite(prepared.input_tensor).all().item())
