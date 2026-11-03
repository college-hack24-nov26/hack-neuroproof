"""Historical Flower evidence projection retained outside the active coordinator.

No active V2 route imports this legacy projection. It remains as test-covered
source evidence and must not be mistaken for custom coordinator enrollment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from app.models.auth import Hospital
from app.schemas.federation import (
    FederationHospitalResponse,
    OwnLocalTrainingEvidenceResponse,
)
from app.services.authentication import Principal

# This mapping is evidence interpretation only. It does not discover hospitals,
# configure Flower nodes, create ports, or infer participation for new hospitals.
HISTORICAL_EVIDENCE_CODE_BY_SLUG = {
    "hospital-a": "A",
    "hospital-b": "B",
    "hospital-c": "C",
    "hospital-d": "D",
}
HISTORICAL_EVIDENCE_CODES = frozenset(HISTORICAL_EVIDENCE_CODE_BY_SLUG.values())


class HospitalListingRepository(Protocol):
    """The small read interface needed for federation dashboard discovery."""

    def list_hospitals(self) -> list[Hospital]:
        """Return the registered hospitals in stable display order."""


class FederationHospitalService:
    """Join registered hospitals with historical evidence without inventing nodes."""

    def __init__(self, repository: HospitalListingRepository) -> None:
        self._repository = repository

    def list_dashboard_hospitals(
        self,
        *,
        principal: Principal,
        local_training_metadata: Mapping[str, Mapping[str, Any]],
        fedavg_abc_participants: set[str],
    ) -> list[FederationHospitalResponse]:
        """Return every registered hospital, including those with no FL config."""

        result: list[FederationHospitalResponse] = []
        for hospital in self._repository.list_hospitals():
            evidence_code = HISTORICAL_EVIDENCE_CODE_BY_SLUG.get(hospital.slug)
            metadata = (
                local_training_metadata.get(evidence_code, {})
                if evidence_code is not None
                else {}
            )
            own_training = None
            if hospital.id == principal.hospital_id and metadata:
                own_training = OwnLocalTrainingEvidenceResponse(
                    epochs=metadata.get("epochs"),
                    training_loss=metadata.get("training_loss"),
                    training_seconds=metadata.get("training_seconds"),
                    patch_size=metadata.get("patch_size"),
                    federated_round_completed=metadata.get(
                        "federated_round_completed", False
                    ),
                    purpose=metadata.get("purpose"),
                )

            result.append(
                FederationHospitalResponse(
                    hospital_name=hospital.name,
                    hospital_slug=hospital.slug,
                    registered=True,
                    # No V2 Flower-node configuration exists yet. A registered
                    # hospital must not be represented as a configured node.
                    flower_node_configured=False,
                    flower_node_port=None,
                    flower_node_online=False,
                    local_training_evidence_available=bool(metadata),
                    participated_in_fedavg_abc=(
                        evidence_code in fedavg_abc_participants
                        if evidence_code is not None
                        else False
                    ),
                    own_local_training=own_training,
                )
            )
        return result
