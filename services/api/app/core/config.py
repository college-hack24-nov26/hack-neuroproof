"""Typed environment configuration for the MRI API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _optional_path(name: str) -> Path | None:
    raw_value = os.getenv(name, "").strip()
    return Path(raw_value).expanduser() if raw_value else None


def _optional_value(name: str) -> str | None:
    """Read an optional environment value without supplying an insecure default."""

    value = os.getenv(name, "").strip()
    return value or None


def _csv_values(name: str) -> frozenset[str]:
    """Read a small non-secret allowlist with normalized values."""

    raw_value = os.getenv(name, "")
    return frozenset(
        value.strip().lower()
        for value in raw_value.split(",")
        if value.strip()
    )


def _positive_int(name: str, default: int, *, allow_zero: bool = False) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be positive.")
    return value


def _optional_positive_int(name: str) -> int | None:
    """Read an optional positive integer without enabling a sensitive integration."""

    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive.")
    return value


def _unit_interval_float(name: str, default: float) -> float:
    """Read a floating-point value in the half-open [0, 1) interval."""

    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number from 0 (inclusive) to 1 (exclusive).") from exc
    if not 0 <= value < 1:
        raise ValueError(f"{name} must be from 0 (inclusive) to 1 (exclusive).")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    """Read an explicit boolean without silently enabling sensitive work."""

    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes"}:
        return True
    if raw_value in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be true or false.")


@dataclass(frozen=True)
class Settings:
    """Runtime settings that never embed protected paths or secrets in source code."""

    model_checkpoint_path: Path | None
    model_sha256: str | None
    result_storage_dir: Path | None
    inference_device: str = "cpu"
    max_upload_bytes: int = 64 * 1024 * 1024
    cpu_threads: int = 0
    sliding_window_overlap: float = 0.5
    database_url: str | None = None
    jwt_secret: str | None = None
    jwt_issuer: str = "zkp-cerebrachain-v2"
    access_token_ttl_seconds: int = 900
    global_model_checkpoint_path: Path | None = None
    global_model_sha256: str | None = None
    federation_checkpoint_dir: Path | None = None
    federation_operator_emails: frozenset[str] = frozenset()
    proof_receipt_reader_emails: frozenset[str] = frozenset()
    federation_update_storage_dir: Path | None = None
    federation_update_max_bytes: int = 64 * 1024 * 1024
    training_dataset_root: Path | None = None
    training_execution_enabled: bool = False
    groth16_artifacts_dir: Path | None = None
    groth16_manifest_sha256: str | None = None
    groth16_snarkjs_binary: Path | None = None
    groth16_node_binary: Path | None = None
    groth16_poseidon_script: Path | None = None
    groth16_timeout_seconds: int = 15
    groth16_max_chunks: int = 128
    groth16_proof_max_bytes: int = 128 * 1024
    proof_receipt_anchor_rpc_url: str | None = None
    proof_receipt_anchor_expected_chain_id: int | None = None
    proof_receipt_anchor_contract_address: str | None = None
    proof_receipt_anchor_runtime_code_sha256: str | None = None
    proof_receipt_anchor_abi_version: str | None = None
    proof_receipt_anchor_required_confirmations: int = 1
    proof_receipt_anchor_timeout_seconds: int = 3

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build settings from environment variables without reading secret values."""

        return cls(
            model_checkpoint_path=_optional_path("CEREBRACHAIN_MODEL_CHECKPOINT"),
            model_sha256=os.getenv("CEREBRACHAIN_MODEL_SHA256", "").strip() or None,
            result_storage_dir=_optional_path("CEREBRACHAIN_RESULT_STORAGE_DIR"),
            inference_device=os.getenv("CEREBRACHAIN_INFERENCE_DEVICE", "cpu").strip().lower(),
            max_upload_bytes=_positive_int(
                "CEREBRACHAIN_MAX_UPLOAD_BYTES",
                64 * 1024 * 1024,
            ),
            cpu_threads=_positive_int(
                "CEREBRACHAIN_CPU_THREADS",
                0,
                allow_zero=True,
            ),
            sliding_window_overlap=_unit_interval_float(
                "CEREBRACHAIN_SLIDING_WINDOW_OVERLAP",
                0.5,
            ),
            database_url=_optional_value("CEREBRACHAIN_DATABASE_URL"),
            jwt_secret=_optional_value("CEREBRACHAIN_JWT_SECRET"),
            jwt_issuer=os.getenv(
                "CEREBRACHAIN_JWT_ISSUER", "zkp-cerebrachain-v2"
            ).strip(),
            access_token_ttl_seconds=_positive_int(
                "CEREBRACHAIN_ACCESS_TOKEN_TTL_SECONDS",
                900,
            ),
            global_model_checkpoint_path=_optional_path("CEREBRACHAIN_GLOBAL_MODEL_CHECKPOINT"),
            global_model_sha256=_optional_value("CEREBRACHAIN_GLOBAL_MODEL_SHA256"),
            federation_checkpoint_dir=_optional_path("CEREBRACHAIN_FEDERATION_CHECKPOINT_DIR"),
            federation_operator_emails=_csv_values("CEREBRACHAIN_FEDERATION_OPERATOR_EMAILS"),
            proof_receipt_reader_emails=_csv_values(
                "CEREBRACHAIN_PROOF_RECEIPT_READER_EMAILS"
            ),
            federation_update_storage_dir=_optional_path("CEREBRACHAIN_FEDERATION_UPDATE_STORAGE_DIR"),
            federation_update_max_bytes=_positive_int(
                "CEREBRACHAIN_FEDERATION_UPDATE_MAX_BYTES",
                64 * 1024 * 1024,
            ),
            training_dataset_root=_optional_path("CEREBRACHAIN_TRAINING_DATASET_ROOT"),
            training_execution_enabled=_boolean("CEREBRACHAIN_TRAINING_EXECUTION_ENABLED"),
            groth16_artifacts_dir=_optional_path("CEREBRACHAIN_GROTH16_ARTIFACTS_DIR"),
            groth16_manifest_sha256=_optional_value("CEREBRACHAIN_GROTH16_MANIFEST_SHA256"),
            groth16_snarkjs_binary=_optional_path("CEREBRACHAIN_GROTH16_SNARKJS_BIN"),
            groth16_node_binary=_optional_path("CEREBRACHAIN_GROTH16_NODE_BIN"),
            groth16_poseidon_script=_optional_path("CEREBRACHAIN_GROTH16_POSEIDON_SCRIPT"),
            groth16_timeout_seconds=_positive_int("CEREBRACHAIN_GROTH16_TIMEOUT_SECONDS", 15),
            groth16_max_chunks=_positive_int("CEREBRACHAIN_GROTH16_MAX_CHUNKS", 128),
            groth16_proof_max_bytes=_positive_int(
                "CEREBRACHAIN_GROTH16_PROOF_MAX_BYTES",
                128 * 1024,
            ),
            proof_receipt_anchor_rpc_url=_optional_value(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_RPC_URL"
            ),
            proof_receipt_anchor_expected_chain_id=_optional_positive_int(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_EXPECTED_CHAIN_ID"
            ),
            proof_receipt_anchor_contract_address=_optional_value(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_CONTRACT_ADDRESS"
            ),
            proof_receipt_anchor_runtime_code_sha256=_optional_value(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_RUNTIME_CODE_SHA256"
            ),
            proof_receipt_anchor_abi_version=_optional_value(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_ABI_VERSION"
            ),
            proof_receipt_anchor_required_confirmations=_positive_int(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_REQUIRED_CONFIRMATIONS",
                1,
            ),
            proof_receipt_anchor_timeout_seconds=_positive_int(
                "CEREBRACHAIN_PROOF_RECEIPT_ANCHOR_TIMEOUT_SECONDS",
                3,
            ),
        )

    @property
    def model_is_configured(self) -> bool:
        """Return whether both model path and integrity hash are configured."""

        return self.model_checkpoint_path is not None and self.model_sha256 is not None

    @property
    def global_model_is_configured(self) -> bool:
        return self.global_model_checkpoint_path is not None and self.global_model_sha256 is not None

    @property
    def federation_checkpoint_storage_is_configured(self) -> bool:
        """Return whether custom coordinator output storage was configured."""

        return self.federation_checkpoint_dir is not None

    @property
    def federation_update_storage_is_configured(self) -> bool:
        """Return whether protected external update-artifact storage was configured."""

        return self.federation_update_storage_dir is not None

    @property
    def result_storage_is_configured(self) -> bool:
        """Return whether a protected result-storage root is configured."""

        return self.result_storage_dir is not None

    @property
    def proof_receipt_anchor_is_configured(self) -> bool:
        """Return whether all values for the read-only V2 anchor lookup are present."""

        return all(
            (
                self.proof_receipt_anchor_rpc_url,
                self.proof_receipt_anchor_expected_chain_id,
                self.proof_receipt_anchor_contract_address,
                self.proof_receipt_anchor_runtime_code_sha256,
                self.proof_receipt_anchor_abi_version,
            )
        )

    @property
    def database_is_configured(self) -> bool:
        """Return whether a database connection URL was provided."""

        return self.database_url is not None

    @property
    def authentication_is_configured(self) -> bool:
        """Return whether database and a non-default JWT signing secret are available."""

        return (
            self.database_is_configured
            and self.jwt_secret is not None
            and len(self.jwt_secret) >= 32
            and bool(self.jwt_issuer)
        )
