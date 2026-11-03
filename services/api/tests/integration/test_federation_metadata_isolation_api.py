"""Real JWT + PostgreSQL federation metadata isolation regression.

Uses synthetic hospital identities, model schema and prepared updates.
No patient MRI, model training, or production database access.
"""

from __future__ import annotations

import hashlib
import json
import os

from collections import OrderedDict
from pathlib import Path
from uuid import uuid4

import pytest
import torch

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

from app.modules.federation.training_agent import (
    AUTHORIZED_CASE_BY_HOSPITAL_SLUG,
)

from app.modules.federation.update_archive import (
    parameter_schema_from_state_dict,
)


API = "/api/v1/federation"


@pytest.fixture
def isolated_client(
    postgres_test_database_url: str,
    tmp_path: Path,
):
    """Use explicitly selected test PostgreSQL, never the dev database."""

    previous_url = os.environ.get(
        "CEREBRACHAIN_DATABASE_URL"
    )

    operator_email = (
        f"metadata-operator-{uuid4().hex}@example.test"
    )

    os.environ["CEREBRACHAIN_DATABASE_URL"] = (
        postgres_test_database_url
    )

    try:
        api_root = Path(__file__).parents[2]
        config = Config(str(api_root / "alembic.ini"))

        command.upgrade(config, "head")

        storage = tmp_path / "protected-updates"
        storage.mkdir(mode=0o700)

        settings = Settings(
            model_checkpoint_path=None,
            model_sha256=None,
            result_storage_dir=None,
            database_url=postgres_test_database_url,
            jwt_secret="x" * 32,
            jwt_issuer="metadata-isolation-integration-test",
            federation_operator_emails=frozenset(
                {operator_email}
            ),
            federation_update_storage_dir=storage,
        )

        with TestClient(create_app(settings)) as client:
            yield client, operator_email

    finally:
        if previous_url is None:
            os.environ.pop(
                "CEREBRACHAIN_DATABASE_URL",
                None,
            )
        else:
            os.environ[
                "CEREBRACHAIN_DATABASE_URL"
            ] = previous_url


def register(
    client: TestClient,
    *,
    name: str,
    email: str,
) -> dict:
    response = client.post(
        "/api/v1/auth/hospitals/register",
        json={
            "hospital_name": name,
            "administrator_name": "Synthetic Administrator",
            "email": email,
            "password": "synthetic-test-password",
        },
    )

    assert response.status_code == 201, response.text

    result = response.json()

    assert result.get("access_token")
    assert isinstance(result.get("actor"), dict)
    assert result["actor"].get("hospital_id")

    return result


def headers(identity: dict) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {identity['access_token']}"
        )
    }


def post_success(
    client: TestClient,
    path: str,
    *,
    identity: dict,
    payload: dict | None = None,
    expected_status: int = 201,
) -> dict:
    response = client.post(
        path,
        headers=headers(identity),
        json=payload,
    )

    assert response.status_code == expected_status, (
        f"{path}: {response.status_code} {response.text}"
    )

    return response.json()


def get_success(
    client: TestClient,
    path: str,
    identity: dict,
):
    response = client.get(
        API + path,
        headers=headers(identity),
    )

    assert response.status_code == 200, (
        f"{path}: {response.status_code} {response.text}"
    )

    return response.json()


