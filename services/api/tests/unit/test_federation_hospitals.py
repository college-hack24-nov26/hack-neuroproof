"""Regression tests for dynamic registered-hospital federation cards."""

from __future__ import annotations

from uuid import uuid4

from app.models.auth import Hospital, HospitalRole
from app.services.authentication import Principal
from app.services.federation_hospitals import FederationHospitalService


class StubHospitalRepository:
    """Small repository double that models PostgreSQL's registered-hospital list."""

    def __init__(self, hospitals: list[Hospital]) -> None:
        self._hospitals = hospitals

    def list_hospitals(self) -> list[Hospital]:
        return self._hospitals


def _hospital(slug: str) -> Hospital:
    return Hospital(id=uuid4(), name=slug.replace("-", " ").title(), slug=slug)


def _principal(hospital: Hospital) -> Principal:
    return Principal(
        user_id=uuid4(),
        hospital_id=hospital.id,
        role=HospitalRole.HOSPITAL_ADMIN,
        email="admin@example.test",
        full_name="Test Administrator",
        hospital_name=hospital.name,
        hospital_slug=hospital.slug,
    )


def test_registered_hospitals_are_dynamic_and_do_not_imply_flower_nodes() -> None:
    hospitals = [
        _hospital("hospital-a"),
        _hospital("hospital-b"),
        _hospital("hospital-c"),
        _hospital("hospital-d"),
        _hospital("hospital-e"),
        _hospital("hospital-f"),
        _hospital("hospital-g"),
    ]
    service = FederationHospitalService(StubHospitalRepository(hospitals))

    statuses = service.list_dashboard_hospitals(
        principal=_principal(hospitals[0]),
        local_training_metadata={
            "A": {
                "epochs": 1,
                "training_loss": 0.5,
                "training_seconds": 1.0,
                "patch_size": [96, 96, 96],
                "federated_round_completed": True,
                "purpose": "historical smoke test",
            },
            "D": {"epochs": 1},
        },
        fedavg_abc_participants={"A", "B", "C"},
    )

    by_slug = {status.hospital_slug: status for status in statuses}
    assert set(by_slug) == {hospital.slug for hospital in hospitals}

    hospital_e = by_slug["hospital-e"]
    assert hospital_e.registered is True
    assert hospital_e.flower_node_configured is False
    assert hospital_e.flower_node_port is None
    assert hospital_e.flower_node_online is False
    assert hospital_e.local_training_evidence_available is False
    assert hospital_e.participated_in_fedavg_abc is False
    assert hospital_e.own_local_training is None

    assert by_slug["hospital-a"].participated_in_fedavg_abc is True
    assert by_slug["hospital-b"].participated_in_fedavg_abc is True
    assert by_slug["hospital-c"].participated_in_fedavg_abc is True
    assert by_slug["hospital-d"].participated_in_fedavg_abc is False
    assert by_slug["hospital-d"].local_training_evidence_available is True
    assert by_slug["hospital-a"].own_local_training is not None
