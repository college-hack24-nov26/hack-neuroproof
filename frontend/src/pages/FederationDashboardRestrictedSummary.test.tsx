/**
 * Federation Dashboard restricted-summary regression tests.
 *
 * Synthetic API responses only.
 * Authorization and tenant filtering are enforced by the backend.
 *
 * No database, MRI datasets, training, or proof submission.
 */

import {
  cleanup,
  render,
  screen,
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

function makeUpdate(
  id: string,
  hospitalId: string,
) {
  return {
    id,
    federation_round_id: "synthetic-round",
    hospital_id: hospitalId,

    status: "submitted",

    artifact_sha256: "a".repeat(64),
    artifact_size_bytes: 1024,
    update_commitment: "b".repeat(64),

    sample_count: 1,
    training_metadata_recorded: true,

    proof_verification_status: "not_submitted",
    proof_lifecycle: "awaiting_proof",

    zk_coverage_complete: false,
    aggregation_eligible: false,

    rejection_code: null,
    rejection_reason: null,
  };
}

function makeSummary(
  updates: ReturnType<typeof makeUpdate>[],
) {
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
      submitted_updates: updates,
    },

    historical_evidence: {
      source: "legacy_flower_read_only",
      available: false,
      experiments: [],
      protocol_test: null,
    },

    disclaimer:
      "Synthetic restricted-summary UI test.",
  };
}

describe("Federation restricted-summary dashboard", () => {
  beforeEach(() => {
    requestMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it.each([
    [
      "Hospital A",
      "hospital-a-private-update",
      "hospital-b-private-update",
      "synthetic-hospital-a",
    ],
    [
      "Hospital B",
      "hospital-b-private-update",
      "hospital-a-private-update",
      "synthetic-hospital-b",
    ],
  ])(
    "%s renders only the submitted update supplied for that hospital",
    async (
      _hospital,
      ownUpdate,
      otherUpdate,
      hospitalId,
    ) => {
      requestMock.mockResolvedValue(
        makeSummary([
          makeUpdate(ownUpdate, hospitalId),
        ]),
      );

      render(<FederationDashboardPage />);

      expect(
        await screen.findByText(`Update ${ownUpdate}`),
      ).toBeInTheDocument();

      expect(
        screen.queryByText(`Update ${otherUpdate}`),
      ).not.toBeInTheDocument();

      expect(
        requestMock,
      ).toHaveBeenCalledWith(
        "/federation/summary",
        expect.anything(),
      );

      expect(
        screen.getByText(
          "No custom coordinator rounds have been created.",
        ),
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          "No coordinator model versions are registered.",
        ),
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          "No custom coordinator checkpoint has been saved.",
        ),
      ).toBeInTheDocument();

      expect(
        screen.getByText(
          "Historical Flower evidence is not configured or unavailable.",
        ),
      ).toBeInTheDocument();
    },
  );

  it("renders a restricted summary with no submitted updates", async () => {
    requestMock.mockResolvedValue(
      makeSummary([]),
    );

    render(<FederationDashboardPage />);

    expect(
      await screen.findByText(
        "No model updates have been submitted.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "No custom coordinator rounds have been created.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "No custom coordinator checkpoint has been saved.",
      ),
    ).toBeInTheDocument();
  });

  it("continues rendering multiple updates in an operator-style response", async () => {
    requestMock.mockResolvedValue(
      makeSummary([
        makeUpdate(
          "hospital-a-private-update",
          "synthetic-hospital-a",
        ),
        makeUpdate(
          "hospital-b-private-update",
          "synthetic-hospital-b",
        ),
      ]),
    );

    render(<FederationDashboardPage />);

    expect(
      await screen.findByText(
        "Update hospital-a-private-update",
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(
        "Update hospital-b-private-update",
      ),
    ).toBeInTheDocument();

    expect(
      requestMock,
    ).toHaveBeenCalledWith(
      "/federation/summary",
      expect.anything(),
    );
  });
});