def test_real_jwt_postgres_metadata_isolation(
    isolated_client,
    monkeypatch: pytest.MonkeyPatch,
):
    """Three real JWT identities enforce hospital/global GET scopes."""

    client, operator_email = isolated_client

    suffix = uuid4().hex[:10]

    operator = register(
        client,
        name=f"Operator Hospital {suffix}",
        email=operator_email,
    )

    hospital_a = register(
        client,
        name=f"Hospital A {suffix}",
        email=f"hospital-a-{suffix}@example.test",
    )

    hospital_b = register(
        client,
        name=f"Hospital B {suffix}",
        email=f"hospital-b-{suffix}@example.test",
    )

    a_id = str(hospital_a["actor"]["hospital_id"])
    b_id = str(hospital_b["actor"]["hospital_id"])

    assert a_id != b_id

    # Synthetic authorization only; no external MRI is accessed.
    for letter in ("a", "b"):
        monkeypatch.setitem(
            AUTHORIZED_CASE_BY_HOSPITAL_SLUG,
            f"hospital-{letter}-{suffix}",
            f"synthetic-metadata-case-{letter}",
        )

    # Enroll separate nodes and agents for hospitals A and B.
    for label, identity in (
        ("a", hospital_a),
        ("b", hospital_b),
    ):
        post_success(
            client,
            API + "/training-nodes/enroll",
            identity=identity,
            payload={
                "node_identifier": f"node-{label}-{suffix}"
            },
        )

        post_success(
            client,
            API + "/training-agents/enroll",
            identity=identity,
            payload={
                "agent_identifier": f"agent-{label}-{suffix}"
            },
        )

    # The operator registers one synthetic model version.
    state = OrderedDict(
        weight=torch.tensor(
            [1.0, 2.0],
            dtype=torch.float32,
        )
    )

    schema = parameter_schema_from_state_dict(state)

    model = post_success(
        client,
        API + "/models",
        identity=operator,
        payload={
            "label": f"metadata-model-{suffix}",
            "model_commitment": hashlib.sha256(
                f"metadata-model-{suffix}".encode()
            ).hexdigest(),
            "parameter_schema": [
                item.to_record()
                for item in schema
            ],
        },
    )

    model_id = model["id"]

    federation_round = post_success(
        client,
        API + "/rounds",
        identity=operator,
        payload={
            "base_model_version_id": model_id,
            "participant_hospital_ids": [
                a_id,
                b_id,
            ],
            "requires_zk_verification": True,
            "research_mode": False,
        },
    )

    round_id = federation_round["id"]

    post_success(
        client,
        f"{API}/rounds/{round_id}/open",
        identity=operator,
        expected_status=200,
    )

    # Each hospital prepares its own database-backed update.
    update_a = post_success(
        client,
        f"{API}/rounds/{round_id}/updates/prepare",
        identity=hospital_a,
        payload={"model_version_id": model_id},
    )

    update_b = post_success(
        client,
        f"{API}/rounds/{round_id}/updates/prepare",
        identity=hospital_b,
        payload={"model_version_id": model_id},
    )

    assert update_a["id"] != update_b["id"]

    assert str(update_a["hospital_id"]) == a_id
    assert str(update_b["hospital_id"]) == b_id

    # Verify real PostgreSQL-backed GET /updates isolation.
    a_updates = get_success(
        client,
        "/updates",
        hospital_a,
    )

    b_updates = get_success(
        client,
        "/updates",
        hospital_b,
    )

    operator_updates = get_success(
        client,
        "/updates",
        operator,
    )

    assert update_a["id"] in {
        row["id"] for row in a_updates
    }

    assert update_b["id"] in {
        row["id"] for row in b_updates
    }

    assert all(
        str(row["hospital_id"]) == a_id
        for row in a_updates
    )

    assert all(
        str(row["hospital_id"]) == b_id
        for row in b_updates
    )

    operator_update_ids = {
        row["id"] for row in operator_updates
    }

    assert update_a["id"] in operator_update_ids
    assert update_b["id"] in operator_update_ids

    # Verify real PostgreSQL-backed GET /summary isolation.
    a_summary = get_success(
        client,
        "/summary",
        hospital_a,
    )

    b_summary = get_success(
        client,
        "/summary",
        hospital_b,
    )

    operator_summary = get_success(
        client,
        "/summary",
        operator,
    )

    for own, other_id, own_id, own_update in (
        (
            a_summary,
            b_id,
            a_id,
            update_a["id"],
        ),
        (
            b_summary,
            a_id,
            b_id,
            update_b["id"],
        ),
    ):
        coordinator = own["coordinator"]

        assert len(coordinator["hospitals"]) == 1

        expected_slug = (
            f"hospital-a-{suffix}"
            if own_id == a_id
            else f"hospital-b-{suffix}"
        )

        forbidden_slug = (
            f"hospital-b-{suffix}"
            if own_id == a_id
            else f"hospital-a-{suffix}"
        )

        assert (
            coordinator["hospitals"][0]["hospital_slug"]
            == expected_slug
        )

        assert forbidden_slug not in json.dumps(own)

        assert other_id not in json.dumps(own)

        assert coordinator["rounds"] == []
        assert coordinator["models"] == []
        assert coordinator["global_checkpoints"] == []

        assert own["historical_evidence"]["available"] is False
        assert own["historical_evidence"]["experiments"] == []

        visible_update_ids = {
            row["id"]
            for row in coordinator["submitted_updates"]
        }

        assert own_update in visible_update_ids

        assert all(
            str(row["hospital_id"]) == own_id
            for row in coordinator["submitted_updates"]
        )

        assert all(
            str(row["hospital_id"]) == own_id
            for row in coordinator["training_agents"]
        )

    operator_state = operator_summary["coordinator"]

    operator_hospital_slugs = {
        row["hospital_slug"]
        for row in operator_state["hospitals"]
    }

    assert (
        f"hospital-a-{suffix}"
        in operator_hospital_slugs
    )

    assert (
        f"hospital-b-{suffix}"
        in operator_hospital_slugs
    )

    assert round_id in {
        row["id"] for row in operator_state["rounds"]
    }

    assert model_id in {
        row["id"] for row in operator_state["models"]
    }

    operator_summary_updates = {
        row["id"]
        for row in operator_state["submitted_updates"]
    }

    assert update_a["id"] in operator_summary_updates
    assert update_b["id"] in operator_summary_updates

    # Nonoperator admins must not read global model/round APIs.
    for identity in (hospital_a, hospital_b):
        for path in ("/models", "/rounds"):
            response = client.get(
                API + path,
                headers=headers(identity),
            )

            assert response.status_code == 403, (
                f"{path}: {response.status_code} "
                f"{response.text}"
            )

    # Operator remains authorized for global model/round GET.
    operator_models = get_success(
        client,
        "/models",
        operator,
    )

    operator_rounds = get_success(
        client,
        "/rounds",
        operator,
    )

    assert model_id in {
        row["id"] for row in operator_models
    }

    assert round_id in {
        row["id"] for row in operator_rounds
    }

    # Requests without authentication must be rejected.
    for path in (
        "/summary",
        "/updates",
        "/models",
        "/rounds",
    ):
        response = client.get(API + path)

        assert response.status_code in (401, 403), (
            f"{path}: unexpected unauthenticated status "
            f"{response.status_code}"
        )


