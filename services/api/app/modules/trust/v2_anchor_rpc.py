"""Strictly read-only Ethereum JSON-RPC adapter for the V2 receipt anchor.

The adapter is intentionally limited to a fixed ABI and a fixed allowlist of
read-only RPC calls. It has no signing, deployment, or transaction-submission
capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Protocol
import urllib.error
import urllib.request

from Crypto.Hash import keccak

from app.modules.trust.proof_receipt_anchor import (
    ChainReceiptLookupState,
    ProofReceiptAnchorReadConfig,
    ProofReceiptAnchorPayload,
)


V2_ANCHOR_ABI_VERSION = "neuroproof-receipt-anchor-v1"
_BYTES32_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")
_WORD_BYTES = 32
_RECEIPT_WORD_COUNT = 9
_EVENT_DATA_WORD_COUNT = 7
_READ_ONLY_METHODS = frozenset(
    {
        "eth_chainId",
        "eth_blockNumber",
        "eth_getCode",
        "eth_call",
        "eth_getTransactionReceipt",
        "eth_getTransactionByHash",
    }
)


class JsonRpcUnavailableError(RuntimeError):
    """The configured endpoint could not be reached safely."""


class JsonRpcMalformedResponseError(RuntimeError):
    """The endpoint returned an invalid JSON-RPC response."""


class JsonRpcRemoteError(RuntimeError):
    """The endpoint rejected an allowed read-only RPC call."""


class JsonRpcCaller(Protocol):
    """Minimal read-only RPC boundary, injectable for deterministic tests."""

    def call(self, method: str, params: list[object]) -> object:
        """Return the JSON-RPC result for a permitted read-only request."""


class EthereumJsonRpcClient:
    """Bounded JSON-RPC client that refuses all write-capable methods."""

    def __init__(self, rpc_url: str, *, timeout_seconds: int) -> None:
        if not rpc_url.startswith(("http://", "https://")):
            raise ValueError("RPC URL must use HTTP(S).")
        if timeout_seconds <= 0:
            raise ValueError("RPC timeout must be positive.")
        self._rpc_url = rpc_url
        self._timeout_seconds = timeout_seconds

    def call(self, method: str, params: list[object]) -> object:
        if method not in _READ_ONLY_METHODS:
            raise ValueError("Only allowlisted read-only Ethereum RPC methods are permitted.")

        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            self._rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                decoded = json.load(response)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise JsonRpcUnavailableError("The configured blockchain RPC endpoint is unavailable.") from exc
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise JsonRpcMalformedResponseError("The blockchain RPC response was malformed.") from exc

        if not isinstance(decoded, dict):
            raise JsonRpcMalformedResponseError("The blockchain RPC response was not an object.")
        if "error" in decoded:
            raise JsonRpcRemoteError("The blockchain RPC endpoint rejected a read-only request.")
        if "result" not in decoded:
            raise JsonRpcMalformedResponseError("The blockchain RPC response omitted a result.")
        return decoded["result"]


def ethereum_keccak256(value: bytes) -> bytes:
    """Return Ethereum Keccak-256, not the distinct NIST SHA3-256 function."""

    digest = keccak.new(digest_bits=256)
    digest.update(value)
    return digest.digest()


def _function_selector(signature: str) -> bytes:
    return ethereum_keccak256(signature.encode("ascii"))[:4]


def _event_topic(signature: str) -> str:
    return "0x" + ethereum_keccak256(signature.encode("ascii")).hex()


_RECEIPT_EXISTS_SELECTOR = _function_selector("receiptExists(bytes32)")
_GET_RECEIPT_SELECTOR = _function_selector("getReceipt(bytes32)")
_COMPUTE_RECEIPT_ID_SELECTOR = _function_selector(
    "computeReceiptId((bytes32,bytes32,bytes32,bytes32,bytes32))"
)
_RECEIPT_ANCHORED_TOPIC = _event_topic(
    "ReceiptAnchored(bytes32,bytes32,bytes32,bytes32,bytes32,bytes32,uint8,address,uint64,uint64)"
)


def _require_bytes32(value: str, field: str) -> str:
    if not isinstance(value, str) or not _BYTES32_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a 32-byte hexadecimal value.")
    return value.lower()


def _hex_bytes(value: object, field: str) -> bytes:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise JsonRpcMalformedResponseError(f"{field} was not hexadecimal.")
    raw = value[2:]
    if len(raw) % 2 or not re.fullmatch(r"[0-9a-fA-F]*", raw):
        raise JsonRpcMalformedResponseError(f"{field} was not valid hexadecimal.")
    return bytes.fromhex(raw)


def _hex_quantity(value: object, field: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise JsonRpcMalformedResponseError(f"{field} was not an Ethereum quantity.")
    return int(value, 16)


def _word_as_uint(word: bytes) -> int:
    if len(word) != _WORD_BYTES:
        raise JsonRpcMalformedResponseError("ABI return word had an invalid length.")
    return int.from_bytes(word, byteorder="big")


def _word_as_bytes32(word: bytes) -> str:
    if len(word) != _WORD_BYTES:
        raise JsonRpcMalformedResponseError("ABI return word had an invalid length.")
    return "0x" + word.hex()


def _word_as_address(word: bytes) -> str:
    if len(word) != _WORD_BYTES or any(word[:12]):
        raise JsonRpcMalformedResponseError("ABI address word was invalid.")
    return "0x" + word[12:].hex()


def _encode_static_call(selector: bytes, values: tuple[str, ...]) -> str:
    encoded_values = b"".join(bytes.fromhex(_require_bytes32(value, "ABI value")[2:]) for value in values)
    return "0x" + (selector + encoded_values).hex()


@dataclass(frozen=True)
class AnchoredProofReceipt:
    """Decoded immutable V2 anchor metadata; no proof or private update is returned."""

    federation_round_commitment: str
    model_version_commitment: str
    hospital_update_commitment: str
    proof_artifact_sha256: str
    verification_key_id: str
    attestation_status: str
    anchored_at: int
    anchored_block: int
    attested_by: str

    def payload(self) -> ProofReceiptAnchorPayload:
        return ProofReceiptAnchorPayload(
            federation_round_commitment=self.federation_round_commitment,
            model_version_commitment=self.model_version_commitment,
            hospital_update_commitment=self.hospital_update_commitment,
            proof_artifact_sha256=self.proof_artifact_sha256,
            verification_key_id=self.verification_key_id,
        )


@dataclass(frozen=True)
class V2AnchorReceiptInspection:
    """Explicit result of one read-only V2 anchor inspection."""

    state: ChainReceiptLookupState
    detail: str
    rpc_available: bool
    chain_id: int | None = None
    contract_address: str | None = None
    runtime_bytecode_sha256: str | None = None
    contract_identity_verified: bool = False
    receipt_id: str | None = None
    receipt: AnchoredProofReceipt | None = None
    transaction_hash: str | None = None
    transaction_block_number: int | None = None
    confirmations: int | None = None
    event_verified: bool = False
    onchain_groth16_verified: bool = False


class V2ProofReceiptAnchorReader:
    """Read the exact V2 ABI after pinning chain ID and runtime-bytecode SHA-256."""

    def __init__(
        self,
        configuration: ProofReceiptAnchorReadConfig,
        *,
        rpc_client: JsonRpcCaller | None = None,
        timeout_seconds: int = 3,
    ) -> None:
        self._configuration = configuration
        self._rpc = rpc_client or EthereumJsonRpcClient(
            configuration.rpc_url,
            timeout_seconds=timeout_seconds,
        )

    def inspect_receipt(
        self,
        *,
        receipt_id: str,
        transaction_hash: str | None = None,
    ) -> V2AnchorReceiptInspection:
        """Inspect a configured receipt without sending a chain transaction."""

        try:
            normalized_receipt_id = _require_bytes32(receipt_id, "receipt identifier")
        except ValueError:
            return self._result(
                ChainReceiptLookupState.INVALID_RECEIPT_ID,
                "Receipt identifier must be a 32-byte hexadecimal value.",
            )
        if transaction_hash is not None:
            try:
                transaction_hash = _require_bytes32(transaction_hash, "transaction hash")
            except ValueError:
                return self._result(
                    ChainReceiptLookupState.INVALID_TRANSACTION_HASH,
                    "Transaction hash must be a 32-byte hexadecimal value.",
                    receipt_id=normalized_receipt_id,
                )

        try:
            chain_id = _hex_quantity(self._rpc.call("eth_chainId", []), "chain ID")
        except JsonRpcUnavailableError:
            return self._result(
                ChainReceiptLookupState.UNAVAILABLE,
                "Configured blockchain RPC endpoint is unavailable.",
                rpc_available=False,
                receipt_id=normalized_receipt_id,
            )
        except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
            return self._result(
                ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                "Blockchain RPC returned an invalid read-only response.",
                receipt_id=normalized_receipt_id,
            )

        if chain_id != self._configuration.expected_chain_id:
            return self._result(
                ChainReceiptLookupState.CHAIN_ID_MISMATCH,
                "Configured blockchain chain ID does not match the trusted deployment.",
                receipt_id=normalized_receipt_id,
                chain_id=chain_id,
            )

        address = self._configuration.contract_address.lower()
        try:
            runtime_code = _hex_bytes(
                self._rpc.call("eth_getCode", [address, "latest"]),
                "runtime bytecode",
            )
        except JsonRpcUnavailableError:
            return self._result(
                ChainReceiptLookupState.UNAVAILABLE,
                "Configured blockchain RPC endpoint is unavailable.",
                rpc_available=False,
                receipt_id=normalized_receipt_id,
                chain_id=chain_id,
            )
        except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
            return self._result(
                ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                "Blockchain RPC returned invalid contract bytecode.",
                receipt_id=normalized_receipt_id,
                chain_id=chain_id,
            )

        if not runtime_code:
            return self._result(
                ChainReceiptLookupState.CONTRACT_CODE_MISSING,
                "No contract bytecode exists at the configured address.",
                receipt_id=normalized_receipt_id,
                chain_id=chain_id,
                contract_address=address,
            )
        runtime_hash = sha256(runtime_code).hexdigest()
        if runtime_hash.lower() != self._configuration.expected_runtime_code_sha256.lower():
            return self._result(
                ChainReceiptLookupState.CONTRACT_RUNTIME_MISMATCH,
                "Configured contract runtime bytecode does not match the trusted SHA-256.",
                receipt_id=normalized_receipt_id,
                chain_id=chain_id,
                contract_address=address,
                runtime_bytecode_sha256=runtime_hash,
            )

        identity = {
            "chain_id": chain_id,
            "contract_address": address,
            "runtime_bytecode_sha256": runtime_hash,
            "contract_identity_verified": True,
            "receipt_id": normalized_receipt_id,
        }
        try:
            exists = self._receipt_exists(address, normalized_receipt_id)
        except JsonRpcUnavailableError:
            return self._result(
                ChainReceiptLookupState.UNAVAILABLE,
                "Configured blockchain RPC endpoint is unavailable.",
                rpc_available=False,
                **identity,
            )
        except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
            return self._result(
                ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                "Blockchain RPC returned an invalid receipt lookup response.",
                **identity,
            )

        if not exists:
            return self._result(
                ChainReceiptLookupState.RECEIPT_MISSING,
                "No receipt exists for the requested V2 receipt identifier.",
                **identity,
            )

        try:
            receipt = self._read_receipt(address, normalized_receipt_id)
            computed_receipt_id = self._compute_receipt_id(address, receipt.payload())
        except JsonRpcUnavailableError:
            return self._result(
                ChainReceiptLookupState.UNAVAILABLE,
                "Configured blockchain RPC endpoint is unavailable.",
                rpc_available=False,
                **identity,
            )
        except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
            return self._result(
                ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                "Blockchain RPC returned invalid V2 receipt metadata.",
                **identity,
            )

        if computed_receipt_id != normalized_receipt_id:
            return self._result(
                ChainReceiptLookupState.RECEIPT_MISMATCH,
                "Stored receipt commitments do not reproduce the requested receipt identifier.",
                receipt=receipt,
                **identity,
            )

        if transaction_hash is None:
            return self._result(
                ChainReceiptLookupState.RECEIPT_FOUND,
                "Receipt storage and canonical V2 identifier were verified; no transaction was supplied.",
                receipt=receipt,
                **identity,
            )
        return self._inspect_transaction(
            address=address,
            receipt_id_for_event=normalized_receipt_id,
            receipt=receipt,
            transaction_hash=transaction_hash,
            **identity,
        )

    def _receipt_exists(self, address: str, receipt_id: str) -> bool:
        data = _encode_static_call(_RECEIPT_EXISTS_SELECTOR, (receipt_id,))
        raw = _hex_bytes(self._rpc.call("eth_call", [{"to": address, "data": data}, "latest"]), "receipt existence")
        if len(raw) != _WORD_BYTES:
            raise JsonRpcMalformedResponseError("receiptExists returned an invalid ABI length.")
        value = _word_as_uint(raw)
        if value not in {0, 1}:
            raise JsonRpcMalformedResponseError("receiptExists returned a non-boolean value.")
        return bool(value)

    def _read_receipt(self, address: str, receipt_id: str) -> AnchoredProofReceipt:
        data = _encode_static_call(_GET_RECEIPT_SELECTOR, (receipt_id,))
        raw = _hex_bytes(self._rpc.call("eth_call", [{"to": address, "data": data}, "latest"]), "receipt metadata")
        if len(raw) != _RECEIPT_WORD_COUNT * _WORD_BYTES:
            raise JsonRpcMalformedResponseError("getReceipt returned an invalid ABI length.")
        words = tuple(raw[offset : offset + _WORD_BYTES] for offset in range(0, len(raw), _WORD_BYTES))
        status = _word_as_uint(words[5])
        if status != 0:
            raise JsonRpcMalformedResponseError("Unsupported V2 receipt attestation status.")
        return AnchoredProofReceipt(
            federation_round_commitment=_word_as_bytes32(words[0]),
            model_version_commitment=_word_as_bytes32(words[1]),
            hospital_update_commitment=_word_as_bytes32(words[2]),
            proof_artifact_sha256=_word_as_bytes32(words[3]),
            verification_key_id=_word_as_bytes32(words[4]),
            attestation_status="offchain_groth16_verified",
            anchored_at=_word_as_uint(words[6]),
            anchored_block=_word_as_uint(words[7]),
            attested_by=_word_as_address(words[8]),
        )

    def _compute_receipt_id(self, address: str, payload: ProofReceiptAnchorPayload) -> str:
        data = _encode_static_call(
            _COMPUTE_RECEIPT_ID_SELECTOR,
            (
                payload.federation_round_commitment,
                payload.model_version_commitment,
                payload.hospital_update_commitment,
                payload.proof_artifact_sha256,
                payload.verification_key_id,
            ),
        )
        raw = _hex_bytes(self._rpc.call("eth_call", [{"to": address, "data": data}, "latest"]), "computed receipt identifier")
        if len(raw) != _WORD_BYTES:
            raise JsonRpcMalformedResponseError("computeReceiptId returned an invalid ABI length.")
        return _word_as_bytes32(raw)

    def _inspect_transaction(
        self,
        *,
        address: str,
        receipt_id_for_event: str,
        receipt: AnchoredProofReceipt,
        transaction_hash: str,
        **identity: object,
    ) -> V2AnchorReceiptInspection:
        try:
            transaction_receipt = self._rpc.call("eth_getTransactionReceipt", [transaction_hash])
        except JsonRpcUnavailableError:
            return self._result(
                ChainReceiptLookupState.UNAVAILABLE,
                "Configured blockchain RPC endpoint is unavailable.",
                rpc_available=False,
                receipt=receipt,
                transaction_hash=transaction_hash,
                **identity,
            )
        except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
            return self._result(
                ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                "Blockchain RPC returned an invalid transaction receipt response.",
                receipt=receipt,
                transaction_hash=transaction_hash,
                **identity,
            )

        if transaction_receipt is None:
            try:
                transaction = self._rpc.call("eth_getTransactionByHash", [transaction_hash])
            except JsonRpcUnavailableError:
                return self._result(
                    ChainReceiptLookupState.UNAVAILABLE,
                    "Configured blockchain RPC endpoint is unavailable.",
                    rpc_available=False,
                    receipt=receipt,
                    transaction_hash=transaction_hash,
                    **identity,
                )
            except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
                return self._result(
                    ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                    "Blockchain RPC returned an invalid pending transaction response.",
                    receipt=receipt,
                    transaction_hash=transaction_hash,
                    **identity,
                )
            state = (
                ChainReceiptLookupState.TRANSACTION_PENDING
                if isinstance(transaction, dict)
                else ChainReceiptLookupState.TRANSACTION_MISSING
            )
            detail = (
                "Anchor transaction is pending confirmation."
                if state is ChainReceiptLookupState.TRANSACTION_PENDING
                else "No transaction exists for the supplied transaction hash."
            )
            return self._result(state, detail, receipt=receipt, transaction_hash=transaction_hash, **identity)

        try:
            block_number, event_verified = self._validate_anchor_transaction(
                transaction_receipt,
                address=address,
                receipt_id=receipt_id_for_event,
                receipt=receipt,
            )
            latest_block = _hex_quantity(self._rpc.call("eth_blockNumber", []), "latest block")
        except (JsonRpcMalformedResponseError, JsonRpcRemoteError, TypeError, ValueError):
            return self._result(
                ChainReceiptLookupState.EVENT_MISMATCH,
                "Transaction receipt does not contain matching V2 anchor event metadata.",
                receipt=receipt,
                transaction_hash=transaction_hash,
                **identity,
            )
        confirmations = latest_block - block_number + 1
        if confirmations < 1:
            return self._result(
                ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                "Transaction block is ahead of the reported latest block.",
                receipt=receipt,
                transaction_hash=transaction_hash,
                transaction_block_number=block_number,
                **identity,
            )
        if confirmations < self._configuration.required_confirmations:
            return self._result(
                ChainReceiptLookupState.TRANSACTION_PENDING,
                "Anchor transaction has not reached the configured confirmation count.",
                receipt=receipt,
                transaction_hash=transaction_hash,
                transaction_block_number=block_number,
                confirmations=confirmations,
                event_verified=event_verified,
                **identity,
            )
        return self._result(
            ChainReceiptLookupState.CONFIRMED,
            "V2 anchor receipt, event, and transaction confirmation were verified read-only.",
            receipt=receipt,
            transaction_hash=transaction_hash,
            transaction_block_number=block_number,
            confirmations=confirmations,
            event_verified=event_verified,
            **identity,
        )

    def _validate_anchor_transaction(
        self,
        transaction_receipt: object,
        *,
        address: str,
        receipt_id: str,
        receipt: AnchoredProofReceipt,
    ) -> tuple[int, bool]:
        if not isinstance(transaction_receipt, dict):
            raise JsonRpcMalformedResponseError("Transaction receipt was not an object.")
        if transaction_receipt.get("status") != "0x1":
            raise JsonRpcMalformedResponseError("Anchor transaction did not succeed.")
        block_number = _hex_quantity(transaction_receipt.get("blockNumber"), "transaction block")
        logs = transaction_receipt.get("logs")
        if not isinstance(logs, list):
            raise JsonRpcMalformedResponseError("Transaction receipt omitted logs.")
        for log in logs:
            if not isinstance(log, dict) or str(log.get("address", "")).lower() != address:
                continue
            topics = log.get("topics")
            if not isinstance(topics, list) or len(topics) != 4:
                continue
            if str(topics[0]).lower() != _RECEIPT_ANCHORED_TOPIC:
                continue
            try:
                event_receipt_id = _require_bytes32(str(topics[1]), "event receipt identifier")
                event_round = _require_bytes32(str(topics[2]), "event round commitment")
                event_update = _require_bytes32(str(topics[3]), "event update commitment")
                raw = _hex_bytes(log.get("data"), "event data")
            except (TypeError, ValueError, JsonRpcMalformedResponseError):
                continue
            if len(raw) != _EVENT_DATA_WORD_COUNT * _WORD_BYTES:
                continue
            words = tuple(raw[offset : offset + _WORD_BYTES] for offset in range(0, len(raw), _WORD_BYTES))
            try:
                event_status = _word_as_uint(words[3])
                event_matches = (
                    event_receipt_id == receipt_id
                    and event_round == receipt.federation_round_commitment
                    and event_update == receipt.hospital_update_commitment
                    and _word_as_bytes32(words[0]) == receipt.model_version_commitment
                    and _word_as_bytes32(words[1]) == receipt.proof_artifact_sha256
                    and _word_as_bytes32(words[2]) == receipt.verification_key_id
                    and event_status == 0
                    and _word_as_address(words[4]) == receipt.attested_by
                    and _word_as_uint(words[5]) == receipt.anchored_at
                    and _word_as_uint(words[6]) == receipt.anchored_block
                    and receipt.anchored_block == block_number
                )
            except JsonRpcMalformedResponseError:
                continue
            if event_matches:
                return block_number, True
        raise JsonRpcMalformedResponseError("Matching ReceiptAnchored event was not found.")

    @staticmethod
    def _result(
        state: ChainReceiptLookupState,
        detail: str,
        *,
        rpc_available: bool = True,
        **kwargs: object,
    ) -> V2AnchorReceiptInspection:
        return V2AnchorReceiptInspection(
            state=state,
            detail=detail,
            rpc_available=rpc_available,
            **kwargs,
        )
