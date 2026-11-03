"""Domain models used by application services and repositories."""
"""Persistence and domain models used by the API."""

from app.models.auth import Hospital, HospitalMembership, HospitalRole, User
from app.models.federation import (
    FederationGlobalCheckpoint,
    FederationModelVersion,
    FederationRound,
    FederationRoundParticipant,
    FederationTrainingNode,
    FederationTrainingAgent,
    FederationUpdateArtifact,
)
from app.models.imaging import MriCase, MriJobRecord, MriJobState

__all__ = [
    "Hospital",
    "HospitalMembership",
    "HospitalRole",
    "FederationGlobalCheckpoint",
    "FederationModelVersion",
    "FederationRound",
    "FederationRoundParticipant",
    "FederationTrainingNode",
    "FederationTrainingAgent",
    "FederationUpdateArtifact",
    "MriCase",
    "MriJobRecord",
    "MriJobState",
    "User",
]
