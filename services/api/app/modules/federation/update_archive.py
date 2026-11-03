"""Safe, bounded model-update archive format for hospital-local transport.

The format uses JSON plus NumPy ``.npy`` tensors inside a ZIP archive. It never
uses ``torch.load`` or pickle on a hospital-submitted artifact.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch

from app.modules.federation.fedavg import state_dict_sha256

ARCHIVE_FORMAT = "cerebrachain-model-update-v1"
MANIFEST_NAME = "manifest.json"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_REFERENCE_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,512}$")
_SUPPORTED_DTYPES = {
    torch.bool,
    torch.uint8,
    torch.int8,
    torch.int16,
    torch.int32,
    torch.int64,
    torch.float16,
    torch.bfloat16,
    torch.float32,
    torch.float64,
}
_ALLOWED_TRAINING_METADATA = {
    "training_executed",
    "local_epochs_completed",
    "training_seconds",
    "training_started_at",
    "training_completed_at",
    "final_loss",
    "base_checkpoint_sha256",
}


class UpdateArchiveError(ValueError):
    """A submitted update archive is invalid or unsafe to process."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParameterSpec:
    """Public tensor schema metadata; it contains no parameter values."""

    name: str
    shape: tuple[int, ...]
    dtype: str

    def to_record(self) -> dict[str, object]:
        return {"name": self.name, "shape": list(self.shape), "dtype": self.dtype}


@dataclass(frozen=True)
class ParsedModelUpdateArchive:
    """Validated archive contents retained only in coordinator process memory."""

    state_dict: OrderedDict[str, torch.Tensor]
    model_version_commitment: str
    update_commitment: str
    parameter_schema_commitment: str
    sample_count: int
    proof_artifact_reference: str | None
    training_metadata: dict[str, object] | None
    artifact_sha256: str
    artifact_size_bytes: int


def parameter_schema_from_state_dict(
    state_dict: Mapping[str, torch.Tensor],
) -> tuple[ParameterSpec, ...]:
    """Return a stable public schema after validating tensor safety basics."""

    if not state_dict:
        raise UpdateArchiveError("empty_state_dict", "Model update must include at least one tensor.")
    result: list[ParameterSpec] = []
    for name in sorted(state_dict):
        tensor = state_dict[name]
        if not isinstance(name, str) or not name or len(name) > 512:
            raise UpdateArchiveError("invalid_parameter_name", "Model update contains an invalid parameter name.")
        if not isinstance(tensor, torch.Tensor) or tensor.layout != torch.strided:
            raise UpdateArchiveError("invalid_tensor", f"State entry '{name}' is not a supported tensor.")
        if tensor.dtype not in _SUPPORTED_DTYPES:
            raise UpdateArchiveError("unsupported_tensor_dtype", f"State entry '{name}' has an unsupported dtype.")
        if tensor.dtype.is_floating_point and not bool(torch.isfinite(tensor).all().item()):
            raise UpdateArchiveError("non_finite_tensor", f"State entry '{name}' contains NaN or infinity.")
        result.append(
            ParameterSpec(
                name=name,
                shape=tuple(int(dimension) for dimension in tensor.shape),
                dtype=str(tensor.dtype),
            )
        )
    return tuple(result)


