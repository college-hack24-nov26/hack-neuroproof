"""Public-safe schemas for the V2 read-only proof receipt anchor API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class V2AnchorReceiptMetadataResponse(BaseModel):
    """Immutable on-chain commitments; no proof, model update, or patient data."""

    federation_round_commitment: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    model_version_commitment: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    hospital_update_commitment: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    proof_artifact_sha256: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    verification_key_id: str = Field(pattern=r"^0x[0-9a-f]{64}$")
    attestation_status: Literal["offchain_groth16_verified"]
    anchored_at: int = Field(ge=0)
    anchored_block: int = Field(ge=0)
    attested_by: str = Field(pattern=r"^0x[0-9a-f]{40}$")


class V2AnchorReceiptLookupResponse(BaseModel):
    """Explicit V2 chain-inspection state; this anchor never verifies Groth16 on-chain."""

    state: Literal[
        "unconfigured",
        "unavailable",
        "chain_id_mismatch",
        "contract_code_missing",
        "contract_runtime_mismatch",
        "invalid_receipt_id",
        "invalid_transaction_hash",
        "receipt_mismatch",
        "receipt_missing",
        "receipt_found",
        "transaction_missing",
        "transaction_pending",
        "event_mismatch",
        "malformed_rpc_response",
        "confirmed",
    ]
    detail: str = Field(max_length=256)
    rpc_available: bool
    chain_id: int | None = Field(default=None, ge=0)
    contract_address: str | None = Field(default=None, pattern=r"^0x[0-9a-f]{40}$")
    runtime_bytecode_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    contract_identity_verified: bool
    receipt_id: str | None = Field(default=None, pattern=r"^0x[0-9a-f]{64}$")
    receipt: V2AnchorReceiptMetadataResponse | None = None
    transaction_hash: str | None = Field(default=None, pattern=r"^0x[0-9a-f]{64}$")
    transaction_block_number: int | None = Field(default=None, ge=0)
    confirmations: int | None = Field(default=None, ge=0)
    event_verified: bool
    offchain_groth16_verified: bool
    onchain_groth16_verified: Literal[False] = False
