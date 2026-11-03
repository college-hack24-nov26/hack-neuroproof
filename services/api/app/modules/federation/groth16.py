"""Pinned, bounded verification for the V2 quantized-update Groth16 circuit.

The module never accepts a client verification key, proving key, witness, or
artifact path. It verifies only a server-pinned verification key and replays
the deterministic quantization of the protected model-update archive in memory.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

import torch

from app.modules.federation.types import ProofVerificationStatus
from app.modules.federation.verification import (
    Groth16ProofEnvelope,
    Groth16VerificationRequest,
    Groth16VerificationResult,
)

BN254_SCALAR_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
CIRCUIT_VERSION = "quantized-update-chunk-v1"
PUBLIC_SIGNAL_NAMES = (
    "round_context",
    "model_context",
    "artifact_context",
    "chunk_index",
    "chunk_count",
    "chunk_commitment",
    "binding_commitment",
)
CHUNK_SIZE = 8
QUANTIZATION_SCALE = Decimal("16")
QUANTIZED_MIN = -128
QUANTIZED_MAX = 127
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_RE = re.compile(r"^(0|[1-9][0-9]*)$")


class Groth16VerificationError(ValueError):
    """A proof, artifact, or quantized update does not satisfy the V2 policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QuantizedUpdate:
    """Canonical signed-int8 representation used only for proof verification."""

    chunks: tuple[tuple[int, ...], ...]
    value_count: int


@dataclass(frozen=True)
class Groth16VerifierConfiguration:
    """Server-owned executable and artifact locations for one approved circuit."""

    artifacts_dir: Path | None
    manifest_sha256: str | None
    snarkjs_binary: Path | None
    node_binary: Path | None
    poseidon_script: Path | None
    timeout_seconds: int = 15
    max_chunks: int = 128


def hash_to_field(domain: str, value: str) -> str:
    """Encode public V2 context as SHA-256(domain || NUL || UTF-8 value) mod r.

    This is a public context encoder, not a zero-knowledge commitment and not a
    substitute for the circuit's Poseidon commitments.
    """

    if not domain or "\x00" in domain or not isinstance(value, str):
        raise Groth16VerificationError("context_encoding_invalid", "Proof context encoding is invalid.")
    digest = hashlib.sha256(domain.encode("ascii") + b"\x00" + value.encode("utf-8")).digest()
    return str(int.from_bytes(digest, "big") % BN254_SCALAR_FIELD)


def _enforce_chunk_capacity(
    state_dict: Mapping[str, object],
    max_chunks: int,
) -> None:
    """Reject oversized updates before expensive quantization.

    Reads only tensor metadata, never tensor values.
    This is an early resource guard, not a replacement for
    the existing cryptographic coverage verification.
    """

    if (
        isinstance(max_chunks, bool)
        or not isinstance(max_chunks, int)
        or max_chunks <= 0
    ):
        raise Groth16VerificationError(
            "proof_capacity_invalid",
            "Groth16 proof capacity configuration is invalid.",
        )

    maximum_values = max_chunks * CHUNK_SIZE
    total_values = 0

    for tensor in state_dict.values():
        if not isinstance(tensor, torch.Tensor):
            raise Groth16VerificationError(
                "quantization_invalid",
                "Model update cannot be quantized safely.",
            )

        total_values += tensor.numel()

        if total_values > maximum_values:
            raise Groth16VerificationError(
                "proof_coverage_exceeds_limit",
                "Update requires more proofs than this verifier "
                "is configured to process.",
            )


def quantize_state_dict(state_dict: Mapping[str, object]) -> QuantizedUpdate:
    """Use sorted names, C-order values, scale 16, and ties-to-even rounding.

    Values outside the signed-int8 range are rejected rather than clipped: a
    proof must describe the actual documented quantization, not a substituted
    update. The final chunk is deterministically padded with zeroes.
    """

    values: list[int] = []
    for name in sorted(state_dict):
        tensor = state_dict[name]
        if not isinstance(name, str) or not isinstance(tensor, torch.Tensor):
            raise Groth16VerificationError("quantization_invalid", "Model update cannot be quantized safely.")
        if tensor.layout != torch.strided:
            raise Groth16VerificationError("quantization_invalid", "Model update cannot be quantized safely.")
        value = tensor.detach().to(device="cpu").contiguous().reshape(-1)
        if tensor.dtype.is_floating_point and not bool(torch.isfinite(value).all().item()):
            raise Groth16VerificationError("quantization_non_finite", "Model update contains non-finite values.")
        for item in value.tolist():
            if isinstance(item, bool):
                decimal_value = Decimal(int(item))
            elif isinstance(item, int):
                decimal_value = Decimal(item)
            elif isinstance(item, float) and math.isfinite(item):
                decimal_value = Decimal(str(item))
            else:
                raise Groth16VerificationError("quantization_invalid", "Model update cannot be quantized safely.")
            quantized = int((decimal_value * QUANTIZATION_SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))
            if not QUANTIZED_MIN <= quantized <= QUANTIZED_MAX:
                raise Groth16VerificationError(
                    "quantization_out_of_range",
                    "Model update exceeds the configured signed-int8 quantization range.",
                )
            values.append(quantized)
    if not values:
        raise Groth16VerificationError("quantization_empty", "Model update has no quantizable values.")
    chunks: list[tuple[int, ...]] = []
    for offset in range(0, len(values), CHUNK_SIZE):
        chunk = values[offset : offset + CHUNK_SIZE]
        chunks.append(tuple(chunk + [0] * (CHUNK_SIZE - len(chunk))))
    return QuantizedUpdate(chunks=tuple(chunks), value_count=len(values))


