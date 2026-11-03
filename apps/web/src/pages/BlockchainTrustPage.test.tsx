/**
 * Synthetic UI coverage for the protected V2 receipt lookup.
 * No real chain, wallet, proof, hospital record, or MRI data is used.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BlockchainTrustPage } from "./BlockchainTrustPage";
import { getV2LookupErrorMessage } from "../utils/trustLookup";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

vi.mock("../services/apiClient", () => ({
  apiClient: { request: requestMock },
}));

const RECEIPT_ID = `0x${"a".repeat(64)}`;
const TRANSACTION_HASH = `0x${"b".repeat(64)}`;

function historicalSummary() {
  return {
    network: { rpc_available: false, chain_id: null, latest_block: null, genesis_matches: false },
    contract: { name: null, address: null, runtime_hash_matches: false, code_present: false },
    transactions: { deployment_hash: null, deployment_confirmed: false, anchoring_hash: null, anchoring_confirmed: false },
    proof_evidence: {
      recorded_jobs: null,
      proofset_total: null,
      hospital_count: null,
      merkle_root_matches_historical_record: false,
      merkle_root: null,
      historical_blockchain_anchored_flag: false,
      onchain_proof_verification_count: 0,
      proofs_reverified_during_anchoring: 0,
      verification_scope: null,
    },
    verification: { current_anchor_transaction_confirmed: false, individual_groth16_proofs_verified_live: false },
    disclaimer: "Synthetic historical trust response.",
  };
}

function lookup(state: string, overrides: Record<string, unknown> = {}) {
  return {
    state,
    detail: `Synthetic ${state} result.`,
    rpc_available: state !== "unconfigured" && state !== "unavailable",
    chain_id: state === "unconfigured" ? null : 31337,
    contract_address: state === "unconfigured" ? null : `0x${"1".repeat(40)}`,
    runtime_bytecode_sha256: state === "unconfigured" ? null : "2".repeat(64),
    contract_identity_verified: state === "confirmed",
    receipt_id: RECEIPT_ID,
    receipt: null,
    transaction_hash: null,
    transaction_block_number: null,
    confirmations: null,
    event_verified: false,
    offchain_groth16_verified: false,
    onchain_groth16_verified: false,
    ...overrides,
  };
}

function setupLookup(result: unknown | Error | { status: number }) {
  requestMock.mockImplementation((path: string) => {
    if (path === "/trust/summary") return Promise.resolve(historicalSummary());
    if (result instanceof Error || (typeof result === "object" && result !== null && "status" in result)) {
      return Promise.resolve().then(() => {
        throw result;
      });
    }
    return Promise.resolve(result);
  });
}

async function submitLookup(transactionHash = "") {
  fireEvent.change(screen.getByLabelText(/Receipt ID/), { target: { value: RECEIPT_ID } });
  if (transactionHash) {
    fireEvent.change(screen.getByLabelText(/Anchoring transaction hash/), {
      target: { value: transactionHash },
    });
  }
  fireEvent.click(screen.getByRole("button", { name: "Check V2 receipt" }));
}

describe("Blockchain trust V2 receipt lookup", () => {
  beforeEach(() => requestMock.mockReset());
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders an unconfigured V2 anchor result without claiming verification", async () => {
    setupLookup(lookup("unconfigured"));
    render(<BlockchainTrustPage />);

    await submitLookup();

    expect(await screen.findByText("V2 anchor not configured")).toBeInTheDocument();
    expect(screen.getByText(/On-chain Groth16 proof verification:/)).toHaveTextContent("Not performed");
  });

  it("maps receipt-viewer authorization failure without bypassing the protected API", () => {
    expect(getV2LookupErrorMessage({ status: 403 })).toBe("Receipt Viewer access is required for V2 receipt lookup.");
  });

  it("marks an invalid receipt identifier invalid before lookup submission", () => {
    setupLookup(lookup("receipt_missing"));
    render(<BlockchainTrustPage />);

    const receiptInput = screen.getByLabelText(/Receipt ID/) as HTMLInputElement;
    fireEvent.change(receiptInput, { target: { value: "not-a-receipt" } });

    expect(receiptInput.checkValidity()).toBe(false);
  });

  it.each([
    ["receipt_missing", "No on-chain receipt found"],
    ["chain_id_mismatch", "Unexpected blockchain network"],
    ["contract_runtime_mismatch", "Contract bytecode mismatch"],
    ["unavailable", "Blockchain RPC unavailable"],
    ["transaction_pending", "Transaction awaiting confirmations"],
  ])("renders explicit non-confirmed state %s", async (state, label) => {
    setupLookup(lookup(state));
    render(<BlockchainTrustPage />);

    await submitLookup(TRANSACTION_HASH);

    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByText(/Anchoring transaction:/)).toHaveTextContent("Not confirmed by lookup");
  });

  it("renders a confirmed synthetic receipt while preserving verification-scope limits", async () => {
    setupLookup(lookup("confirmed", {
      contract_identity_verified: true,
      event_verified: true,
      transaction_hash: TRANSACTION_HASH,
      transaction_block_number: 12,
      confirmations: 2,
      offchain_groth16_verified: true,
      receipt: {
        federation_round_commitment: `0x${"3".repeat(64)}`,
        model_version_commitment: `0x${"4".repeat(64)}`,
        hospital_update_commitment: `0x${"5".repeat(64)}`,
        proof_artifact_sha256: `0x${"6".repeat(64)}`,
        verification_key_id: `0x${"7".repeat(64)}`,
        attestation_status: "offchain_groth16_verified",
        anchored_at: 123,
        anchored_block: 12,
        attested_by: `0x${"8".repeat(40)}`,
      },
    }));
    render(<BlockchainTrustPage />);

    await submitLookup(TRANSACTION_HASH);

    expect(await screen.findByText("Anchoring transaction confirmed")).toBeInTheDocument();
    expect(screen.getByText("Immutable on-chain receipt metadata")).toBeInTheDocument();
    expect(screen.getByText(/Off-chain Groth16 verification attested by this receipt:/)).toHaveTextContent("Claim recorded on-chain");
    expect(screen.getByText(/On-chain Groth16 proof verification:/)).toHaveTextContent("Not performed");
  });
});
