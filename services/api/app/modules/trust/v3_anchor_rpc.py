"""Read-only adapter for V3 development-only receipt attestations.

V3 is deliberately separate from the existing V2 API and contract.

The deployed runtime hash must be independently pinned before use.
A recorded attestation is not proof that Groth16 was verified on-chain.

No private keys, signing, deployment, or transaction submission exist here.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

from app.modules.trust.proof_receipt_anchor import (
    ChainReceiptLookupState,
    ProofReceiptAnchorReadConfig,
)
from app.modules.trust.v2_anchor_rpc import (
    AnchoredProofReceipt,
    EthereumJsonRpcClient,
    JsonRpcCaller,
    JsonRpcMalformedResponseError,
    JsonRpcRemoteError,
    JsonRpcUnavailableError,
    V2AnchorReceiptInspection,
    V2ProofReceiptAnchorReader,
    ethereum_keccak256,
)


V3_ANCHOR_ABI_VERSION = "neuroproof-receipt-anchor-v3"

V3_CLASSIFICATION = "development_synthetic_offchain_verified"

V3_RECEIPT_DOMAIN = (
    "cerebrachain-v3:"
    "development-synthetic-proof-receipt-anchor:v1"
)


def _selector(signature: str) -> str:
    """Return the standard four-byte Ethereum function selector."""
    digest = ethereum_keccak256(signature.encode("ascii"))
    return "0x" + digest[:4].hex()


def _abi_string(value: str) -> str:
    """Encode the return value of a zero-argument Solidity string getter."""
    data = value.encode("utf-8")
    padding = (-len(data)) % 32

    result = (
        (32).to_bytes(32, "big")
        + len(data).to_bytes(32, "big")
        + data
        + bytes(padding)
    )

    return "0x" + result.hex()


def _abi_bool(value: bool) -> str:
    return "0x" + int(value).to_bytes(32, "big").hex()


def _abi_bytes32(value: bytes) -> str:
    if len(value) != 32:
        raise ValueError("Expected a bytes32 value.")

    return "0x" + value.hex()


@dataclass(frozen=True)
class V3AnchorReceiptInspection(V2AnchorReceiptInspection):
    """V3 result with explicit development-only classification.

    verified_classification is populated only after V3 identity checks.
    It does not assert independent Groth16 verification.
    """

    verified_classification: str | None = None
    production_eligible: bool = False


class V3ProofReceiptAnchorReader(V2ProofReceiptAnchorReader):
    """Inspect V3 receipts using the audited read-only V2 ABI machinery.

    V3 intentionally retains the V2 receipt tuple and event ABI.
    The canonical ID is computed by the deployed V3 contract, which
    uses a distinct receipt domain.

    Separate runtime-bytecode pinning is mandatory.
    """

    def __init__(
        self,
        configuration: ProofReceiptAnchorReadConfig,
        *,
        rpc_client: JsonRpcCaller | None = None,
        timeout_seconds: int = 3,
    ) -> None:
        super().__init__(
            configuration,
            rpc_client=rpc_client,
            timeout_seconds=timeout_seconds,
        )

    def _read_receipt(
        self,
        address: str,
        receipt_id: str,
    ) -> AnchoredProofReceipt:
        """Decode the common ABI but never expose the V2 status label."""

        receipt = super()._read_receipt(
            address,
            receipt_id,
        )

        return replace(
            receipt,
            attestation_status=V3_CLASSIFICATION,
        )

    def _verify_v3_identity(self, address: str) -> None:
        """Verify V3-specific constant getters after code-hash pinning."""

        expected = {
            "RECEIPT_DOMAIN()": _abi_bytes32(
                ethereum_keccak256(
                    V3_RECEIPT_DOMAIN.encode("ascii")
                )
            ),
            "ATTESTATION_CLASSIFICATION()": _abi_string(
                V3_CLASSIFICATION
            ),
            "PRODUCTION_ELIGIBLE()": _abi_bool(False),
            "ONCHAIN_GROTH16_VERIFIED()": _abi_bool(False),
        }

        for signature, required in expected.items():
            actual = self._rpc.call(
                "eth_call",
                [
                    {
                        "to": address,
                        "data": _selector(signature),
                    },
                    "latest",
                ],
            )

            if not isinstance(actual, str):
                raise JsonRpcMalformedResponseError(
                    "V3 identity getter returned an invalid type."
                )

            if actual.lower() != required.lower():
                raise JsonRpcMalformedResponseError(
                    "V3 contract classification or ABI identity mismatch."
                )

    @staticmethod
    def _as_v3_result(
        inspection: V2AnchorReceiptInspection,
        *,
        classification_verified: bool,
    ) -> V3AnchorReceiptInspection:

        data = {
            field.name: getattr(inspection, field.name)
            for field in fields(V2AnchorReceiptInspection)
        }

        return V3AnchorReceiptInspection(
            **data,
            verified_classification=(
                V3_CLASSIFICATION
                if classification_verified
                else None
            ),
            production_eligible=False,
        )

    def inspect_receipt(
        self,
        *,
        receipt_id: str,
        transaction_hash: str | None = None,
    ) -> V3AnchorReceiptInspection:
        """Inspect V3 state; fail closed on contract identity mismatch."""

        inspection = super().inspect_receipt(
            receipt_id=receipt_id,
            transaction_hash=transaction_hash,
        )

        if not inspection.contract_identity_verified:
            return self._as_v3_result(
                inspection,
                classification_verified=False,
            )

        if inspection.contract_address is None:
            failed = replace(
                inspection,
                state=ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                detail="V3 contract address is missing.",
                contract_identity_verified=False,
                receipt=None,
                event_verified=False,
            )

            return self._as_v3_result(
                failed,
                classification_verified=False,
            )

        try:
            self._verify_v3_identity(
                inspection.contract_address
            )

        except JsonRpcUnavailableError:
            failed = replace(
                inspection,
                state=ChainReceiptLookupState.UNAVAILABLE,
                detail="V3 blockchain RPC is unavailable.",
                rpc_available=False,
                contract_identity_verified=False,
                receipt=None,
                event_verified=False,
            )

            return self._as_v3_result(
                failed,
                classification_verified=False,
            )

        except (
            JsonRpcMalformedResponseError,
            JsonRpcRemoteError,
            TypeError,
            ValueError,
        ):
            failed = replace(
                inspection,
                state=ChainReceiptLookupState.MALFORMED_RPC_RESPONSE,
                detail=(
                    "V3 contract classification or ABI "
                    "identity could not be verified."
                ),
                contract_identity_verified=False,
                receipt=None,
                event_verified=False,
            )

            return self._as_v3_result(
                failed,
                classification_verified=False,
            )

        inspection = replace(
            inspection,
            detail=inspection.detail.replace("V2", "V3"),
        )

        return self._as_v3_result(
            inspection,
            classification_verified=True,
        )