class PoseidonCommitmentComputer:
    """Run the trusted local circomlibjs helper with bounded JSON stdin/stdout."""

    def __init__(self, *, node_binary: Path | None, script_path: Path | None, timeout_seconds: int) -> None:
        self._node_binary = node_binary
        self._script_path = script_path
        self._timeout_seconds = timeout_seconds

    @property
    def is_available(self) -> bool:
        return bool(
            self._node_binary
            and self._node_binary.is_file()
            and self._script_path
            and self._script_path.is_file()
            and not self._script_path.is_symlink()
        )

    def commitments(self, chunks: Sequence[Sequence[int]]) -> tuple[str, ...]:
        if not self.is_available:
            raise Groth16VerificationError("poseidon_unavailable", "Poseidon commitment helper is not configured.")
        if len(chunks) > 4096 or any(len(chunk) != CHUNK_SIZE for chunk in chunks):
            raise Groth16VerificationError("proof_coverage_invalid", "Proof chunk coverage is invalid.")
        encoded = [[str(value + 128) for value in chunk] for chunk in chunks]
        if any(value < 0 or value > 255 for chunk in encoded for value in map(int, chunk)):
            raise Groth16VerificationError("quantization_out_of_range", "Quantized chunk values are invalid.")
        request = json.dumps({"chunks": encoded}, separators=(",", ":")).encode("utf-8")
        try:
            completed = subprocess.run(
                [str(self._node_binary), str(self._script_path)],
                input=request,
                capture_output=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Groth16VerificationError("poseidon_execution_failed", "Poseidon commitment computation failed.") from exc
        if completed.returncode != 0 or len(completed.stdout) > 512 * 1024:
            raise Groth16VerificationError("poseidon_execution_failed", "Poseidon commitment computation failed.")
        try:
            result = json.loads(completed.stdout.decode("utf-8"))
            commitments = result["commitments"]
        except (KeyError, UnicodeDecodeError, ValueError, TypeError) as exc:
            raise Groth16VerificationError("poseidon_execution_failed", "Poseidon commitment computation failed.") from exc
        if not isinstance(commitments, list) or len(commitments) != len(chunks):
            raise Groth16VerificationError("poseidon_execution_failed", "Poseidon commitment computation failed.")
        return tuple(_field_signal(value, "chunk commitment") for value in commitments)


class Groth16ArtifactVerifier:
    """Verify the pinned V2 circuit and full protected-update chunk coverage."""

    def __init__(self, configuration: Groth16VerifierConfiguration) -> None:
        self._configuration = configuration
        self._manifest: dict[str, Any] | None = None
        self._verification_key_path: Path | None = None
        self._verification_key_id: str | None = None
        self._unavailable_reason = "A pinned Groth16 verifier is not configured."
        self._poseidon = PoseidonCommitmentComputer(
            node_binary=configuration.node_binary,
            script_path=configuration.poseidon_script,
            timeout_seconds=configuration.timeout_seconds,
        )
        self._load_artifacts()

    @property
    def is_available(self) -> bool:
        return self._manifest is not None and self._verification_key_path is not None and self._poseidon.is_available

    @property
    def is_ready(self) -> bool:
        """Phase 3 intentionally never enables production aggregation."""

        return False

    @property
    def verification_key_id(self) -> str | None:
        return self._verification_key_id

    @property
    def circuit_version(self) -> str | None:
        return self._manifest.get("circuit_version") if self._manifest is not None else None

    def verify(self, request: Groth16VerificationRequest) -> Groth16VerificationResult:
        """Verify every chunk proof and its server-derived artifact binding."""

        if not self.is_available:
            return Groth16VerificationResult(
                status=ProofVerificationStatus.PENDING_VERIFICATION,
                reason=self._unavailable_reason,
            )
        try:
            self._verify_envelope(request)
        except Groth16VerificationError as exc:
            return Groth16VerificationResult(
                status=ProofVerificationStatus.REJECTED,
                reason=str(exc),
                circuit_version=self.circuit_version,
                verification_key_id=self.verification_key_id,
            )
        return Groth16VerificationResult(
            status=ProofVerificationStatus.VERIFIED,
            reason=(
                "Cryptographically verified with a development-only circuit artifact; "
                "production aggregation remains disabled."
                if not self.is_ready
                else "Cryptographically verified against the pinned Groth16 verification key."
            ),
            circuit_version=self.circuit_version,
            verification_key_id=self.verification_key_id,
            coverage_complete=True,
            aggregation_eligible=False,
        )

    def _load_artifacts(self) -> None:
        configuration = self._configuration
        if (
            configuration.artifacts_dir is None
            or configuration.manifest_sha256 is None
            or configuration.snarkjs_binary is None
            or not configuration.snarkjs_binary.is_file()
            or not self._poseidon.is_available
            or configuration.timeout_seconds <= 0
            or configuration.max_chunks <= 0
        ):
            return
        root = configuration.artifacts_dir
        manifest_path = root / "manifest.json"
        key_path = root / "verification_key.json"
        if root.is_symlink() or not root.is_dir() or manifest_path.is_symlink() or key_path.is_symlink():
            self._unavailable_reason = "Pinned Groth16 artifacts are unavailable."
            return
        try:
            manifest_bytes = _read_bounded_file(manifest_path, 64 * 1024)
            if not _valid_sha256(configuration.manifest_sha256) or _sha256(manifest_bytes) != configuration.manifest_sha256.lower():
                self._unavailable_reason = "Pinned Groth16 manifest integrity validation failed."
                return
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            key_bytes = _read_bounded_file(key_path, 256 * 1024)
        except (Groth16VerificationError, UnicodeDecodeError, ValueError):
            self._unavailable_reason = "Pinned Groth16 artifacts are invalid."
            return
        if not _valid_manifest(manifest, _sha256(key_bytes)):
            self._unavailable_reason = "Pinned Groth16 artifact metadata is incompatible."
            return
        self._manifest = manifest
        self._verification_key_path = key_path
        self._verification_key_id = _sha256(key_bytes)

    def _verify_envelope(self, request: Groth16VerificationRequest) -> None:
        envelope = request.proof_envelope
        if envelope.circuit_version != CIRCUIT_VERSION or envelope.circuit_version != self.circuit_version:
            raise Groth16VerificationError("wrong_circuit", "Submitted proof uses an unapproved circuit version.")
        if envelope.verification_key_id.lower() != self.verification_key_id:
            raise Groth16VerificationError("wrong_verification_key", "Submitted proof uses an unapproved verification key.")
        if not _valid_sha256(request.artifact_sha256):
            raise Groth16VerificationError("artifact_binding_invalid", "Protected update artifact binding is invalid.")
        _enforce_chunk_capacity(
            request.state_dict,
            self._configuration.max_chunks,
        )
        quantized = quantize_state_dict(request.state_dict)
        if len(quantized.chunks) > self._configuration.max_chunks:
            raise Groth16VerificationError(
                "proof_coverage_exceeds_limit",
                "Update requires more proofs than this verifier is configured to process.",
            )
        if len(envelope.proofs) != len(quantized.chunks):
            raise Groth16VerificationError(
                "proof_coverage_incomplete",
                "Proof envelope does not cover every required quantized update chunk.",
            )
        commitments = self._poseidon.commitments(quantized.chunks)
        expected_context = (
            hash_to_field("cerebrachain/v2/groth16/round", request.training_round_identifier),
            hash_to_field("cerebrachain/v2/groth16/model", request.model_version_commitment.lower()),
            hash_to_field("cerebrachain/v2/groth16/artifact", request.artifact_sha256.lower()),
        )
        observed_indices: set[int] = set()
        for proof_item in envelope.proofs:
            signals = _validate_proof_schema(proof_item.proof, proof_item.public_signals)
            chunk_index = int(signals[3])
            if chunk_index >= len(quantized.chunks) or chunk_index in observed_indices:
                raise Groth16VerificationError("proof_coverage_invalid", "Proof chunk coverage is invalid.")
            expected = (*expected_context, str(chunk_index), str(len(quantized.chunks)), commitments[chunk_index])
            if signals[:6] != expected:
                raise Groth16VerificationError(
                    "public_input_mismatch",
                    "Proof public inputs do not match the authenticated round, model, artifact, or chunk.",
                )
            self._verify_with_snarkjs(proof_item.proof, signals)
            observed_indices.add(chunk_index)
        if observed_indices != set(range(len(quantized.chunks))):
            raise Groth16VerificationError("proof_coverage_incomplete", "Proof envelope has incomplete chunk coverage.")

    def _verify_with_snarkjs(self, proof: dict[str, object], signals: tuple[str, ...]) -> None:
        assert self._verification_key_path is not None
        assert self._configuration.snarkjs_binary is not None
        try:
            with tempfile.TemporaryDirectory(prefix="cerebrachain-groth16-") as directory:
                root = Path(directory)
                public_path = root / "public.json"
                proof_path = root / "proof.json"
                public_path.write_text(json.dumps(list(signals), separators=(",", ":")), encoding="utf-8")
                proof_path.write_text(json.dumps(proof, separators=(",", ":")), encoding="utf-8")
                completed = subprocess.run(
                    [
                        str(self._configuration.snarkjs_binary),
                        "groth16",
                        "verify",
                        str(self._verification_key_path),
                        str(public_path),
                        str(proof_path),
                    ],
                    capture_output=True,
                    check=False,
                    timeout=self._configuration.timeout_seconds,
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Groth16VerificationError("verification_execution_failed", "Groth16 verification failed safely.") from exc
        output = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode != 0 or "OK!" not in output:
            raise Groth16VerificationError("invalid_proof", "Groth16 proof verification failed.")


def verifier_from_settings(settings: object) -> Groth16ArtifactVerifier:
    """Build the verifier from non-secret deployment configuration only."""

    return Groth16ArtifactVerifier(
        Groth16VerifierConfiguration(
            artifacts_dir=getattr(settings, "groth16_artifacts_dir", None),
            manifest_sha256=getattr(settings, "groth16_manifest_sha256", None),
            snarkjs_binary=getattr(settings, "groth16_snarkjs_binary", None),
            node_binary=getattr(settings, "groth16_node_binary", None),
            poseidon_script=getattr(settings, "groth16_poseidon_script", None),
            timeout_seconds=getattr(settings, "groth16_timeout_seconds", 15),
            max_chunks=getattr(settings, "groth16_max_chunks", 128),
        )
    )


def _valid_manifest(value: object, verification_key_sha256: str) -> bool:
    if not isinstance(value, dict):
        return False
    quantization = value.get("quantization")
    return bool(
        value.get("circuit_version") == CIRCUIT_VERSION
        and value.get("curve") == "bn128"
        and value.get("public_signal_names") == list(PUBLIC_SIGNAL_NAMES)
        and value.get("verification_key_sha256") == verification_key_sha256
        and isinstance(value.get("constraint_count"), int)
        and value["constraint_count"] > 0
        and isinstance(quantization, dict)
        and quantization == {
            "scale": int(QUANTIZATION_SCALE),
            "signed_min": QUANTIZED_MIN,
            "signed_max": QUANTIZED_MAX,
            "chunk_size": CHUNK_SIZE,
        }
        and isinstance(value.get("development_only"), bool)
    )


def _read_bounded_file(path: Path, max_bytes: int) -> bytes:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > max_bytes:
        raise Groth16VerificationError("artifact_invalid", "Pinned Groth16 artifact is invalid.")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise Groth16VerificationError("artifact_invalid", "Pinned Groth16 artifact is invalid.") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value.lower()))


