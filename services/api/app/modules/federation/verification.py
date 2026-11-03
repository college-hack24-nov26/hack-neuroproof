"""Proof contracts for real Groth16 verification with a fail-closed fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol
from uuid import UUID

from app.modules.federation.types import ProofVerificationStatus


@dataclass(frozen=True)
class Groth16VerificationRequest:
    """Server-derived bindings and in-memory update state for one proof envelope."""

    training_round_identifier: str
    model_version_commitment: str
    hospital_update_commitment: str
    proof_artifact_reference: str
    hospital_id: UUID
    artifact_sha256: str
    state_dict: Mapping[str, object]
    proof_envelope: "Groth16ProofEnvelope"


@dataclass(frozen=True)
class Groth16ChunkProof:
    """One public Groth16 proof and its public signals; no witness is retained."""

    proof: dict[str, object]
    public_signals: tuple[str, ...]


@dataclass(frozen=True)
class Groth16ProofEnvelope:
    """Circuit-pinned collection of chunk proofs for one protected update artifact."""

    circuit_version: str
    verification_key_id: str
    proofs: tuple[Groth16ChunkProof, ...]

    def to_record(self) -> dict[str, object]:
        """Serialize public proof material for protected server-side storage only."""

        return {
            "circuit_version": self.circuit_version,
            "verification_key_id": self.verification_key_id,
            "proofs": [
                {
                    "proof": item.proof,
                    "public_signals": list(item.public_signals),
                }
                for item in self.proofs
            ],
        }


@dataclass(frozen=True)
class Groth16VerificationResult:
    """Observed verifier outcome without exposing witnesses or proof contents."""

    status: ProofVerificationStatus
    reason: str | None = None
    circuit_version: str | None = None
    verification_key_id: str | None = None
    coverage_complete: bool = False
    aggregation_eligible: bool = False


class Groth16Verifier(Protocol):
    """Interface implemented only by a reviewed verifier with pinned public inputs."""

    @property
    def is_ready(self) -> bool:
        """Whether this verifier is approved for production aggregation."""

    @property
    def is_available(self) -> bool:
        """Whether a pinned cryptographic verifier is configured and usable."""

    def verify(self, request: Groth16VerificationRequest) -> Groth16VerificationResult:
        """Verify one proof against the provided round and commitment bindings."""


class UnavailableGroth16Verifier:
    """Phase 1 implementation: deliberately never claims a proof is verified."""

    @property
    def is_ready(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        return False

    def verify(self, request: Groth16VerificationRequest) -> Groth16VerificationResult:
        del request
        return Groth16VerificationResult(
            status=ProofVerificationStatus.PENDING_VERIFICATION,
            reason="A reviewed Groth16 verifier is not configured.",
        )
