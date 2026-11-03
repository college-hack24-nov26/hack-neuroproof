# Development Roadmap

## Phase 1 — Architecture preparation

Status: complete.

Delivered:

- Read-only legacy inspection and asset inventory.
- Strict compatibility verification of the source trained MONAI 3D U-Net checkpoint.
- V2 repository structure, architecture plan, API plan, permanent rules, and security-oriented ignore rules.
- Documentation of legacy limitations and explicit non-claims.

Not delivered:

- Dependencies, service startup, application code, database schema, authentication flow, MRI upload, inference endpoint, UI, federation run, proof generation, deployment, or blockchain transaction.

## Phase 2 — Foundation, tenancy, and developer quality gates

Goal: create the runnable but feature-minimal web and API foundations.

1. Add pinned dependency manifests and lockfiles for Vite/React/TypeScript and FastAPI/SQLAlchemy/Pydantic/Alembic after review.
2. Create centralized backend configuration with typed environment settings and a safe environment example without values.
3. Establish PostgreSQL schema, Alembic baseline migration, session lifecycle, repository conventions, and hospital-owned entities.
4. Implement hospital/doctor authentication and role-based authorization with tests for hospital data isolation.
5. Add the React routing shell, layout primitives, authentication-state boundary, typed API client, and accessible loading/error/empty states.
6. Add formatter, linter, type checks, unit/integration test foundations, and CI workflow.

Exit criteria:

- No service has a hard-coded credential, database URL, model path, or tenant bypass.
- Migration, API tests, frontend type check, lint, and production build pass.
- Cross-hospital access attempts are tested and denied.

## Phase 3 — Secure MRI study workflow

Goal: implement protected study metadata, four-modality upload validation, and authorized visualization primitives.

1. Implement de-identified study and artifact metadata models.
2. Add protected external artifact storage contract with retention and audit metadata.
3. Validate NIfTI file type, decode safety, sizes, modality completeness/order, shape/affine alignment, and safe paths.
4. Implement hospital-scoped study routes and frontend upload/status pages.
5. Add slice-view and overlay-ready visualization contracts without embedding raw volume data in logs or global browser state.

Exit criteria:

- Upload failure modes are explicit and tested.
- MRI data is excluded by Git and unavailable across hospital boundaries.
- No actual model inference occurs yet unless Phase 4 checks pass.

## Phase 4 — Verified real-model inference and reports

Goal: integrate the externally stored trained MONAI checkpoint through the ML adapter.

1. Implement configuration for checkpoint location, expected SHA-256, inference device, and protected output location.
2. Port the verified preprocessing, architecture, sliding-window inference, and postprocessing behind a testable adapter.
3. Add strict-load, hash, modality-order, alignment, and output-schema tests against approved de-identified test fixtures stored outside Git.
4. Implement asynchronous analysis job state, artifact provenance, and research-only report rendering.
5. Add interactive authorized MRI visualization and explicit model/inference metadata.

Exit criteria:

- A model mismatch or missing configuration fails closed.
- Every result records model hash and inference configuration.
- Reports make no clinical or independently validated claim.

## Phase 5 — Custom federated-learning coordinator foundation

Goal: build a Flower-free coordinator foundation without launching hospital training.

1. Establish dynamic hospital discovery, explicit training-node enrollment, model registration, and immutable round state.
2. Add deterministic FedAvg state/schema checks and dashboard reporting based only on persisted coordinator facts.
3. Isolate historical Flower evidence without representing it as coordinator activity.
4. Test failure handling for missing enrolled nodes, hash/schema mismatch, invalid sample counts, failed aggregation, and missing Groth16 verification.

Exit criteria:

- No round appears successful without recorded evidence.
- Metrics are labelled with their source, evaluation scope, and validation status.
- No training is triggered by a dashboard request without explicit authorized workflow controls.

## Phase 6 — ZK, chain, and artifact provenance

Goal: integrate only reviewed proof and chain semantics.

1. Pin circuit, WASM, verification-key, and contract versions/hashes.
2. Define proof artifact schemas and verification receipts without exposing witness/private update data.
3. Replace legacy local-chain credential fallback with environment-only configuration and deployment controls.
4. Integrate Groth16 verification and contract interactions with explicit unavailable/failed/rejected states.
5. Add content-addressed artifact references and clarify CID availability, privacy, and integrity semantics.

Exit criteria:

- Documentation accurately states what the circuit and contracts establish.
- Verification and anchoring claims are traceable to actual receipts.
- Private keys, proving keys, witnesses, and artifacts are outside the repository.

## Phase 7 — Hardening and release readiness

Goal: prove the system can be responsibly demonstrated as a research prototype.

1. Threat modelling, dependency/security scanning, secrets scanning, audit-log review, and access-control testing.
2. Load/failure testing for upload and analysis paths.
3. Accessibility, responsive UX, and visualization performance review.
4. Reproducible build/deployment documentation and operational runbooks.
5. Research-data governance, consent, retention, and clinical-use disclaimer review.

Exit criteria:

- All stated claims have recorded evidence.
- Demonstration data is synthetic or authorized de-identified material.
- The release checklist, test suite, build, and security review pass.

## Delivery discipline for every phase

1. Work only within the approved phase scope.
2. Run the tests, formatters, type checks, lint, and production build relevant to the change.
3. Review the diff and staged diff.
4. Scan intended staged files for secrets and prohibited MRI/model/proof artifacts.
5. Commit only validated, intended files with a descriptive message.
6. Push to origin/main without force-pushing or rewriting history.
