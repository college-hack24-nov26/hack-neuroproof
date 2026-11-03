"""Persistence queries for custom coordinator metadata, not model payloads."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.federation import (
    FederationGlobalCheckpoint,
    FederationModelVersion,
    FederationRound,
    FederationRoundParticipant,
    FederationTrainingAgent,
    FederationTrainingNode,
    FederationUpdateArtifact,
)


class SqlAlchemyFederationRepository:
    """Keep coordinator persistence and transaction details out of routes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def training_node_for_hospital(self, hospital_id: UUID) -> FederationTrainingNode | None:
        return self._session.scalar(
            select(FederationTrainingNode).where(FederationTrainingNode.hospital_id == hospital_id)
        )

    def list_training_nodes(self) -> list[FederationTrainingNode]:
        return list(
            self._session.scalars(
                select(FederationTrainingNode).order_by(FederationTrainingNode.created_at)
            )
        )

    def model_version(self, model_version_id: UUID) -> FederationModelVersion | None:
        return self._session.get(FederationModelVersion, model_version_id)

    def list_model_versions(self) -> list[FederationModelVersion]:
        return list(
            self._session.scalars(
                select(FederationModelVersion).order_by(FederationModelVersion.created_at.desc())
            )
        )

    def federation_round(self, round_id: UUID) -> FederationRound | None:
        return self._session.get(FederationRound, round_id)

    def round(self, round_id: UUID) -> FederationRound | None:
        return self.federation_round(round_id)

    def list_rounds(self, *, limit: int = 20) -> list[FederationRound]:
        return list(
            self._session.scalars(
                select(FederationRound)
                .order_by(FederationRound.created_at.desc())
                .limit(limit)
            )
        )

    def participants_for_round(self, round_id: UUID) -> list[FederationRoundParticipant]:
        return list(
            self._session.scalars(
                select(FederationRoundParticipant)
                .where(FederationRoundParticipant.federation_round_id == round_id)
                .order_by(FederationRoundParticipant.hospital_id)
            )
        )

    def participant_for_round_hospital(
        self,
        *,
        round_id: UUID,
        hospital_id: UUID,
    ) -> FederationRoundParticipant | None:
        return self._session.scalar(
            select(FederationRoundParticipant).where(
                FederationRoundParticipant.federation_round_id == round_id,
                FederationRoundParticipant.hospital_id == hospital_id,
            )
        )

    def training_agent_for_hospital(self, hospital_id: UUID) -> FederationTrainingAgent | None:
        return self._session.scalar(
            select(FederationTrainingAgent).where(
                FederationTrainingAgent.hospital_id == hospital_id,
            )
        )

    def training_agent_for_id(self, agent_id: UUID) -> FederationTrainingAgent | None:
        return self._session.get(FederationTrainingAgent, agent_id)

    def list_training_agents(self) -> list[FederationTrainingAgent]:
        return list(
            self._session.scalars(
                select(FederationTrainingAgent).order_by(FederationTrainingAgent.created_at)
            )
        )

    def update_artifact_for_round_hospital(
        self,
        *,
        round_id: UUID,
        hospital_id: UUID,
    ) -> FederationUpdateArtifact | None:
        return self._session.scalar(
            select(FederationUpdateArtifact).where(
                FederationUpdateArtifact.federation_round_id == round_id,
                FederationUpdateArtifact.hospital_id == hospital_id,
            )
        )

    def update_artifact(self, submission_id: UUID) -> FederationUpdateArtifact | None:
        return self._session.get(FederationUpdateArtifact, submission_id)

    def list_update_artifacts(
        self,
        *,
        hospital_id: UUID | None = None,
        limit: int = 100,
    ) -> list[FederationUpdateArtifact]:
        """List update metadata with optional hospital filtering.

        The API layer must authorize global access explicitly.
        Hospital-specific callers must supply hospital_id.
        """
        statement = select(FederationUpdateArtifact)

        if hospital_id is not None:
            statement = statement.where(
                FederationUpdateArtifact.hospital_id == hospital_id
            )

        statement = (
            statement
            .order_by(FederationUpdateArtifact.prepared_at.desc())
            .limit(limit)
        )

        return list(self._session.scalars(statement))

    def list_checkpoints(self) -> list[FederationGlobalCheckpoint]:
        return list(
            self._session.scalars(
                select(FederationGlobalCheckpoint)
                .order_by(FederationGlobalCheckpoint.created_at.desc())
            )
        )

    def add(self, entity: object) -> None:
        self._session.add(entity)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