def test_real_doctor_jwt_denied_federation_admin_gets(
    isolated_client,
):
    """Verify real doctor login and administrative GET rejection."""

    client, _operator_email = isolated_client

    suffix = uuid4().hex[:10]

    # Create a genuine hospital-admin identity.
    admin = register(
        client,
        name=f"Doctor Security Hospital {suffix}",
        email=f"doctor-admin-{suffix}@example.test",
    )

    admin_actor = admin["actor"]

    hospital_id = str(admin_actor["hospital_id"])

    hospital_slug = admin_actor["hospital_slug"]

    doctor_email = f"doctor-{suffix}@example.test"

    doctor_password = "synthetic-doctor-test-password"

    # Hospital admin creates a doctor through the real API.
    created = client.post(
        "/api/v1/hospitals/me/doctors",
        headers=headers(admin),
        json={
            "full_name": "Synthetic Test Doctor",
            "email": doctor_email,
            "password": doctor_password,
        },
    )

    assert created.status_code == 201, created.text

    doctor_actor = created.json()

    assert doctor_actor["role"] == "doctor"

    assert str(doctor_actor["hospital_id"]) == hospital_id

    assert doctor_actor["hospital_slug"] == hospital_slug

    # Doctor logs in using the official HTTP endpoint.
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": doctor_email,
            "password": doctor_password,
            "hospital_slug": hospital_slug,
        },
    )

    assert login.status_code == 200, login.text

    doctor_identity = login.json()

    assert doctor_identity["token_type"] == "bearer"

    assert doctor_identity["access_token"]

    assert doctor_identity["actor"]["role"] == "doctor"

    assert (
        str(doctor_identity["actor"]["hospital_id"])
        == hospital_id
    )

    # The server must resolve the same doctor membership.
    me = client.get(
        "/api/v1/auth/me",
        headers=headers(doctor_identity),
    )

    assert me.status_code == 200, me.text

    resolved_actor = me.json()

    assert resolved_actor["role"] == "doctor"

    assert str(resolved_actor["hospital_id"]) == hospital_id

    assert (
        str(resolved_actor["user_id"])
        == str(doctor_actor["user_id"])
    )

    # Ensure the hospital administrator can access its summary.
    admin_summary = client.get(
        API + "/summary",
        headers=headers(admin),
    )

    assert admin_summary.status_code == 200, (
        admin_summary.text
    )

    # Real doctor JWT must not access federation admin routes.
    administrative_paths = (
        "/summary",
        "/updates",
        "/models",
        "/rounds",
    )

    for path in administrative_paths:
        response = client.get(
            API + path,
            headers=headers(doctor_identity),
        )

        assert response.status_code == 403, (
            f"Doctor unexpectedly accessed {path}: "
            f"{response.status_code} {response.text}"
        )
