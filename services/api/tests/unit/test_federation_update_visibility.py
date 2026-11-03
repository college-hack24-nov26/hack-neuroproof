"""Hospital-scoped federation metadata regression tests.

Synthetic repository test; no PostgreSQL or MRI data required.
"""

from unittest.mock import Mock
from uuid import uuid4

from app.repositories.federation import (
    SqlAlchemyFederationRepository,
)


def test_federation_updates_support_hospital_scoping() -> None:
    """A hospital-specific query must enforce its tenant boundary."""

    session = Mock()
    session.scalars.return_value = []

    repository = SqlAlchemyFederationRepository(session)

    hospital_id = uuid4()

    repository.list_update_artifacts(
        hospital_id=hospital_id,
    )

    assert session.scalars.called

    statement = session.scalars.call_args.args[0]

    assert statement.whereclause is not None

    compiled_filter = str(
        statement.whereclause.compile(
            compile_kwargs={"literal_binds": True}
        )
    )

    assert "hospital_id" in compiled_filter
    assert any(
        str(value).replace("-", "").lower() == hospital_id.hex
        for value in statement.whereclause.compile().params.values()
    )
