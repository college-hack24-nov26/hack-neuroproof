"""Cross-hospital federation write ownership tests.

Tests actual ModelUpdateSubmissionService methods using synthetic objects.
No PostgreSQL, ZIP storage, MRI files, or cryptographic execution.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.errors import ResourceNotFoundError
from app.modules.federation.update_transport import (
    ModelUpdateSubmissionService,
)


def make_service(repository, storage):
    return ModelUpdateSubmissionService(
        repository,
        storage=storage,
        max_bytes=1024,
        validator=Mock(),
    )


@pytest.mark.parametrize(
    "operation",
    ["artifact", "proof"],
)
@pytest.mark.parametrize(
    "scenario",
    [
        "other_hospital",
        "unknown_submission",
        "missing_identity",
    ],
)
def test_unauthorized_submission_rejected_before_side_effects(
    operation,
    scenario,
):
    own_hospital = uuid4()
    other_hospital = uuid4()
    submission_id = uuid4()

    principal = SimpleNamespace(
        hospital_id=(
            None
            if scenario == "missing_identity"
            else own_hospital
        ),
    )

    repository = Mock()
    storage = Mock()

    if scenario == "unknown_submission":
        repository.update_artifact.return_value = None
    else:
        repository.update_artifact.return_value = SimpleNamespace(
            id=submission_id,
            hospital_id=other_hospital,
        )

    service = make_service(repository, storage)

    with pytest.raises(ResourceNotFoundError) as captured:
        if operation == "artifact":
            service.submit_artifact(
                principal=principal,
                submission_id=submission_id,
                content=b"synthetic-invalid-update",
            )
        else:
            service.submit_proof(
                principal=principal,
                submission_id=submission_id,
                proof_envelope=Mock(),
            )

    assert (
        str(captured.value)
        == "The requested update submission was not found."
    )

    repository.update_artifact.assert_called_once_with(
        submission_id
    )

    repository.commit.assert_not_called()
    repository.add.assert_not_called()
    repository.round.assert_not_called()
    repository.training_node_for_hospital.assert_not_called()

    assert storage.mock_calls == []


def test_matching_hospital_passes_owned_artifact_lookup():
    hospital_id = uuid4()
    submission_id = uuid4()

    principal = SimpleNamespace(
        hospital_id=hospital_id,
    )

    artifact = SimpleNamespace(
        id=submission_id,
        hospital_id=hospital_id,
    )

    repository = Mock()
    repository.update_artifact.return_value = artifact

    storage = Mock()

    service = make_service(repository, storage)

    result = service._required_owned_artifact(
        principal,
        submission_id,
    )

    assert result is artifact

    repository.update_artifact.assert_called_once_with(
        submission_id
    )

    repository.commit.assert_not_called()
    assert storage.mock_calls == []
