"""Hospital-local training integration security tests.

Synthetic principals and agent records only.
No real MRI, checkpoints, database access, or training.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.modules.federation.local_training_service as service
from app.modules.federation.training_agent import (
    LocalTrainingConfiguration,
    TrainingAgentError,
)


def make_settings(*, enabled: bool = False):
    return SimpleNamespace(
        training_execution_enabled=enabled,
        training_dataset_root=None,
        model_checkpoint_path=None,
        model_sha256=None,
    )


def make_hospital(
    *,
    slug: str = "hospital-a",
    case_reference: str = "BraTS2021_00495",
):
    hospital_id = uuid4()

    principal = SimpleNamespace(
        hospital_id=hospital_id,
        hospital_slug=slug,
    )

    agent = SimpleNamespace(
        hospital_id=hospital_id,
        status="enrolled",
        authorized_case_reference=case_reference,
    )

    return principal, agent


def run_service(
    *,
    settings,
    principal,
    agent,
    configuration=None,
    authorized=False,
):
    if configuration is None:
        configuration = LocalTrainingConfiguration(
            local_epochs=1,
            batch_size=1,
            learning_rate=0.0001,
        )

    return service.run_hospital_local_training_once(
        settings=settings,
        principal=principal,
        agent=agent,
        model_version=SimpleNamespace(),
        configuration=configuration,
        execution_authorized=authorized,
    )


@pytest.mark.parametrize(
    "enabled,authorized",
    [
        (False, False),
        (False, True),
        (True, False),
    ],
)
def test_training_requires_both_execution_permissions(
    monkeypatch,
    enabled,
    authorized,
):
    principal, agent = make_hospital()

    class ForbiddenAgent:
        def __init__(self, settings):
            raise AssertionError(
                "Training agent must not be initialized."
            )

    monkeypatch.setattr(
        service,
        "HospitalTrainingAgent",
        ForbiddenAgent,
    )

    with pytest.raises(
        TrainingAgentError,
        match="disabled",
    ):
        run_service(
            settings=make_settings(enabled=enabled),
            principal=principal,
            agent=agent,
            authorized=authorized,
        )


def test_cross_hospital_agent_rejected():
    principal, agent = make_hospital()

    # Hospital A tries to use an agent belonging
    # to a different hospital.
    agent.hospital_id = uuid4()

    with pytest.raises(TrainingAgentError):
        run_service(
            settings=make_settings(enabled=True),
            principal=principal,
            agent=agent,
            authorized=True,
        )


def test_unauthorized_dataset_assignment_rejected():
    principal, agent = make_hospital()

    # Hospital A's approved case is BraTS2021_00495.
    agent.authorized_case_reference = "BraTS2021_00000"

    with pytest.raises(TrainingAgentError):
        run_service(
            settings=make_settings(enabled=True),
            principal=principal,
            agent=agent,
            authorized=True,
        )


def test_hospital_e_without_approved_dataset_rejected():
    principal, agent = make_hospital(
        slug="hospital-e",
        case_reference="BraTS2021_00495",
    )

    with pytest.raises(TrainingAgentError):
        run_service(
            settings=make_settings(enabled=True),
            principal=principal,
            agent=agent,
            authorized=True,
        )


def test_unsupported_training_configuration_rejected():
    principal, agent = make_hospital()

    configuration = LocalTrainingConfiguration(
        local_epochs=2,
        batch_size=1,
        learning_rate=0.0001,
    )

    with pytest.raises(
        TrainingAgentError,
        match="Unsupported",
    ):
        run_service(
            settings=make_settings(enabled=True),
            principal=principal,
            agent=agent,
            configuration=configuration,
            authorized=True,
        )


def test_missing_training_dataset_root_rejected():
    principal, agent = make_hospital()

    with pytest.raises(
        TrainingAgentError,
        match="dataset",
    ):
        run_service(
            settings=make_settings(enabled=True),
            principal=principal,
            agent=agent,
            authorized=True,
        )
