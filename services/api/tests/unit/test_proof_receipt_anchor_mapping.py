"""Synthetic, non-persistent tests for V2 proof-receipt anchoring eligibility."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.trust.proof_receipt_anchor import (
    ChainReceiptLookupState,
    ProofReceiptAnchorReadConfig,
    ReceiptAnchorEligibilityError,
    build_proof_receipt_anchor_payload,
    derive_round_commitment,
)


def _verified_components() -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    round_id = uuid4()
    model_id = uuid4()
    federation_round = SimpleNamespace(id=round_id)
    model_version = SimpleNamespace(id=model_id, model_commitment="a" * 64)
    artifact = SimpleNamespace(
        federation_round_id=round_id,
        model_version_id=model_id,
        status="accepted",
        proof_verification_status="verified",
        zk_coverage_complete=True,
        aggregation_eligible=True,
        cryptographically_verified_at=datetime.now(UTC),
        update_commitment="b" * 64,
        proof_artifact_sha256="c" * 64,
        zk_verification_key_id="d" * 64,
    )
    return federation_round, model_version, artifact


def test_verified_complete_production_receipt_maps_to_v2_anchor_arguments() -> None:
    federation_round, model_version, artifact = _verified_components()

    payload = build_proof_receipt_anchor_payload(
        federation_round=federation_round,
        model_version=model_version,
        artifact=artifact,
    )

    assert payload.federation_round_commitment == derive_round_commitment(federation_round.id)
    assert payload.model_version_commitment == "0x" + "a" * 64
    assert payload.hospital_update_commitment == "0x" + "b" * 64
    assert payload.proof_artifact_sha256 == "0x" + "c" * 64
    assert payload.verification_key_id == "0x" + "d" * 64
    assert set(payload.as_contract_args()) == {
        "federationRoundCommitment",
        "modelVersionCommitment",
        "hospitalUpdateCommitment",
        "proofArtifactSha256",
        "verificationKeyId",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("proof_verification_status", "pending_verification"),
        ("zk_coverage_complete", False),
        ("aggregation_eligible", False),
        ("status", "submitted"),
        ("cryptographically_verified_at", None),
    ],
)
def test_unverified_or_incomplete_receipts_are_not_anchor_eligible(field: str, value: object) -> None:
    federation_round, model_version, artifact = _verified_components()
    setattr(artifact, field, value)

    with pytest.raises(ReceiptAnchorEligibilityError):
        build_proof_receipt_anchor_payload(
            federation_round=federation_round,
            model_version=model_version,
            artifact=artifact,
        )


def test_read_only_chain_configuration_requires_pinned_deployment_values() -> None:
    configuration = ProofReceiptAnchorReadConfig(
        rpc_url="http://127.0.0.1:18545",
        expected_chain_id=31337,
        contract_address="0x" + "1" * 40,
        expected_runtime_code_sha256="e" * 64,
    )

    assert configuration.expected_chain_id == 31337
    assert ChainReceiptLookupState.CONFIRMED.value == "confirmed"

    with pytest.raises(ValueError):
        ProofReceiptAnchorReadConfig(
            rpc_url="ftp://untrusted",
            expected_chain_id=0,
            contract_address="not-an-address",
            expected_runtime_code_sha256="not-a-hash",
        )
