"""Deterministic, validated weighted FedAvg for in-memory PyTorch state dicts."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

import torch

from app.modules.federation.verification import Groth16ProofEnvelope


class FedAvgValidationError(ValueError):
    """A model update cannot safely participate in aggregation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelUpdate:
    """An in-memory full-model update from one explicitly enrolled hospital.

    This object is deliberately not an API schema.  Private tensor payloads must
    arrive through a future authenticated coordinator transport, not a browser
    JSON request or PostgreSQL row.
    """

    hospital_id: UUID
    training_node_id: UUID
    sample_count: int
    state_dict: Mapping[str, torch.Tensor]
    model_version_commitment: str
    hospital_update_commitment: str
    proof_artifact_reference: str | None = None
    artifact_sha256: str | None = None
    proof_envelope: Groth16ProofEnvelope | None = None


@dataclass(frozen=True)
class AggregationResult:
    """The deterministic output of one weighted FedAvg operation."""

    state_dict: OrderedDict[str, torch.Tensor]
    total_sample_count: int
    participant_hospital_ids: tuple[UUID, ...]


_FLOATING_DTYPES = {
    torch.float16,
    torch.bfloat16,
    torch.float32,
    torch.float64,
}
_INVARIANT_DTYPES = {
    torch.bool,
    torch.uint8,
    torch.int8,
    torch.int16,
    torch.int32,
    torch.int64,
}


def state_dict_sha256(state_dict: Mapping[str, torch.Tensor]) -> str:
    """Create a deterministic SHA-256 commitment for a validated model state.

    The resulting digest is an integrity commitment only.  It is not a Groth16
    proof and must never be used as evidence of ZK verification.
    """

    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name]
        if not isinstance(tensor, torch.Tensor):
            raise FedAvgValidationError(
                "invalid_tensor",
                f"State entry '{name}' is not a PyTorch tensor.",
            )
        value = tensor.detach().to(device="cpu").contiguous()
        name_bytes = name.encode("utf-8")
        dtype_bytes = str(value.dtype).encode("ascii")
        shape_bytes = ",".join(str(dimension) for dimension in value.shape).encode("ascii")
        for part in (name_bytes, dtype_bytes, shape_bytes):
            digest.update(len(part).to_bytes(4, "big"))
            digest.update(part)
        raw = value.reshape(-1).view(torch.uint8).numpy().tobytes()
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


class FedAvgAggregator:
    """Aggregate compatible full-model state dicts using sample weighting.

    Floating tensors are accumulated in CPU float64 in stable hospital UUID
    order, then restored to their original dtype.  Integral and boolean state
    entries (for example BatchNorm counters) are copied only when every client
    supplied exactly the same value; averaging them would silently corrupt their
    meaning.
    """

    algorithm = "weighted_fedavg_v1"

    def aggregate(self, updates: Sequence[ModelUpdate]) -> AggregationResult:
        """Validate and aggregate updates, failing with a precise stable code."""

        if not updates:
            raise FedAvgValidationError("no_updates", "At least one model update is required.")

        ordered_updates = tuple(sorted(updates, key=lambda update: str(update.hospital_id)))
        self._validate_unique_hospitals(ordered_updates)
        reference = ordered_updates[0]
        reference_names = set(reference.state_dict)
        if not reference_names:
            raise FedAvgValidationError("empty_state_dict", "Model updates must include parameters.")

        total_samples = 0
        for update in ordered_updates:
            self._validate_sample_count(update.sample_count)
            self._validate_state_schema(reference, update, reference_names)
            total_samples += update.sample_count

        aggregated: OrderedDict[str, torch.Tensor] = OrderedDict()
        for name in sorted(reference_names):
            tensors = [update.state_dict[name] for update in ordered_updates]
            aggregated[name] = self._aggregate_tensor(name, tensors, ordered_updates, total_samples)

        return AggregationResult(
            state_dict=aggregated,
            total_sample_count=total_samples,
            participant_hospital_ids=tuple(update.hospital_id for update in ordered_updates),
        )

    @staticmethod
    def _validate_unique_hospitals(updates: Sequence[ModelUpdate]) -> None:
        hospital_ids = [update.hospital_id for update in updates]
        if len(set(hospital_ids)) != len(hospital_ids):
            raise FedAvgValidationError(
                "duplicate_hospital_update",
                "A hospital may submit only one update per round.",
            )

    @staticmethod
    def _validate_sample_count(sample_count: int) -> None:
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
            raise FedAvgValidationError(
                "invalid_sample_count",
                "Model update sample_count must be a positive integer.",
            )

    def _validate_state_schema(
        self,
        reference: ModelUpdate,
        update: ModelUpdate,
        reference_names: set[str],
    ) -> None:
        if set(update.state_dict) != reference_names:
            raise FedAvgValidationError(
                "parameter_name_mismatch",
                "Model update parameter names do not match the round model.",
            )

        for name in sorted(reference_names):
            expected = reference.state_dict[name]
            received = update.state_dict[name]
            if not isinstance(received, torch.Tensor):
                raise FedAvgValidationError(
                    "invalid_tensor",
                    f"State entry '{name}' is not a PyTorch tensor.",
                )
            if expected.shape != received.shape:
                raise FedAvgValidationError(
                    "parameter_shape_mismatch",
                    f"State entry '{name}' has an incompatible tensor shape.",
                )
            if expected.dtype != received.dtype:
                raise FedAvgValidationError(
                    "parameter_dtype_mismatch",
                    f"State entry '{name}' has an incompatible tensor dtype.",
                )
            self._validate_tensor(name, received)

    @staticmethod
    def _validate_tensor(name: str, tensor: torch.Tensor) -> None:
        if tensor.layout != torch.strided:
            raise FedAvgValidationError(
                "unsupported_tensor_layout",
                f"State entry '{name}' must use a strided tensor layout.",
            )
        if tensor.dtype not in _FLOATING_DTYPES | _INVARIANT_DTYPES:
            raise FedAvgValidationError(
                "unsupported_tensor_dtype",
                f"State entry '{name}' uses unsupported dtype {tensor.dtype}.",
            )
        if tensor.dtype in _FLOATING_DTYPES and not bool(torch.isfinite(tensor).all().item()):
            raise FedAvgValidationError(
                "non_finite_tensor",
                f"State entry '{name}' contains NaN or infinity.",
            )

    def _aggregate_tensor(
        self,
        name: str,
        tensors: Sequence[torch.Tensor],
        updates: Sequence[ModelUpdate],
        total_samples: int,
    ) -> torch.Tensor:
        reference = tensors[0]
        if reference.dtype in _INVARIANT_DTYPES:
            reference_value = reference.detach().to(device="cpu").clone()
            if any(not torch.equal(reference_value, tensor.detach().to(device="cpu")) for tensor in tensors[1:]):
                raise FedAvgValidationError(
                    "invariant_tensor_mismatch",
                    f"Non-floating state entry '{name}' differs between updates.",
                )
            return reference_value

        accumulator = torch.zeros_like(reference, dtype=torch.float64, device="cpu")
        for update, tensor in zip(updates, tensors, strict=True):
            accumulator.add_(
                tensor.detach().to(device="cpu", dtype=torch.float64),
                alpha=update.sample_count / total_samples,
            )
        return accumulator.to(dtype=reference.dtype)
