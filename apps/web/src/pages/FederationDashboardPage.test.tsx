/**
 * Federation verification dashboard security regression.
 *
 * All API responses are synthetic fixtures.
 * These tests do not train models, submit proofs,
 * access MRI datasets, or modify PostgreSQL.
 */

import {
  cleanup,
  render,
  screen,
  within,
} from "@testing-library/react";

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { FederationDashboardPage } from "./FederationDashboardPage";

const { requestMock } = vi.hoisted(() => ({
  requestMock: vi.fn(),
}));

vi.mock("../services/apiClient", () => ({
  apiClient: {
    request: requestMock,
  },
}));

type ProofStatus =
  | "not_submitted"
  | "pending_verification"
  | "verified"
  | "rejected";

type ProofLifecycle =
  | "prepared"
  | "submitted"
  | "awaiting_proof"
  | "verification_pending"
  | "cryptographically_verified"
  | "rejected";

function makeUpdate(
  overrides: Record<string, unknown> = {},
) {
  return {
    id: "synthetic-update-001",
    federation_round_id: "synthetic-round-001",
    hospital_id: "synthetic-hospital-001",

    status: "submitted",

    artifact_sha256: "a".repeat(64),
    artifact_size_bytes: 1024,
    update_commitment: "b".repeat(64),
    proof_artifact_sha256: null,

    sample_count: 1,
    training_metadata_recorded: true,

    proof_verification_status:
      "not_submitted" as ProofStatus,

    proof_lifecycle:
      "awaiting_proof" as ProofLifecycle,

    zk_coverage_complete: false,
    aggregation_eligible: false,

    rejection_code: null,
    rejection_reason: null,

    ...overrides,
  };
}

function makeSummary(update: ReturnType<typeof makeUpdate>) {
  return {
    generated_at: "2026-11-03T00:00:00Z",

    coordinator: {
      readiness: {
        database_backed: true,
        checkpoint_storage_configured: true,
        update_storage_configured: true,
        groth16_verifier: "development_only",
        production_aggregation:
          "blocked_pending_groth16_verifier",
      },

      hospitals: [],
      rounds: [],
      models: [],
      global_checkpoints: [],
      submitted_updates: [update],
    },

    historical_evidence: {
      source: "legacy_flower_read_only",
      available: false,
      experiments: [],
      protocol_test: null,
    },

    disclaimer:
      "Synthetic dashboard test data. Not clinical evidence.",
  };
}

async function renderUpdate(
  overrides: Record<string, unknown> = {},
) {
  requestMock.mockResolvedValue(
    makeSummary(makeUpdate(overrides)),
  );

  render(<FederationDashboardPage />);

  const heading = await screen.findByText(
    "Update synthetic-update-001",
  );

  const card = heading.closest("div.rounded-lg");

  if (!card) {
    throw new Error(
      "Submitted update card not found.",
    );
  }

  return within(card as HTMLElement);
}

describe("Federation dashboard verification security", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows verified proof with bounded coverage and blocked aggregation", async () => {
    const card = await renderUpdate({
      status: "accepted",
      proof_verification_status: "verified",
      proof_lifecycle: "cryptographically_verified",
      zk_coverage_complete: true,
      aggregation_eligible: false,
    });

    expect(
      card.getByText(/Proof:/),
    ).toHaveTextContent("verified");

    expect(
      card.getByText(/Proof lifecycle:/),
    ).toHaveTextContent(
      "cryptographically verified",
    );

    expect(
      card.getByText(/ZK chunk coverage:/),
    ).toHaveTextContent(
      "Complete for submitted quantized update",
    );

    expect(
      card.getByText(/Aggregation eligible:/),
    ).toHaveTextContent("No");
  });

  it("shows a persisted proof receipt hash without treating it as proof verification", async () => {
    const receiptHash = "c".repeat(64);
    const card = await renderUpdate({
      proof_artifact_sha256: receiptHash,
      proof_verification_status: "pending_verification",
      proof_lifecycle: "verification_pending",
      aggregation_eligible: false,
    });

    expect(
      card.getByText(/Proof receipt SHA256:/),
    ).toHaveTextContent(receiptHash);
    expect(card.getByText(/Proof:/)).toHaveTextContent("pending verification");
    expect(
      card.getByText(/Aggregation eligible:/),
    ).toHaveTextContent("No");
  });

  it("never claims verified ZK coverage for a rejected proof", async () => {
    const card = await renderUpdate({
      status: "rejected",
      proof_verification_status: "rejected",
      proof_lifecycle: "rejected",
      zk_coverage_complete: false,
      aggregation_eligible: false,
      rejection_code: "artifact_binding_mismatch",
      rejection_reason:
        "Protected update artifact failed integrity verification.",
    });

    expect(
      card.getByText(/ZK chunk coverage:/),
    ).toHaveTextContent("Not verified");

    expect(
      card.queryByText(
        /Complete for submitted quantized update/,
      ),
    ).not.toBeInTheDocument();

    expect(
      card.getByText(/Aggregation eligible:/),
    ).toHaveTextContent("No");

    expect(
      card.getByText(/Rejected:/),
    ).toHaveTextContent(
      "failed integrity verification",
    );
  });

  it("does not misrepresent missing integrity and training evidence", async () => {
    const card = await renderUpdate({
      proof_verification_status: "verified",
      proof_lifecycle: "cryptographically_verified",
      zk_coverage_complete: true,
      aggregation_eligible: false,
    });

    expect(
      card.getByText(/Full-model integrity:/),
    ).toHaveTextContent(
      "Not separately recorded",
    );

    expect(
      card.getByText(/Training correctness:/),
    ).toHaveTextContent(
      "Not independently verified",
    );

    expect(
      card.getByText(/Aggregation eligible:/),
    ).toHaveTextContent("No");
  });

  it("renders incomplete coverage without granting eligibility", async () => {
    const card = await renderUpdate({
      proof_verification_status: "verified",
      proof_lifecycle: "cryptographically_verified",
      zk_coverage_complete: false,
      aggregation_eligible: false,
    });

    expect(
      card.getByText(/ZK chunk coverage:/),
    ).toHaveTextContent("Incomplete");

    expect(
      card.getByText(/Aggregation eligible:/),
    ).toHaveTextContent("No");
  });

  it("keeps pending proof coverage unverified", async () => {
    const card = await renderUpdate({
      proof_verification_status: "pending_verification",
      proof_lifecycle: "verification_pending",
      zk_coverage_complete: false,
      aggregation_eligible: false,
    });

    expect(
      card.getByText(/ZK chunk coverage:/),
    ).toHaveTextContent("Not verified");

    expect(
      card.getByText(/Aggregation eligible:/),
    ).toHaveTextContent("No");
  });
});
