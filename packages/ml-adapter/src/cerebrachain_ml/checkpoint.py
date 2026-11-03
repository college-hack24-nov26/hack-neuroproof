"""Checkpoint hashing and strict loading for the approved 3D U-Net."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn

from cerebrachain_ml.architecture import MODEL_PARAMETER_COUNT, build_model, parameter_count
from cerebrachain_ml.errors import CheckpointIntegrityError, ModelLoadError

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CheckpointInfo:
    """Verified immutable metadata for a checkpoint file."""

    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class LoadedModel:
    """A strict-loaded model and the verified checkpoint metadata."""

    model: nn.Module
    checkpoint: CheckpointInfo


def sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest without reading a model file into memory at once."""

    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checkpoint(path: Path, expected_sha256: str) -> CheckpointInfo:
    """Verify that a configured checkpoint exists and matches its expected digest."""

    normalized_hash = expected_sha256.lower()
    if not _SHA256_PATTERN.fullmatch(normalized_hash):
        raise CheckpointIntegrityError("Configured model SHA-256 is invalid.")
    if not path.is_file():
        raise CheckpointIntegrityError("Configured model checkpoint is unavailable.")

    actual_hash = sha256_file(path)
    if actual_hash != normalized_hash:
        raise CheckpointIntegrityError("Configured model checkpoint failed integrity verification.")

    return CheckpointInfo(sha256=actual_hash, size_bytes=path.stat().st_size)


def _extract_state_dict(payload: Any) -> dict[str, torch.Tensor]:
    if not isinstance(payload, dict):
        raise ModelLoadError("Model checkpoint does not contain a state dictionary.")

    state_dict = payload.get("model_state_dict", payload.get("state_dict", payload))
    if not isinstance(state_dict, dict):
        raise ModelLoadError("Model checkpoint contains an invalid state dictionary.")
    if not all(isinstance(key, str) and isinstance(value, torch.Tensor) for key, value in state_dict.items()):
        raise ModelLoadError("Model checkpoint state dictionary contains invalid tensors.")

    return state_dict


def load_verified_model(
    checkpoint_path: Path,
    expected_sha256: str,
    *,
    device: str = "cpu",
) -> LoadedModel:
    """Verify checkpoint bytes and strictly load them into the original MONAI U-Net."""

    checkpoint = verify_checkpoint(checkpoint_path, expected_sha256)
    try:
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ModelLoadError("Model checkpoint could not be safely read.") from exc

    state_dict = _extract_state_dict(payload)
    model = build_model()
    try:
        model.load_state_dict(state_dict, strict=True)
    except RuntimeError as exc:
        raise ModelLoadError("Model checkpoint is incompatible with the MONAI 3D U-Net.") from exc

    if parameter_count(model) != MODEL_PARAMETER_COUNT:
        raise ModelLoadError("Loaded model has an unexpected parameter count.")

    model = model.to(device)
    model.eval()
    return LoadedModel(model=model, checkpoint=checkpoint)
