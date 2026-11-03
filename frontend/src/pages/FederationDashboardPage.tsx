import { useEffect, useState } from "react";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { apiClient } from "../services/apiClient";
import { getErrorMessage } from "../utils/errors";

type CoordinatorHospital = {
  hospital_name: string;
  hospital_slug: string;
  registered: boolean;
  training_node_status: "not_enrolled" | "enrolled" | "disabled";
  training_agent_status: "not_enrolled" | "enrolled" | "disabled";
  dataset_availability:
    | "authorized_unvalidated"
    | "geometry_validated"
    | "not_approved"
    | "unavailable";
  training_readiness:
    | "not_ready_missing_node"
    | "not_ready_missing_agent"
    | "not_ready_dataset_unvalidated"
    | "not_ready_no_dataset"
    | "execution_disabled"
    | "execution_authorization_required";
};

type RoundParticipant = {
  hospital_id: string;
  status: "invited" | "submitted" | "accepted" | "rejected";
  sample_count: number | null;
  proof_verification_status:
    | "not_submitted"
    | "pending_verification"
    | "verified"
    | "rejected";
};

type CoordinatorRound = {
  id: string;
  base_model_version_id: string;
  global_model_version_id: string | null;
  status: "draft" | "open" | "aggregating" | "completed" | "failed";
  requires_zk_verification: boolean;
  research_mode: boolean;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
  participants: RoundParticipant[];
};

type ModelVersion = {
  id: string;
  label: string;
  model_commitment: string;
  parent_model_version_id: string | null;
  artifact_reference: string | null;
  artifact_sha256: string | null;
  parameter_schema_commitment: string | null;
  parameter_schema_available: boolean;
  created_at: string;
};

type SubmittedUpdate = {
  id: string;
  federation_round_id: string;
  hospital_id: string;
  status: "prepared" | "submitted" | "accepted" | "rejected";
  artifact_sha256: string | null;
  artifact_size_bytes: number | null;
  update_commitment: string | null;
  sample_count: number | null;
  proof_verification_status:
    | "not_submitted"
    | "pending_verification"
    | "verified"
    | "rejected";
  training_metadata_recorded: boolean;
  proof_lifecycle:
    | "prepared"
    | "submitted"
    | "awaiting_proof"
    | "verification_pending"
    | "cryptographically_verified"
    | "rejected";
  zk_coverage_complete: boolean;
  aggregation_eligible: boolean;
  rejection_code: string | null;
  rejection_reason: string | null;
};

type GlobalCheckpoint = {
  federation_round_id: string;
  model_version_id: string;
  storage_reference: string;
  checkpoint_sha256: string;
  size_bytes: number;
  aggregation_algorithm: string;
  participant_count: number;
  total_sample_count: number;
  created_at: string;
};

type HistoricalExperiment = {
  id: string;
  title: string;
  metadata_available: boolean;
  round: number | null;
  participants: string[];
  total_samples: number | null;
  aggregation: string | null;
  changed_global_parameters: number | null;
  global_update_l2_norm: number | null;
  secure_aggregation: boolean;
  distributed_privacy_verified: boolean;
  zk_proof_generated: boolean;
  blockchain_committed: boolean;
  clinical_validation: boolean;
  single_process_smoke_test: boolean;
  secure_sum_mismatches: number | null;
  checkpoint: {
    sha256: string | null;
    integrity: string;
    size_bytes: number | null;
  };
};

type FederationSummary = {
  generated_at: string;
  coordinator: {
    readiness: {
      database_backed: boolean;
      checkpoint_storage_configured: boolean;
      update_storage_configured: boolean;
      groth16_verifier: "unavailable" | "development_only" | "production_ready";
      production_aggregation: "blocked_pending_groth16_verifier";
    };
    hospitals: CoordinatorHospital[];
    rounds: CoordinatorRound[];
    models: ModelVersion[];
    global_checkpoints: GlobalCheckpoint[];
    submitted_updates: SubmittedUpdate[];
  };
  historical_evidence: {
    source: "legacy_flower_read_only";
    available: boolean;
    experiments: HistoricalExperiment[];
    protocol_test: {
      round_label: number | null;
      purpose: string | null;
      full_model_proven: boolean;
      live_proof_submitted: boolean;
      blockchain_verification_completed: boolean;
    } | null;
  };
  disclaimer: string;
};

