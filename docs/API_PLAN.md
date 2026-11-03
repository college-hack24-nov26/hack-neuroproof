# API Plan

## Conventions

All browser-facing API endpoints will be versioned below /api/v1 and use JSON unless explicitly handling a protected upload or download stream. Routes require an authenticated actor unless marked public. The API will derive the active hospital from membership and authorization context rather than trusting a hospital ID supplied by the client.

The proposed error envelope is:

    {
      "error": {
        "code": "study_not_found",
        "message": "The requested study is not available in the active hospital.",
        "request_id": "..."
      }
    }

Validation errors will retain field-level details. Error responses must not disclose whether inaccessible cross-hospital records exist.

## Authentication and identity

Phase 3 implements the public registration/login/me contract and hospital administration endpoints documented in [AUTH_API.md](AUTH_API.md). The earlier proposed separate hospital/doctor login paths are intentionally consolidated into `POST /auth/login` with an explicit `hospital_slug`; its response reveals only a verified active membership. Refresh tokens and server-side revocation remain deferred rather than simulated.

| Method and path | Purpose | Initial authorization |
| --- | --- | --- |
| POST /auth/hospitals/register | Begin hospital registration workflow | Public, rate limited; not an automatic approval |
| POST /auth/hospitals/login | Authenticate a hospital administrator or service account | Public, rate limited |
| POST /auth/doctors/register | Create a doctor account within an approved hospital | Hospital administrator |
| POST /auth/doctors/login | Authenticate a doctor | Public, rate limited |
| POST /auth/refresh | Rotate a valid refresh credential | Authenticated refresh context |
| POST /auth/logout | Revoke current session/refresh credential | Authenticated |
| GET /auth/me | Return actor, roles, and active hospital memberships | Authenticated |

The final mechanism will be selected in Phase 2. Passwords must be salted and securely hashed; issued credentials must be short-lived and revocable. Safe demo accounts, if later required, must use environment-provided non-production values.

## Hospital and dashboard

| Method and path | Purpose | Authorization |
| --- | --- | --- |
| GET /hospitals/me | Return active hospital profile and permitted capabilities | Hospital member |
| PATCH /hospitals/me | Update authorized hospital metadata | Hospital administrator |
| GET /dashboard/summary | Counts, workflow statuses, and model/round summaries for the active hospital | Hospital member |
| GET /dashboard/activity | Paginated hospital-scoped audit/activity feed | Hospital member |

## Studies, uploads, and artifacts

| Method and path | Purpose | Authorization |
| --- | --- | --- |
| POST /studies | Create a de-identified study record | Doctor or hospital administrator |
| GET /studies | List only active-hospital studies with pagination/filtering | Hospital member |
| GET /studies/{study_id} | Read one authorized study and workflow state | Hospital member |
| POST /studies/{study_id}/uploads | Initiate protected four-modality upload | Doctor or authorized service account |
| POST /studies/{study_id}/uploads/{upload_id}/complete | Validate uploaded artifact set and mark ready/rejected | Uploader or authorized service account |
| GET /studies/{study_id}/artifacts | List authorized input/derived artifact metadata, never storage secrets | Hospital member |
| GET /studies/{study_id}/preview | Return a guarded rendered slice/overlay representation | Hospital member |

The API will accept only an approved storage-upload flow, enforce size and content limits, validate all four modalities, reject unsafe paths, and log artifact metadata. Raw MRI is never embedded in JSON, application logs, Git, or browser state.

## Analysis and reports

| Method and path | Purpose | Authorization |
| --- | --- | --- |
| POST /studies/{study_id}/analyses | Request a research-only segmentation job | Doctor or authorized service account |
| GET /studies/{study_id}/analyses | List analysis jobs and statuses | Hospital member |
| GET /analyses/{analysis_id} | Read job state, model provenance, and result metadata | Hospital member |
| GET /analyses/{analysis_id}/report | Return authorized structured research report | Hospital member |
| GET /analyses/{analysis_id}/visualization | Return visualization manifest for authorized derived artifacts | Hospital member |

Analysis submission must fail closed if the configured checkpoint hash, modality requirements, storage access, or model compatibility checks fail. A result will include provenance and research-only language, not a diagnosis.

## Custom federated-learning coordinator

| Method and path | Purpose | Authorization |
| --- | --- | --- |
| GET /federation/summary | Custom coordinator readiness, dynamic hospital enrollment, rounds, and separate historical evidence | Hospital administrator |
| POST /federation/training-nodes/enroll | Explicitly enroll only the caller's hospital training node | Hospital administrator |
| POST /federation/training-agents/enroll | Explicitly enroll a hospital-local agent tied to the caller's node | Hospital administrator |
| GET /federation/models | List custom coordinator model metadata | Hospital administrator |
| POST /federation/models | Register base-model commitment metadata | Explicit configured federation operator |
| GET /federation/rounds | List observed custom coordinator round state and proof statuses | Hospital administrator |
| POST /federation/rounds | Create a draft from explicitly enrolled nodes | Explicit configured federation operator |
| POST /federation/rounds/{round_id}/open | Open a draft round; does not train or accept browser tensor payloads | Explicit configured federation operator |
| POST /federation/rounds/{round_id}/updates/prepare | Reserve one node/agent/model-bound update submission slot | Participating hospital administrator |
| POST /federation/updates/{submission_id}/artifact | Submit one bounded safe private-update archive | Owning hospital administrator |
| GET /federation/updates | List safe update provenance/status metadata | Hospital administrator |

Private tensors, witnesses, and proof contents are deliberately not browser request payloads or PostgreSQL records. Production aggregation requires real Groth16 verification and fails closed while the verifier is unavailable. A SHA-256 model/update commitment is not a Groth16 proof. The service must not derive performance or verification state from filenames or unverified client assertions.

The artifact upload accepts only the custom bounded ZIP/JSON/`.npy` format; it does not call `torch.load` on hospital input. The database stores no MRI paths or update tensors. An accepted archive still does not imply aggregation eligibility unless a reviewed Groth16 verifier validates its proof against the required public inputs.

## Trust-layer records

| Method and path | Purpose | Authorization |
| --- | --- | --- |
| GET /trust/proofs | List proof-record metadata visible to the active hospital | Hospital member |
| GET /trust/proofs/{proof_id} | Return verification status, circuit/version bindings, and non-sensitive receipt metadata | Hospital member |
| GET /trust/anchors | List recorded chain-anchor metadata | Hospital member |
| GET /trust/anchors/{anchor_id} | Return anchor, transaction, and CID reference metadata | Hospital member |

V2 will expose observed states such as unavailable, pending, verified, rejected, failed, or not_requested. It will not infer proof verification from a CID or an anchored integrity root. Private proof inputs and witness material are never API responses.

## Health and operations

| Method and path | Purpose | Authorization |
| --- | --- | --- |
| GET /health | Process liveness only; no secrets or dependency details | Public or infrastructure-only |
| GET /ready | Readiness of configured dependencies, reported without secrets | Infrastructure-only |
| GET /openapi.json | Generated API schema | Deployment policy controlled |

## Data contracts and pagination

List responses will use cursor or bounded offset pagination, explicit sort fields, and stable response schemas. UUIDs will identify V2 records. Timestamps use UTC ISO 8601. Model, storage, proof, and chain references will carry algorithms and hashes where applicable.

The React client will consume generated or shared TypeScript types rather than duplicate handwritten API shapes. Database entities remain backend-private and are never directly serialized.