def parameter_schema_commitment(schema: tuple[ParameterSpec, ...]) -> str:
    """Hash a canonical schema record; this is not a Groth16 proof."""

    payload = json.dumps(
        [item.to_record() for item in schema],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_parameter_schema(records: object) -> tuple[ParameterSpec, ...]:
    """Validate persisted/API schema records before trusting an update archive."""

    if not isinstance(records, list) or not records:
        raise UpdateArchiveError("parameter_schema_missing", "Model version has no usable parameter schema.")
    specs: list[ParameterSpec] = []
    for item in records:
        if not isinstance(item, dict):
            raise UpdateArchiveError("parameter_schema_invalid", "Model parameter schema is invalid.")
        name = item.get("name")
        shape = item.get("shape")
        dtype = item.get("dtype")
        if (
            not isinstance(name, str)
            or not name
            or len(name) > 512
            or not isinstance(shape, list)
            or len(shape) > 8
            or not all(isinstance(value, int) and value >= 0 for value in shape)
            or not isinstance(dtype, str)
        ):
            raise UpdateArchiveError("parameter_schema_invalid", "Model parameter schema is invalid.")
        specs.append(ParameterSpec(name=name, shape=tuple(shape), dtype=dtype))
    if len({item.name for item in specs}) != len(specs):
        raise UpdateArchiveError("parameter_schema_invalid", "Model parameter schema has duplicate names.")
    ordered = tuple(sorted(specs, key=lambda item: item.name))
    _validate_schema_dtypes(ordered)
    return ordered


def build_model_update_archive(
    *,
    state_dict: Mapping[str, torch.Tensor],
    model_version_commitment: str,
    sample_count: int,
    proof_artifact_reference: str | None = None,
    training_metadata: Mapping[str, object] | None = None,
) -> bytes:
    """Create a safe archive from an already-authorized local training result.

    This serializer does not train a model. Callers must obtain an explicit
    authorization before passing a locally trained state dictionary here.
    """

    schema = parameter_schema_from_state_dict(state_dict)
    if not _is_sha256(model_version_commitment):
        raise UpdateArchiveError("invalid_model_commitment", "Model version commitment is invalid.")
    _validate_sample_count(sample_count)
    _validate_proof_reference(proof_artifact_reference)
    normalized_metadata = _normalize_training_metadata(training_metadata)
    ordered_state = OrderedDict((name, state_dict[name]) for name in sorted(state_dict))
    manifest: dict[str, object] = {
        "format": ARCHIVE_FORMAT,
        "model_version_commitment": model_version_commitment.lower(),
        "update_commitment": state_dict_sha256(ordered_state),
        "parameter_schema_commitment": parameter_schema_commitment(schema),
        "sample_count": sample_count,
        "tensors": [
            {"name": item.name, "path": f"tensors/{index:04d}.npy"}
            for index, item in enumerate(schema)
        ],
    }
    if proof_artifact_reference is not None:
        manifest["proof_artifact_reference"] = proof_artifact_reference
    if normalized_metadata is not None:
        manifest["training_metadata"] = normalized_metadata

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, sort_keys=True, separators=(",", ":")))
        for index, item in enumerate(schema):
            tensor = ordered_state[item.name].detach().to(device="cpu").contiguous()
            try:
                # NumPy does not represent torch.bfloat16. Preserve its exact
                # bit pattern as uint16 rather than silently casting it.
                value = (
                    tensor.view(torch.uint16).numpy()
                    if tensor.dtype is torch.bfloat16
                    else tensor.numpy()
                )
            except TypeError as exc:
                raise UpdateArchiveError(
                    "unsupported_tensor_dtype",
                    f"State entry '{item.name}' cannot be represented in a safe archive.",
                ) from exc
            tensor_output = io.BytesIO()
            np.save(tensor_output, value, allow_pickle=False)
            archive.writestr(f"tensors/{index:04d}.npy", tensor_output.getvalue())
    return output.getvalue()