function YesNo({ value }: { value: boolean }) {
  return (
    <span className={value ? "text-emerald-300" : "text-amber-300"}>
      {value ? "Yes" : "No"}
    </span>
  );
}

function State({ value }: { value: string }) {
  const successful = value === "enrolled" || value === "completed" || value === "verified";
  const attention = value.includes("blocked") || value === "failed" || value === "rejected";
  const color = successful
    ? "text-emerald-300"
    : attention
      ? "text-rose-300"
      : "text-amber-300";
  return <span className={color}>{value.replaceAll("_", " ")}</span>;
}

function HistoricalModelCard({ item }: { item: HistoricalExperiment }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-ink">{item.title}</h3>
          <p className="mt-1 text-sm text-muted">
            {item.single_process_smoke_test
              ? "Historical single-process research smoke test"
              : "Historical aggregation prototype"}
          </p>
        </div>
        <span className="rounded-lg border border-border px-3 py-1 text-xs text-muted">
          {item.metadata_available ? "Evidence available" : "Unavailable"}
        </span>
      </div>

      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted">Round</dt>
          <dd className="font-medium text-ink">{item.round ?? "Not recorded"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Participants</dt>
          <dd className="font-medium text-ink">
            {item.participants.length ? item.participants.join(" + ") : "Not recorded"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Training samples</dt>
          <dd className="font-medium text-ink">{item.total_samples ?? "Not recorded"}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Recorded aggregation</dt>
          <dd className="break-words text-sm text-ink">{item.aggregation ?? "Not recorded"}</dd>
        </div>
      </dl>

      <div className="mt-5 rounded-lg border border-border bg-slate-900/50 p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Historical checkpoint SHA256
        </p>
        <p className="mt-2 break-all font-mono text-xs text-cyan-200">
          {item.checkpoint.sha256 ?? "Checkpoint unavailable"}
        </p>
        <p className="mt-2 text-xs text-muted">
          Integrity: {item.checkpoint.integrity.replaceAll("_", " ")}
        </p>
      </div>

      <div className="mt-5 grid gap-2 text-sm text-muted sm:grid-cols-2">
        <p>ZK proof recorded: <YesNo value={item.zk_proof_generated} /></p>
        <p>On-chain recorded: <YesNo value={item.blockchain_committed} /></p>
        <p>Distributed privacy verified: <YesNo value={item.distributed_privacy_verified} /></p>
        <p>Clinical validation: <YesNo value={item.clinical_validation} /></p>
      </div>
    </Card>
  );
}

export function FederationDashboardPage() {
  const [data, setData] = useState<FederationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(null);

    apiClient
      .request<FederationSummary>("/federation/summary", { signal: controller.signal })
      .then((response) => {
        if (active) setData(response);
      })
      .catch((reason: unknown) => {
        if (active && !controller.signal.aborted) setError(getErrorMessage(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [refreshKey]);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Federated Learning Coordinator"
        description="Custom coordinator status, model provenance, and fail-closed Groth16 verification readiness."
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Hospital registration, training-node enrollment, dataset availability, training, and proof verification are separate states.
        </p>
        <button
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          className="rounded-lg border border-violet-400/40 bg-violet-500/20 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500/30"
        >
          Refresh coordinator status
        </button>
      </div>

      {loading ? <Card><p className="text-muted">Loading coordinator state…</p></Card> : null}
      {error ? (
        <Card><p className="text-rose-300" role="alert">Federation API error: {error}</p></Card>
      ) : null}

      {data ? (
        <>
          <Card>
            <h2 className="text-lg font-semibold text-ink">Coordinator readiness</h2>
            <div className="mt-4 grid gap-3 text-sm text-muted sm:grid-cols-2 lg:grid-cols-4">
              <p>Database-backed: <YesNo value={data.coordinator.readiness.database_backed} /></p>
              <p>Checkpoint storage configured: <YesNo value={data.coordinator.readiness.checkpoint_storage_configured} /></p>
              <p>Update storage configured: <YesNo value={data.coordinator.readiness.update_storage_configured} /></p>
              <p>Groth16 verifier: <State value={data.coordinator.readiness.groth16_verifier} /></p>
              <p>Production aggregation: <State value={data.coordinator.readiness.production_aggregation} /></p>
            </div>
            <p className="mt-4 text-sm text-amber-200">
              A model or update SHA256 is an integrity commitment, not a Groth16 proof. Production aggregation remains blocked until a reviewed verifier is implemented.
            </p>
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-ink">Registered hospitals and training-node enrollment</h2>
            <p className="mt-2 text-sm text-muted">
              Hospitals are discovered from PostgreSQL. Node and agent enrollment do not claim a dataset validation, training result, round participation, or proof.
            </p>
            {data.coordinator.hospitals.length ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {data.coordinator.hospitals.map((hospital) => (
                  <div key={hospital.hospital_slug} className="rounded-lg border border-border bg-slate-900/40 p-4">
                    <h3 className="font-semibold text-ink">{hospital.hospital_name}</h3>
                    <p className="mt-2 text-sm text-muted">Registered: <YesNo value={hospital.registered} /></p>
                    <p className="mt-1 text-sm text-muted">Training node: <State value={hospital.training_node_status} /></p>
                    <p className="mt-1 text-sm text-muted">Dataset: {hospital.dataset_availability.replaceAll("_", " ")}</p>
                    <p className="mt-1 text-sm text-muted">Training agent: <State value={hospital.training_agent_status} /></p>
                    <p className="mt-1 text-sm text-muted">Training readiness: <State value={hospital.training_readiness} /></p>
                  </div>
                ))}
              </div>
            ) : <p className="mt-4 text-sm text-muted">No registered hospitals are available to this coordinator.</p>}
          </Card>

          <Card>
            <h2 className="text-lg font-semibold text-ink">Custom coordinator rounds</h2>
            {data.coordinator.rounds.length ? (
              <div className="mt-4 grid gap-4">
                {data.coordinator.rounds.map((round) => (
                  <div key={round.id} className="rounded-lg border border-border bg-slate-900/40 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-ink">Round {round.id}</p>
                        <p className="mt-1 text-xs text-muted">Base model: {round.base_model_version_id}</p>
                      </div>
                      <State value={round.status} />
                    </div>
                    <div className="mt-3 grid gap-2 text-sm text-muted sm:grid-cols-3">
                      <p>ZK required: <YesNo value={round.requires_zk_verification} /></p>
                      <p>Research-only: <YesNo value={round.research_mode} /></p>
                      <p>Participants: {round.participants.length}</p>
                    </div>
                    {round.failure_reason ? <p className="mt-3 text-sm text-rose-300">Failure: {round.failure_reason}</p> : null}
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                      {round.participants.map((participant) => (
                        <p key={participant.hospital_id}>
                          {participant.hospital_id}: <State value={participant.status} /> / proof <State value={participant.proof_verification_status} />
                        </p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="mt-4 text-sm text-muted">No custom coordinator rounds have been created.</p>}
          </Card>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <h2 className="text-lg font-semibold text-ink">Model versions</h2>
              {data.coordinator.models.length ? (
                <div className="mt-4 grid gap-3">
                  {data.coordinator.models.map((model) => (
                    <div key={model.id} className="rounded-lg border border-border bg-slate-900/40 p-4">
                      <p className="font-semibold text-ink">{model.label}</p>
                      <p className="mt-2 break-all font-mono text-xs text-cyan-200">{model.model_commitment}</p>
                      <p className="mt-2 text-xs text-muted">Artifact: {model.artifact_reference ?? "Not recorded"}</p>
                      <p className="mt-1 text-xs text-muted">
                        Parameter schema: {model.parameter_schema_available ? "Registered" : "Not registered"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : <p className="mt-4 text-sm text-muted">No coordinator model versions are registered.</p>}
            </Card>
            <Card>
              <h2 className="text-lg font-semibold text-ink">Global checkpoint provenance</h2>
              {data.coordinator.global_checkpoints.length ? (
                <div className="mt-4 grid gap-3">
                  {data.coordinator.global_checkpoints.map((checkpoint) => (
                    <div key={checkpoint.model_version_id} className="rounded-lg border border-border bg-slate-900/40 p-4">
                      <p className="text-sm text-ink">{checkpoint.aggregation_algorithm}</p>
                      <p className="mt-2 break-all font-mono text-xs text-cyan-200">{checkpoint.checkpoint_sha256}</p>
                      <p className="mt-2 text-xs text-muted">{checkpoint.participant_count} participants · {checkpoint.total_sample_count} samples</p>
                    </div>
                  ))}
                </div>
              ) : <p className="mt-4 text-sm text-muted">No custom coordinator checkpoint has been saved.</p>}
            </Card>
          </div>

          <Card>
            <h2 className="text-lg font-semibold text-ink">Submitted model updates</h2>
            <p className="mt-2 text-sm text-muted">
              Metadata and integrity commitments only. Raw updates remain in protected storage; rejected updates are not aggregation-eligible.
            </p>
            {data.coordinator.submitted_updates.length ? (
              <div className="mt-4 grid gap-3">
                {data.coordinator.submitted_updates.map((update) => (
                  <div key={update.id} className="rounded-lg border border-border bg-slate-900/40 p-4">
                    <div className="flex flex-wrap justify-between gap-3 text-sm">
                      <p className="font-semibold text-ink">Update {update.id}</p>
                      <State value={update.status} />
                    </div>
                    <div className="mt-2 grid gap-2 text-xs text-muted sm:grid-cols-3">
                      <p>Samples: {update.sample_count ?? "Not recorded"}</p>
                      <p>Proof: <State value={update.proof_verification_status} /></p>
                      <p>Proof lifecycle: <State value={update.proof_lifecycle} /></p>
                      <p>
                        ZK chunk coverage:{" "}
                        {update.proof_verification_status === "verified"
                          ? update.zk_coverage_complete
                            ? "Complete for submitted quantized update"
                            : "Incomplete"
                          : "Not verified"}
                      </p>
                      <p>Full-model integrity: Not separately recorded</p>
                      <p>Training correctness: Not independently verified</p>
                      <p>Training metadata: <YesNo value={update.training_metadata_recorded} /></p>
                      <p>Aggregation eligible: <YesNo value={update.aggregation_eligible} /></p>
                    </div>
                    {update.artifact_sha256 ? <p className="mt-2 break-all font-mono text-xs text-cyan-200">{update.artifact_sha256}</p> : null}
                    {update.rejection_reason ? <p className="mt-2 text-sm text-rose-300">Rejected: {update.rejection_reason}</p> : null}
                  </div>
                ))}
              </div>
            ) : <p className="mt-4 text-sm text-muted">No model updates have been submitted.</p>}
          </Card>

          <section className="grid gap-5" aria-labelledby="historical-evidence-heading">
            <div>
              <h2 id="historical-evidence-heading" className="text-xl font-semibold text-ink">Historical Flower evidence</h2>
              <p className="mt-1 text-sm text-muted">
                Read-only legacy experiments; they are not custom-coordinator rounds and do not establish current node enrollment or ZK verification.
              </p>
            </div>
            {data.historical_evidence.available ? (
              <>
                <div className="grid gap-5 xl:grid-cols-2">
                  {data.historical_evidence.experiments.map((experiment) => (
                    <HistoricalModelCard item={experiment} key={experiment.id} />
                  ))}
                </div>
                {data.historical_evidence.protocol_test ? (
                  <Card>
                    <h3 className="text-lg font-semibold text-ink">
                      Historical ZKP protocol evidence — Round {data.historical_evidence.protocol_test.round_label ?? "unknown"}
                    </h3>
                    <p className="mt-2 text-sm text-muted">
                      {data.historical_evidence.protocol_test.purpose ?? "No protocol evidence available."}
                    </p>
                    <div className="mt-4 grid gap-3 text-sm text-muted sm:grid-cols-3">
                      <p>Full model proven: <YesNo value={data.historical_evidence.protocol_test.full_model_proven} /></p>
                      <p>Live proof submitted: <YesNo value={data.historical_evidence.protocol_test.live_proof_submitted} /></p>
                      <p>Blockchain verified: <YesNo value={data.historical_evidence.protocol_test.blockchain_verification_completed} /></p>
                    </div>
                  </Card>
                ) : null}
              </>
            ) : <Card><p className="text-sm text-muted">Historical Flower evidence is not configured or unavailable.</p></Card>}
          </section>

          <Card>
            <p className="text-sm text-amber-200">{data.disclaimer}</p>
            <p className="mt-2 text-xs text-muted">Snapshot: {new Date(data.generated_at).toLocaleString()}</p>
          </Card>
        </>
      ) : null}
    </div>
  );
}
