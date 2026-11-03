"""Model provenance must be visible only to authenticated hospital members."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.v1.dependencies import get_current_principal
from app.api.v1.model import model_info
from app.core.errors import AuthenticationRequiredError
from app.models.auth import HospitalRole
from app.schemas.mri import ModelInfoResponse
from app.services.authentication import Principal


def _principal() -> Principal:
    return Principal(
        user_id=uuid4(),
        hospital_id=uuid4(),
        role=HospitalRole.DOCTOR,
        email="doctor@example.test",
        full_name="Doctor",
        hospital_name="Research Hospital",
        hospital_slug="research-hospital",
    )


def test_model_info_requires_bearer_authentication() -> None:
    """The dependency rejects a request before a model service is consulted."""

    with pytest.raises(AuthenticationRequiredError):
        get_current_principal(None, object())


class _ModelService:
    def model_info(self, model_source: str) -> dict[str, object]:
        return {
            "model_source": model_source,
            "model_name": "MONAI 3D U-Net",
            "modality_order": ["flair", "t1", "t1ce", "t2"],
            "architecture": {},
            "expected_parameter_count": 1,
            "configured": False,
            "integrity_status": "not_configured",
            "checkpoint": None,
            "model_loaded": False,
        }


def test_authenticated_doctor_can_inspect_global_model_readiness() -> None:
    response = model_info(
        model_source="global_fedavg_abc",
        service=_ModelService(),  # type: ignore[arg-type]
        _=_principal(),
    )

    assert isinstance(response, ModelInfoResponse)
    assert response.model_source == "global_fedavg_abc"
    assert response.configured is False
    assert response.integrity_status == "not_configured"