def parse_model_update_archive(
    data: bytes,
    *,
    expected_schema: tuple[ParameterSpec, ...],
    expected_schema_commitment: str,
    max_bytes: int,
) -> ParsedModelUpdateArchive:
    """Safely parse a bounded archive and verify its schema and commitments."""

    if not data or len(data) > max_bytes:
        raise UpdateArchiveError("artifact_size_invalid", "Update artifact exceeds the configured size limit.")
    if not _is_sha256(expected_schema_commitment):
        raise UpdateArchiveError("parameter_schema_missing", "Model version has no usable parameter schema.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _validate_zip_members(archive, max_bytes)
            manifest = _read_manifest(archive)
            entries = _manifest_entries(manifest, expected_schema)
            expected_files = {MANIFEST_NAME, *(entry["path"] for entry in entries)}
            if {info.filename for info in archive.infolist()} != expected_files:
                raise UpdateArchiveError("archive_members_invalid", "Update archive contains unexpected files.")
            state_dict = _read_tensors(archive, entries, expected_schema)
    except zipfile.BadZipFile as exc:
        raise UpdateArchiveError("archive_invalid", "Update artifact is not a valid archive.") from exc

    actual_schema = parameter_schema_from_state_dict(state_dict)
    actual_schema_commitment = parameter_schema_commitment(actual_schema)
    manifest_schema_commitment = _manifest_hash(manifest, "parameter_schema_commitment")
    if (
        actual_schema != expected_schema
        or actual_schema_commitment != expected_schema_commitment
        or manifest_schema_commitment != expected_schema_commitment
    ):
        raise UpdateArchiveError("parameter_schema_mismatch", "Update artifact does not match the approved model schema.")
    update_commitment = _manifest_hash(manifest, "update_commitment")
    if update_commitment != state_dict_sha256(state_dict):
        raise UpdateArchiveError("update_commitment_mismatch", "Update artifact commitment does not match its tensors.")
    model_version_commitment = _manifest_hash(manifest, "model_version_commitment")
    sample_count = manifest.get("sample_count")
    _validate_sample_count(sample_count)
    proof_reference = manifest.get("proof_artifact_reference")
    if proof_reference is not None and not isinstance(proof_reference, str):
        raise UpdateArchiveError("proof_reference_invalid", "Proof artifact reference is invalid.")
    _validate_proof_reference(proof_reference)
    metadata = _normalize_training_metadata(manifest.get("training_metadata"))
    if metadata is None:
        raise UpdateArchiveError(
            "training_metadata_missing",
            "Update artifact must include execution metadata from an authorized local run.",
        )
    return ParsedModelUpdateArchive(
        state_dict=state_dict,
        model_version_commitment=model_version_commitment,
        update_commitment=update_commitment,
        parameter_schema_commitment=expected_schema_commitment,
        sample_count=sample_count,
        proof_artifact_reference=proof_reference,
        training_metadata=metadata,
        artifact_sha256=hashlib.sha256(data).hexdigest(),
        artifact_size_bytes=len(data),
    )


def _validate_zip_members(archive: zipfile.ZipFile, max_bytes: int) -> None:
    members = archive.infolist()
    if not members or len(members) > 512:
        raise UpdateArchiveError("archive_members_invalid", "Update archive has an invalid number of files.")
    if len({member.filename for member in members}) != len(members):
        raise UpdateArchiveError("archive_members_invalid", "Update archive contains duplicate file names.")
    total_uncompressed = 0
    for member in members:
        if (
            member.is_dir()
            or member.flag_bits & 0x1
            or member.filename.startswith(("/", "\\"))
            or ".." in member.filename.split("/")
        ):
            raise UpdateArchiveError("archive_members_invalid", "Update archive contains an unsafe file path.")
        total_uncompressed += member.file_size
        if total_uncompressed > max_bytes:
            raise UpdateArchiveError("archive_expansion_invalid", "Update archive expands beyond the configured size limit.")


def _read_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        raw = archive.read(MANIFEST_NAME)
        if len(raw) > 128_000:
            raise UpdateArchiveError("manifest_invalid", "Update artifact manifest is too large.")
        manifest = json.loads(raw.decode("utf-8"))
    except KeyError as exc:
        raise UpdateArchiveError("manifest_missing", "Update artifact manifest is missing.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateArchiveError("manifest_invalid", "Update artifact manifest is invalid.") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT:
        raise UpdateArchiveError("manifest_invalid", "Update artifact format is not supported.")
    return manifest


def _manifest_entries(
    manifest: Mapping[str, object],
    expected_schema: tuple[ParameterSpec, ...],
) -> list[dict[str, str]]:
    raw_entries = manifest.get("tensors")
    if not isinstance(raw_entries, list) or len(raw_entries) != len(expected_schema):
        raise UpdateArchiveError("parameter_schema_mismatch", "Update artifact tensor list is invalid.")
    entries: list[dict[str, str]] = []
    for index, (entry, spec) in enumerate(zip(raw_entries, expected_schema, strict=True)):
        expected_path = f"tensors/{index:04d}.npy"
        if (
            not isinstance(entry, dict)
            or entry.get("name") != spec.name
            or entry.get("path") != expected_path
        ):
            raise UpdateArchiveError("parameter_schema_mismatch", "Update artifact tensor list is invalid.")
        entries.append({"name": spec.name, "path": expected_path})
    return entries


def _read_tensors(
    archive: zipfile.ZipFile,
    entries: list[dict[str, str]],
    expected_schema: tuple[ParameterSpec, ...],
) -> OrderedDict[str, torch.Tensor]:
    result: OrderedDict[str, torch.Tensor] = OrderedDict()
    for entry, spec in zip(entries, expected_schema, strict=True):
        try:
            array = np.load(io.BytesIO(archive.read(entry["path"])), allow_pickle=False)
        except (EOFError, OSError, ValueError) as exc:
            raise UpdateArchiveError("tensor_invalid", "Update artifact contains an invalid tensor.") from exc
        if not isinstance(array, np.ndarray) or array.dtype.hasobject:
            raise UpdateArchiveError("tensor_invalid", "Update artifact contains an invalid tensor.")
        try:
            copied = array.copy(order="C")
            if spec.dtype == str(torch.bfloat16):
                if copied.dtype != np.uint16:
                    raise ValueError("bfloat16 must be represented as uint16 bits")
                tensor = torch.from_numpy(copied).view(torch.bfloat16)
            else:
                tensor = torch.from_numpy(copied)
        except (TypeError, ValueError) as exc:
            raise UpdateArchiveError("tensor_invalid", "Update artifact contains an unsupported tensor.") from exc
        actual = ParameterSpec(
            name=spec.name,
            shape=tuple(int(value) for value in tensor.shape),
            dtype=str(tensor.dtype),
        )
        if actual != spec:
            raise UpdateArchiveError("parameter_schema_mismatch", "Update artifact does not match the approved model schema.")
        result[spec.name] = tensor
    return result


def _manifest_hash(manifest: Mapping[str, object], name: str) -> str:
    value = manifest.get(name)
    if not isinstance(value, str) or not _is_sha256(value):
        raise UpdateArchiveError("manifest_invalid", f"Update artifact {name} is invalid.")
    return value.lower()


def _validate_schema_dtypes(schema: tuple[ParameterSpec, ...]) -> None:
    supported = {str(dtype) for dtype in _SUPPORTED_DTYPES}
    if any(item.dtype not in supported for item in schema):
        raise UpdateArchiveError("parameter_schema_invalid", "Model parameter schema contains an unsupported dtype.")


def _validate_sample_count(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise UpdateArchiveError("invalid_sample_count", "Update sample count must be a positive integer.")


def _validate_proof_reference(value: str | None) -> None:
    if value is not None and (not _SAFE_REFERENCE_RE.fullmatch(value) or value.startswith("/") or ".." in value):
        raise UpdateArchiveError("proof_reference_invalid", "Proof artifact reference is invalid.")


def _normalize_training_metadata(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - _ALLOWED_TRAINING_METADATA:
        raise UpdateArchiveError("training_metadata_invalid", "Training metadata is invalid.")
    if value.get("training_executed") is not True:
        raise UpdateArchiveError("training_metadata_invalid", "Training metadata must confirm actual execution.")
    epochs = value.get("local_epochs_completed")
    seconds = value.get("training_seconds")
    if isinstance(epochs, bool) or not isinstance(epochs, int) or epochs <= 0:
        raise UpdateArchiveError("training_metadata_invalid", "Training metadata is invalid.")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        raise UpdateArchiveError("training_metadata_invalid", "Training metadata is invalid.")
    normalized: dict[str, object] = {
        "training_executed": True,
        "local_epochs_completed": epochs,
        "training_seconds": float(seconds),
    }
    for key in ("training_started_at", "training_completed_at"):
        item = value.get(key)
        if item is not None:
            if not isinstance(item, str) or len(item) > 64:
                raise UpdateArchiveError("training_metadata_invalid", "Training metadata is invalid.")
            normalized[key] = item
    loss = value.get("final_loss")
    if loss is not None:
        if isinstance(loss, bool) or not isinstance(loss, (int, float)) or not math.isfinite(loss):
            raise UpdateArchiveError("training_metadata_invalid", "Training metadata is invalid.")
        normalized["final_loss"] = float(loss)
    checkpoint_sha = value.get("base_checkpoint_sha256")
    if checkpoint_sha is not None:
        if not isinstance(checkpoint_sha, str) or not _is_sha256(checkpoint_sha):
            raise UpdateArchiveError("training_metadata_invalid", "Training metadata is invalid.")
        normalized["base_checkpoint_sha256"] = checkpoint_sha.lower()
    return normalized


def _is_sha256(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value.lower()))
