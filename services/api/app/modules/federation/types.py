"""Shared custom-coordinator value types and explicit lifecycle states."""

from __future__ import annotations

from enum import Enum


class FederationRoundStatus(str, Enum):
    """Lifecycle of a coordinator-managed training round."""

    DRAFT = "draft"
    OPEN = "open"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class RoundParticipantStatus(str, Enum):
    """Lifecycle of one enrolled hospital's round contribution metadata."""

    INVITED = "invited"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProofVerificationStatus(str, Enum):
    """Observed Groth16 verification state, never inferred from a hash."""

    NOT_SUBMITTED = "not_submitted"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"


class TrainingNodeStatus(str, Enum):
    """Whether a hospital has explicitly enrolled a coordinator node."""

    ENROLLED = "enrolled"
    DISABLED = "disabled"


class TrainingAgentStatus(str, Enum):
    """Lifecycle of a hospital-local agent tied to an enrolled training node."""

    ENROLLED = "enrolled"
    DISABLED = "disabled"


class TrainingDatasetStatus(str, Enum):
    """Observed local-dataset readiness without exposing a storage path."""

    AUTHORIZED_UNVALIDATED = "authorized_unvalidated"
    GEOMETRY_VALIDATED = "geometry_validated"
    NOT_APPROVED = "not_approved"
    UNAVAILABLE = "unavailable"


class UpdateArtifactStatus(str, Enum):
    """Lifecycle of a protected submitted update artifact."""

    PREPARED = "prepared"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
