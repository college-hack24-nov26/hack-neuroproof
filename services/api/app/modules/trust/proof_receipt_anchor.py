"""Pure validation and read-only integration contracts for V2 proof receipt anchoring.

This module never sends a chain transaction. It prepares only receipts that
have already satisfied the coordinator's strict production eligibility policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import re
from typing import Protocol
from uuid import UUID

from app.models.federation import (
    FederationModelVersion,
    FederationRound,
    FederationUpdateArtifact,
)
from app.modules.federation.types import ProofVerificationStatus, UpdateArtifactStatus

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ROUND_DOMAIN = b"cerebrachain-v2:proof-receipt-anchor:round:v1:"


class ReceiptAnchorEligibilityError(ValueError):
    """Raised when a coordinator receipt must never be sent for anchoring."""


def _as_bytes32_hex(value: str | None, field: str) -> str:
    if value is None or not _SHA256_PATTERN.fullmatch(value.lower()):
        raise ReceiptAnchorEligibilityError(f"{field} must be a 64-character SHA-256 hex digest.")
    return f"0x{value.lower()}"


@dataclass(frozen=True)
class ProofReceiptAnchorPayload:
    """ABI-ready fixed-size commitments for ``NeuroProofReceiptAnchor.anchorReceipt``."""

    federation_round_commitment: str
    model_version_commitment: str
    hospital_update_commitment: str
    proof_artifact_sha256: str
    verification_key_id: str

    def as_contract_args(self) -> dict[str, str]:
        """Return ABI struct keys without exposing a transaction-sending capability."""

        return {
            "federationRoundCommitment": self.federation_round_commitment,
            "modelVersionCommitment": self.model_version_commitment,
            "hospitalUpdateCommitment": self.hospital_update_commitment,
            "proofArtifactSha256": self.proof_artifact_sha256,
            "verificationKeyId": self.verification_key_id,
        }


def build_proof_receipt_anchor_payload(
    *,
    federation_round: FederationRound,
    model_version: FederationModelVersion,
    artifact: FederationUpdateArtifact,
) -> ProofReceiptAnchorPayload:
    """Map only a complete, production-eligible verified receipt to fixed-size commitments.

    Development-only verifier results remain ineligible by design, even when a
    synthetic proof verifies. The Solidity contract then derives the receipt ID
    itself from this exact commitment tuple.
    """

    if artifact.federation_round_id != federation_round.id:
        raise ReceiptAnchorEligibilityError("Artifact does not belong to the supplied federation round.")
    if artifact.model_version_id != model_version.id:
        raise ReceiptAnchorEligibilityError("Artifact does not belong to the supplied model version.")
    if artifact.status != UpdateArtifactStatus.ACCEPTED.value:
        raise ReceiptAnchorEligibilityError("Only accepted artifacts may be anchored.")
    if artifact.proof_verification_status != ProofVerificationStatus.VERIFIED.value:
        raise ReceiptAnchorEligibilityError("Only cryptographically verified proof receipts may be anchored.")
    if not artifact.zk_coverage_complete:
        raise ReceiptAnchorEligibilityError("Incomplete proof coverage may not be anchored.")
    if not artifact.aggregation_eligible:
        raise ReceiptAnchorEligibilityError("Production-ineligible proof receipts may not be anchored.")
    if artifact.cryptographically_verified_at is None:
        raise ReceiptAnchorEligibilityError("Verified receipt timestamp is required for anchoring.")

    round_commitment = sha256(_ROUND_DOMAIN + str(federation_round.id).encode("ascii")).hexdigest()
    return ProofReceiptAnchorPayload(
        federation_round_commitment=_as_bytes32_hex(round_commitment, "federation round commitment"),
        model_version_commitment=_as_bytes32_hex(model_version.model_commitment, "model version commitment"),
        hospital_update_commitment=_as_bytes32_hex(artifact.update_commitment, "hospital update commitment"),
        proof_artifact_sha256=_as_bytes32_hex(artifact.proof_artifact_sha256, "proof artifact SHA-256"),
        verification_key_id=_as_bytes32_hex(artifact.zk_verification_key_id, "verification key identifier"),
    )


class ChainReceiptLookupState(StrEnum):
    """Explicit read-only chain reconciliation outcomes; no result is inferred."""

    UNCONFIGURED = "unconfigured"
    UNAVAILABLE = "unavailable"
    CHAIN_ID_MISMATCH = "chain_id_mismatch"
    CONTRACT_CODE_MISSING = "contract_code_missing"
    CONTRACT_RUNTIME_MISMATCH = "contract_runtime_mismatch"
    INVALID_RECEIPT_ID = "invalid_receipt_id"
    INVALID_TRANSACTION_HASH = "invalid_transaction_hash"
    RECEIPT_MISMATCH = "receipt_mismatch"
    RECEIPT_MISSING = "receipt_missing"
    RECEIPT_FOUND = "receipt_found"
    TRANSACTION_MISSING = "transaction_missing"
    TRANSACTION_PENDING = "transaction_pending"
    EVENT_MISMATCH = "event_mismatch"
    MALFORMED_RPC_RESPONSE = "malformed_rpc_response"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class ProofReceiptAnchorReadConfig:
    """Pinned read-only chain configuration; transaction credentials are deliberately absent."""

    rpc_url: str
    expected_chain_id: int
    contract_address: str
    expected_runtime_code_sha256: str
    required_confirmations: int = 1

    def __post_init__(self) -> None:
        if not self.rpc_url.startswith(("http://", "https://")):
            raise ValueError("rpc_url must use HTTP(S).")
        if self.expected_chain_id <= 0:
            raise ValueError("expected_chain_id must be positive.")
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", self.contract_address):
            raise ValueError("contract_address must be a 20-byte hexadecimal address.")
        if not _SHA256_PATTERN.fullmatch(self.expected_runtime_code_sha256.lower()):
            raise ValueError("expected_runtime_code_sha256 must be a SHA-256 digest.")
        if self.required_confirmations <= 0:
            raise ValueError("required_confirmations must be positive.")


@dataclass(frozen=True)
class AnchoredReceiptView:
    """Read-only receipt metadata after a chain deployment is independently pinned."""

    receipt_id: str
    payload: ProofReceiptAnchorPayload
    attested_by: str
    anchored_at: int
    anchored_block: int


class ProofReceiptAnchorReader(Protocol):
    """Future read-only adapter boundary. It cannot submit transactions."""

    def lookup(
        self,
        *,
        configuration: ProofReceiptAnchorReadConfig,
        receipt_id: str,
    ) -> tuple[ChainReceiptLookupState, AnchoredReceiptView | None]:
        """Return an explicit chain state after validating chain ID and runtime code hash."""


def derive_round_commitment(round_id: UUID) -> str:
    """Return the documented bytes32 round commitment used by the V2 anchor."""

    return f"0x{sha256(_ROUND_DOMAIN + str(round_id).encode('ascii')).hexdigest()}"
