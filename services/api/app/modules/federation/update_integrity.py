"""Full-model archive integrity verification.

This module verifies complete protected model-update bytes
against trusted commitments and the registered parameter schema.

It does NOT prove training correctness, MRI authenticity,
Groth16 coverage, or aggregation eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re

from app.modules.federation.fedavg import state_dict_sha256
from app.modules.federation.update_archive import (
    ParameterSpec,
    parameter_schema_commitment,
    parse_model_update_archive,
)


_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


class UpdateIntegrityError(RuntimeError):
    """Protected model update failed an integrity requirement."""


@dataclass(frozen=True)
class FullModelIntegrityReceipt:
    """Evidence of archive and full-state integrity only."""

    artifact_sha256: str
    base_model_commitment: str
    update_commitment: str
    parameter_schema_commitment: str
    state_tensor_count: int
    state_value_count: int
    sample_count: int


def verify_pinned_model_update(
    archive_bytes: bytes,
    *,
    trusted_artifact_sha256: str,
    trusted_base_model_commitment: str,
    trusted_parameter_schema: tuple[ParameterSpec, ...],
    max_bytes: int,
) -> FullModelIntegrityReceipt:
    """Validate a complete archive against independently trusted inputs.

    The expected artifact digest must come from a trusted storage
    or authentication boundary, not simply be calculated from
    untrusted uploaded bytes and treated as authorization.

    The expected base commitment and schema must come from
    the registered, verified model version.
    """

    for value in (
        trusted_artifact_sha256,
        trusted_base_model_commitment,
    ):
        if (
            not isinstance(value, str)
            or _SHA256_PATTERN.fullmatch(value) is None
        ):
            raise UpdateIntegrityError(
                "Trusted SHA-256 commitment is invalid."
            )

    if (
        not isinstance(archive_bytes, bytes)
        or not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or max_bytes <= 0
        or not archive_bytes
        or len(archive_bytes) > max_bytes
    ):
        raise UpdateIntegrityError(
            "Model update archive size or type is invalid."
        )

    actual_artifact_sha256 = hashlib.sha256(
        archive_bytes
    ).hexdigest()

    if not hmac.compare_digest(
        actual_artifact_sha256,
        trusted_artifact_sha256.lower(),
    ):
        raise UpdateIntegrityError(
            "Protected model update artifact SHA-256 mismatch."
        )

    expected_schema_commitment = (
        parameter_schema_commitment(
            trusted_parameter_schema
        )
    )

    # Reuse the established safe ZIP/NumPy archive parser.
    parsed = parse_model_update_archive(
        archive_bytes,
        expected_schema=trusted_parameter_schema,
        expected_schema_commitment=expected_schema_commitment,
        max_bytes=max_bytes,
    )

    if not hmac.compare_digest(
        parsed.model_version_commitment.lower(),
        trusted_base_model_commitment.lower(),
    ):
        raise UpdateIntegrityError(
            "Model update does not match the trusted base version."
        )

    actual_update_commitment = state_dict_sha256(
        parsed.state_dict
    )

    if not hmac.compare_digest(
        actual_update_commitment,
        parsed.update_commitment,
    ):
        raise UpdateIntegrityError(
            "Model update tensor commitment mismatch."
        )

    if not hmac.compare_digest(
        parsed.artifact_sha256,
        actual_artifact_sha256,
    ):
        raise UpdateIntegrityError(
            "Parsed artifact integrity mismatch."
        )

    return FullModelIntegrityReceipt(
        artifact_sha256=actual_artifact_sha256,
        base_model_commitment=parsed.model_version_commitment,
        update_commitment=actual_update_commitment,
        parameter_schema_commitment=expected_schema_commitment,
        state_tensor_count=len(parsed.state_dict),
        state_value_count=sum(
            tensor.numel()
            for tensor in parsed.state_dict.values()
        ),
        sample_count=parsed.sample_count,
    )