def _field_signal(value: object, name: str) -> str:
    if not isinstance(value, str) or not _DECIMAL_RE.fullmatch(value):
        raise Groth16VerificationError("malformed_proof", f"Groth16 {name} is invalid.")
    if int(value) >= BN254_SCALAR_FIELD:
        raise Groth16VerificationError("malformed_proof", f"Groth16 {name} is invalid.")
    return value


def _validate_proof_schema(proof: object, public_signals: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(proof, dict) or set(proof) != {"pi_a", "pi_b", "pi_c", "protocol", "curve"}:
        raise Groth16VerificationError("malformed_proof", "Groth16 proof schema is invalid.")
    if proof.get("protocol") != "groth16" or proof.get("curve") != "bn128":
        raise Groth16VerificationError("malformed_proof", "Groth16 proof schema is invalid.")
    coordinates = proof.get("pi_a"), proof.get("pi_b"), proof.get("pi_c")
    if (
        not isinstance(coordinates[0], list)
        or len(coordinates[0]) != 3
        or not isinstance(coordinates[1], list)
        or len(coordinates[1]) != 3
        or any(not isinstance(row, list) or len(row) != 2 for row in coordinates[1])
        or not isinstance(coordinates[2], list)
        or len(coordinates[2]) != 3
    ):
        raise Groth16VerificationError("malformed_proof", "Groth16 proof schema is invalid.")
    flat = [*coordinates[0], *(value for row in coordinates[1] for value in row), *coordinates[2]]
    for coordinate in flat:
        _field_signal(coordinate, "proof coordinate")
    if len(public_signals) != len(PUBLIC_SIGNAL_NAMES):
        raise Groth16VerificationError("malformed_proof", "Groth16 public signal count is invalid.")
    return tuple(_field_signal(value, "public signal") for value in public_signals)
