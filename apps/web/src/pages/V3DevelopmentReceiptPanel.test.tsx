/**
 * Isolated UI tests; no live chain, wallet, password, JWT, or MRI data.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { V3DevelopmentReceiptPanel } from "./V3DevelopmentReceiptPanel";

const { requestMock } = vi.hoisted(() => ({
  requestMock: vi.fn(),
}));

vi.mock("../services/apiClient", () => ({
  apiClient: { request: requestMock },
}));

const ID = `0x${"a".repeat(64)}`;
const TX = `0x${"b".repeat(64)}`;

function receiptResult(overrides: Record<string, unknown> = {}) {
  return {
    state: "confirmed",
    detail: "Synthetic V3 receipt confirmed.",
    rpc_available: true,
    chain_id: 31337,
    contract_address: `0x${"1".repeat(40)}`,
    runtime_bytecode_sha256: "2".repeat(64),
    contract_identity_verified: true,
    receipt_id: ID,
    receipt: {
      federation_round_commitment: `0x${"3".repeat(64)}`,
      model_version_commitment: `0x${"4".repeat(64)}`,
      hospital_update_commitment: `0x${"5".repeat(64)}`,
      proof_artifact_sha256: `0x${"6".repeat(64)}`,
      verification_key_id: `0x${"7".repeat(64)}`,
      attestation_status: "development_synthetic_offchain_verified",
      anchored_at: 123,
      anchored_block: 3,
      attested_by: `0x${"8".repeat(40)}`,
    },
    transaction_hash: TX,
    transaction_block_number: 3,
    confirmations: 1,
    event_verified: true,
    verified_classification: "development_synthetic_offchain_verified",
    development_only: true,
    production_eligible: false,
    offchain_groth16_verified: false,
    onchain_groth16_verified: false,
    ...overrides,
  };
}

function submit(id = ID, tx = TX) {
  fireEvent.change(screen.getByLabelText("V3 receipt ID"), {
    target: { value: id },
  });
  fireEvent.change(screen.getByLabelText("V3 transaction hash"), {
    target: { value: tx },
  });
  fireEvent.click(screen.getByRole("button", { name: "Check V3 receipt" }));
}

describe("V3 development receipt lookup", () => {
  beforeEach(() => requestMock.mockReset());

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("never looks up receipt data automatically", () => {
    render(<V3DevelopmentReceiptPanel />);
    expect(requestMock).not.toHaveBeenCalled();
    expect(screen.getByText(/not production eligible/i)).toBeInTheDocument();
  });

  it("rejects malformed identifiers before API access", () => {
    render(<V3DevelopmentReceiptPanel />);
    submit("invalid-id", TX);

    const input = screen.getByLabelText("V3 receipt ID") as HTMLInputElement;
    expect(input.checkValidity()).toBe(false);
    expect(requestMock).not.toHaveBeenCalled();
  });

  it("uses the authenticated API client for manual V3 lookup", async () => {
    requestMock.mockResolvedValue(receiptResult());
    render(<V3DevelopmentReceiptPanel />);
    submit();

    expect(
      await screen.findByText("Development receipt confirmed on-chain"),
    ).toBeInTheDocument();

    expect(requestMock).toHaveBeenCalledWith(
      `/trust/v3/receipts/${ID}?transaction_hash=${TX}`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    expect(
      screen.getByText("Immutable development receipt commitments"),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/On-chain Groth16 verification:/),
    ).toHaveTextContent("Not performed");
  });

  it("does not upgrade an unconfirmed result into a verified claim", async () => {
    requestMock.mockResolvedValue(
      receiptResult({
        state: "receipt_found",
        event_verified: false,
        confirmations: null,
      }),
    );

    render(<V3DevelopmentReceiptPanel />);
    submit();

    expect(
      await screen.findByText("Not fully confirmed: receipt_found"),
    ).toBeInTheDocument();

    expect(
      screen.queryByText("Immutable development receipt commitments"),
    ).not.toBeInTheDocument();
  });

  it("does not call an unsafe classification confirmed", async () => {
    requestMock.mockResolvedValue(
      receiptResult({ production_eligible: true }),
    );

    render(<V3DevelopmentReceiptPanel />);
    submit();

    expect(
      await screen.findByText("Not fully confirmed: confirmed"),
    ).toBeInTheDocument();

    expect(
      screen.queryByText("Development receipt confirmed on-chain"),
    ).not.toBeInTheDocument();
  });

  it("shows authorization failures without bypassing the backend", async () => {
    const forbiddenError = Object.assign(
      new Error("Receipt viewer access denied"),
      {
        status: 403,
        code: "forbidden",
      },
    );

    requestMock.mockRejectedValue(forbiddenError);

    render(<V3DevelopmentReceiptPanel />);
    submit();

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("Receipt Viewer authorization is required");

    expect(requestMock).toHaveBeenCalledTimes(1);
  });
});
