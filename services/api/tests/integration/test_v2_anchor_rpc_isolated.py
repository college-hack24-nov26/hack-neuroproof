"""Real adapter integration against a fresh, disposable loopback Hardhat node.

The test is skipped unless the caller explicitly supplies the already-installed
local test tooling paths. It never uses port 8545, persistent chains, or a
database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

import pytest

from app.modules.trust.proof_receipt_anchor import (
    ChainReceiptLookupState,
    ProofReceiptAnchorReadConfig,
)
from app.modules.trust.v2_anchor_rpc import V2ProofReceiptAnchorReader


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_ROOT = PROJECT_ROOT / "packages" / "contracts"


def _configured_tool(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        pytest.skip(f"{name} is not configured for isolated EVM testing.")
    return value


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_hardhat(rpc_url: str) -> None:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}).encode()
    for _ in range(80):
        try:
            request = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=1) as response:
                if json.load(response).get("result") == "0x7a69":
                    return
        except OSError:
            time.sleep(0.125)
    pytest.fail("Disposable Hardhat node did not become ready.")


def test_reader_validates_a_real_synthetic_v2_anchor_on_ephemeral_evm() -> None:
    hardhat_binary = _configured_tool("CEREBRACHAIN_TEST_HARDHAT_BIN")
    node_path = _configured_tool("CEREBRACHAIN_TEST_CONTRACTS_NODE_PATH")
    node_binary = os.getenv("CEREBRACHAIN_TEST_NODE_BIN", "node")
    port = _unused_port()
    rpc_url = f"http://127.0.0.1:{port}"
    environment = {**os.environ, "NODE_PATH": node_path}
    process = subprocess.Popen(
        [hardhat_binary, "node", "--hostname", "127.0.0.1", "--port", str(port)],
        cwd=CONTRACTS_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_hardhat(rpc_url)
        deployed = subprocess.run(
            [node_binary, "scripts/deploy-synthetic-anchor.cjs", "--rpc-url", rpc_url],
            cwd=CONTRACTS_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        metadata = json.loads(deployed.stdout)
        reader = V2ProofReceiptAnchorReader(
            ProofReceiptAnchorReadConfig(
                rpc_url=rpc_url,
                expected_chain_id=metadata["chainId"],
                contract_address=metadata["contractAddress"],
                expected_runtime_code_sha256=metadata["runtimeCodeSha256"],
                required_confirmations=1,
            ),
            timeout_seconds=3,
        )

        result = reader.inspect_receipt(
            receipt_id=metadata["receiptId"],
            transaction_hash=metadata["anchorTransactionHash"],
        )

        assert result.state is ChainReceiptLookupState.CONFIRMED
        assert result.contract_identity_verified is True
        assert result.event_verified is True
        assert result.transaction_block_number == metadata["anchorBlockNumber"]
        assert result.receipt is not None
        assert result.receipt.proof_artifact_sha256 == metadata["commitments"]["proofArtifactSha256"].lower()
        assert result.onchain_groth16_verified is False
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
