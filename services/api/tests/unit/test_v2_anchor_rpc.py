"""Synthetic unit coverage for V2's strictly read-only Ethereum receipt adapter."""

from __future__ import annotations

from hashlib import sha256

import pytest

from app.modules.trust.proof_receipt_anchor import (
    ChainReceiptLookupState,
    ProofReceiptAnchorReadConfig,
)
from app.modules.trust.v2_anchor_rpc import (
    JsonRpcUnavailableError,
    V2ProofReceiptAnchorReader,
    _COMPUTE_RECEIPT_ID_SELECTOR,
    _EVENT_DATA_WORD_COUNT,
    _GET_RECEIPT_SELECTOR,
    _RECEIPT_ANCHORED_TOPIC,
    _RECEIPT_EXISTS_SELECTOR,
    ethereum_keccak256,
)


ADDRESS = "0x" + "1" * 40
RECEIPT_ID = "0x" + "2" * 64
ROUND = "0x" + "3" * 64
MODEL = "0x" + "4" * 64
UPDATE = "0x" + "5" * 64
PROOF = "0x" + "6" * 64
KEY = "0x" + "7" * 64
ATTESTED_BY = "0x" + "8" * 40
TX_HASH = "0x" + "9" * 64
RUNTIME_CODE = "0x60006000"


def _word(value: int | str) -> str:
    if isinstance(value, int):
        return f"{value:064x}"
    return value.removeprefix("0x").lower().rjust(64, "0")


def _receipt_return() -> str:
    return "0x" + "".join(
        (
            _word(ROUND),
            _word(MODEL),
            _word(UPDATE),
            _word(PROOF),
            _word(KEY),
            _word(0),
            _word(123),
            _word(7),
            _word(ATTESTED_BY),
        )
    )


def _event_data(*, proof_hash: str = PROOF) -> str:
    values = (
        _word(MODEL),
        _word(proof_hash),
        _word(KEY),
        _word(0),
        _word(ATTESTED_BY),
        _word(123),
        _word(7),
    )
    assert len(values) == _EVENT_DATA_WORD_COUNT
    return "0x" + "".join(values)


class ScriptedRpc:
    def __init__(
        self,
        *,
        chain_id: str = "0x7a69",
        runtime_code: object = RUNTIME_CODE,
        receipt_exists: str = "0x" + _word(1),
        event_data: str | None = None,
        latest_block: str = "0x7",
    ) -> None:
        self.chain_id = chain_id
        self.runtime_code = runtime_code
        self.receipt_exists = receipt_exists
        self.event_data = event_data or _event_data()
        self.latest_block = latest_block

    def call(self, method: str, params: list[object]) -> object:
        if method == "eth_chainId":
            return self.chain_id
        if method == "eth_getCode":
            return self.runtime_code
        if method == "eth_call":
            data = params[0]["data"]  # type: ignore[index]
            selector = bytes.fromhex(data[2:10])
            if selector == _RECEIPT_EXISTS_SELECTOR:
                return self.receipt_exists
            if selector == _GET_RECEIPT_SELECTOR:
                return _receipt_return()
            if selector == _COMPUTE_RECEIPT_ID_SELECTOR:
                return RECEIPT_ID
            raise AssertionError(f"Unexpected eth_call selector: {selector.hex()}")
        if method == "eth_getTransactionReceipt":
            return {
                "status": "0x1",
                "blockNumber": "0x7",
                "logs": [
                    {
                        "address": ADDRESS,
                        "topics": [_RECEIPT_ANCHORED_TOPIC, RECEIPT_ID, ROUND, UPDATE],
                        "data": self.event_data,
                    }
                ],
            }
        if method == "eth_blockNumber":
            return self.latest_block
        raise AssertionError(f"Unexpected RPC method: {method}")


def _config(*, expected_chain_id: int = 31337, runtime_hash: str | None = None, confirmations: int = 1):
    return ProofReceiptAnchorReadConfig(
        rpc_url="http://127.0.0.1:18545",
        expected_chain_id=expected_chain_id,
        contract_address=ADDRESS,
        expected_runtime_code_sha256=runtime_hash or sha256(bytes.fromhex(RUNTIME_CODE[2:])).hexdigest(),
        required_confirmations=confirmations,
    )


def _reader(rpc: ScriptedRpc, **kwargs: object) -> V2ProofReceiptAnchorReader:
    return V2ProofReceiptAnchorReader(_config(**kwargs), rpc_client=rpc)


def test_ethereum_keccak_uses_the_ethereum_reference_algorithm() -> None:
    assert ethereum_keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"


def test_reads_confirmed_receipt_and_matching_event_metadata() -> None:
    result = _reader(ScriptedRpc()).inspect_receipt(receipt_id=RECEIPT_ID, transaction_hash=TX_HASH)

    assert result.state is ChainReceiptLookupState.CONFIRMED
    assert result.contract_identity_verified is True
    assert result.event_verified is True
    assert result.confirmations == 1
    assert result.receipt is not None
    assert result.receipt.hospital_update_commitment == UPDATE


@pytest.mark.parametrize(
    ("reader", "receipt_id", "expected"),
    [
        (_reader(ScriptedRpc(), expected_chain_id=1), RECEIPT_ID, ChainReceiptLookupState.CHAIN_ID_MISMATCH),
        (_reader(ScriptedRpc(runtime_code="0x")), RECEIPT_ID, ChainReceiptLookupState.CONTRACT_CODE_MISSING),
        (_reader(ScriptedRpc(), runtime_hash="a" * 64), RECEIPT_ID, ChainReceiptLookupState.CONTRACT_RUNTIME_MISMATCH),
        (_reader(ScriptedRpc(receipt_exists="0x" + _word(0))), RECEIPT_ID, ChainReceiptLookupState.RECEIPT_MISSING),
        (_reader(ScriptedRpc()), "not-a-receipt-id", ChainReceiptLookupState.INVALID_RECEIPT_ID),
        (_reader(ScriptedRpc(runtime_code=123)), RECEIPT_ID, ChainReceiptLookupState.MALFORMED_RPC_RESPONSE),
    ],
)
def test_rejects_inconsistent_or_invalid_chain_data(
    reader: V2ProofReceiptAnchorReader,
    receipt_id: str,
    expected: ChainReceiptLookupState,
) -> None:
    assert reader.inspect_receipt(receipt_id=receipt_id).state is expected


def test_rejects_mismatched_event_metadata() -> None:
    result = _reader(ScriptedRpc(event_data=_event_data(proof_hash="0x" + "a" * 64))).inspect_receipt(
        receipt_id=RECEIPT_ID,
        transaction_hash=TX_HASH,
    )

    assert result.state is ChainReceiptLookupState.EVENT_MISMATCH


def test_reports_pending_when_confirmations_are_below_policy() -> None:
    result = _reader(ScriptedRpc(), confirmations=2).inspect_receipt(
        receipt_id=RECEIPT_ID,
        transaction_hash=TX_HASH,
    )

    assert result.state is ChainReceiptLookupState.TRANSACTION_PENDING
    assert result.event_verified is True


def test_reports_unavailable_rpc_without_throwing() -> None:
    class UnavailableRpc:
        def call(self, method: str, params: list[object]) -> object:
            del method, params
            raise JsonRpcUnavailableError("synthetic timeout")

    reader = V2ProofReceiptAnchorReader(_config(), rpc_client=UnavailableRpc())
    assert reader.inspect_receipt(receipt_id=RECEIPT_ID).state is ChainReceiptLookupState.UNAVAILABLE
