"""Authorization coverage for the protected V2 read-only proof receipt route."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.v1 import dependencies, trust
from app.modules.trust.proof_receipt_anchor import ChainReceiptLookupState
from app.modules.trust.v2_anchor_rpc import V2AnchorReceiptInspection


API_PREFIX = "/api/v1/trust"
OPERATOR_EMAIL = "operator@example.test"
RECEIPT_READER_EMAIL = "receipt-reader@example.test"
RECEIPT_ID = "0x" + "a" * 64


def _principal(role, email):
    return SimpleNamespace(role=role, email=email, hospital_id=uuid4())


@pytest.fixture
def isolated_trust_api(monkeypatch):
    app = FastAPI()
    app.include_router(trust.router, prefix="/api/v1")
    state = {
        "principal": _principal(dependencies.HospitalRole.HOSPITAL_ADMIN, OPERATOR_EMAIL),
        "reader_emails": frozenset({RECEIPT_READER_EMAIL}),
        "lookup_state": ChainReceiptLookupState.RECEIPT_FOUND,
    }

    app.dependency_overrides[dependencies.get_current_principal] = lambda: state["principal"]
    app.dependency_overrides[dependencies.get_settings] = lambda: SimpleNamespace(
        federation_operator_emails=frozenset({OPERATOR_EMAIL}),
        proof_receipt_reader_emails=state["reader_emails"],
    )

    @app.exception_handler(dependencies.AuthorizationDeniedError)
    async def authorization_denied(request, exc):
        del request, exc
        return JSONResponse(status_code=403, content={"detail": "Access denied"})

    class FakeReader:
        def inspect_receipt(self, *, receipt_id, transaction_hash=None):
            lookup_state = state["lookup_state"]
            return V2AnchorReceiptInspection(
                state=lookup_state,
                detail="Synthetic read-only receipt result.",
                rpc_available=lookup_state is not ChainReceiptLookupState.UNAVAILABLE,
                chain_id=31337 if lookup_state is not ChainReceiptLookupState.UNAVAILABLE else None,
                contract_address="0x" + "1" * 40 if lookup_state is not ChainReceiptLookupState.UNAVAILABLE else None,
                runtime_bytecode_sha256="2" * 64 if lookup_state is not ChainReceiptLookupState.UNAVAILABLE else None,
                contract_identity_verified=lookup_state is not ChainReceiptLookupState.UNAVAILABLE,
                receipt_id=receipt_id.lower(),
                transaction_hash=transaction_hash,
            )

    monkeypatch.setattr(trust, "build_v2_anchor_reader", lambda settings: FakeReader())

    with TestClient(app) as client:
        yield client, state


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (dependencies.HospitalRole.DOCTOR, RECEIPT_READER_EMAIL),
        (dependencies.HospitalRole.HOSPITAL_ADMIN, "other-admin@example.test"),
    ],
)
def test_only_hospital_admin_receipt_readers_can_read_v2_anchor_receipts(isolated_trust_api, role, email) -> None:
    client, state = isolated_trust_api
    state["principal"] = _principal(role, email)

    response = client.get(f"{API_PREFIX}/v2/receipts/{RECEIPT_ID}")

    assert response.status_code == 403


def test_existing_operator_retains_receipt_lookup_access(isolated_trust_api) -> None:
    client, _ = isolated_trust_api

    response = client.get(f"{API_PREFIX}/v2/receipts/{RECEIPT_ID}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state"] == "receipt_found"
    assert payload["receipt"] is None
    assert payload["onchain_groth16_verified"] is False


def test_receipt_reader_lookup_is_read_only_and_typed(isolated_trust_api) -> None:
    client, state = isolated_trust_api
    state["principal"] = _principal(
        dependencies.HospitalRole.HOSPITAL_ADMIN,
        RECEIPT_READER_EMAIL.upper(),
    )

    response = client.get(f"{API_PREFIX}/v2/receipts/{RECEIPT_ID}")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "receipt_found"


def test_empty_receipt_reader_allowlist_fails_closed(isolated_trust_api) -> None:
    client, state = isolated_trust_api
    state["principal"] = _principal(
        dependencies.HospitalRole.HOSPITAL_ADMIN,
        RECEIPT_READER_EMAIL,
    )
    state["reader_emails"] = frozenset()

    response = client.get(f"{API_PREFIX}/v2/receipts/{RECEIPT_ID}")

    assert response.status_code == 403


def test_invalid_receipt_identifier_is_reported_without_calling_chain_reader(isolated_trust_api) -> None:
    client, state = isolated_trust_api
    state["principal"] = _principal(
        dependencies.HospitalRole.HOSPITAL_ADMIN,
        RECEIPT_READER_EMAIL,
    )

    response = client.get(f"{API_PREFIX}/v2/receipts/not-a-receipt")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "invalid_receipt_id"


def test_rpc_unavailable_is_a_safe_read_only_response(isolated_trust_api) -> None:
    client, state = isolated_trust_api
    state["principal"] = _principal(
        dependencies.HospitalRole.HOSPITAL_ADMIN,
        RECEIPT_READER_EMAIL,
    )
    state["lookup_state"] = ChainReceiptLookupState.UNAVAILABLE

    response = client.get(f"{API_PREFIX}/v2/receipts/{RECEIPT_ID}")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "unavailable"
    assert response.json()["onchain_groth16_verified"] is False


def test_unauthenticated_receipt_lookup_returns_401() -> None:
    app = FastAPI()
    app.include_router(trust.router, prefix="/api/v1")
    app.dependency_overrides[dependencies.get_authentication_service] = lambda: object()

    @app.exception_handler(dependencies.AuthenticationRequiredError)
    async def authentication_required(request, exc):
        del request, exc
        return JSONResponse(status_code=401, content={"detail": "Authentication is required"})

    with TestClient(app) as client:
        response = client.get(f"{API_PREFIX}/v2/receipts/{RECEIPT_ID}")

    assert response.status_code == 401
