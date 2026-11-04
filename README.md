# ZKP-CerebraChain V2

ZKP-CerebraChain V2 is a research-oriented federated, zero-knowledge multi-modal MRI segmentation platform. It is being rebuilt as a maintainable full-stack system for hospital-scoped workflows, real MONAI 3D U-Net inference, federated model monitoring, and verifiable model-update provenance.

> Status: Phases 1–4 are complete. V2 has a FastAPI MRI API, PostgreSQL-backed hospital authentication and tenancy, and a React frontend for the authenticated MRI workflow. Federation, ZK verification, blockchain, IPFS, and MRI visualization are deliberately deferred.

## What V2 will support

- Hospital and doctor registration, authentication, and role-based access.
- Hospital-isolated dashboards and MRI study workflows.
- Upload, validation, segmentation, visualization, and research-only AI reports for four-modal brain MRI.
- Flower-based federated learning and FedAvg monitoring.
- Groth16 proof verification, blockchain anchoring, and content-addressed artifact tracking.

Clinical deployment is out of scope. Any future result must remain labelled research-only until the required clinical, security, privacy, and regulatory validation is complete.

## Implemented phases

- **Phase 1:** inspected legacy assets read-only, recorded the verified checkpoint, and established project boundaries and engineering rules.
- **Phase 2:** implemented the FastAPI MRI service, verified strict MONAI 3D U-Net loading, preserved the source modality order, and exposed protected segmentation artifact download.
- **Phase 3:** added PostgreSQL/Alembic identity and ownership records, hospital and doctor authentication, JWT validation, role checks, and hospital-level data isolation.
- **Phase 4:** added the React/Vite/Tailwind application with role-aware routes, in-memory bearer-token sessions, hospital and doctor dashboards, four-modality NIfTI upload, real result metadata, and authorized segmentation download.

## Repository layout

    apps/
      web/                  React + TypeScript + Vite application
    services/
      api/                  FastAPI application and Alembic migrations
    packages/
      ml-adapter/           Validated model-loading and inference boundary
      federation-adapter/   Flower integration boundary
      trust-adapter/        ZK, chain, and artifact-tracking boundary
      contracts/            Reviewed contract source and deployment tooling
      shared-types/         Cross-boundary schemas and generated API types
    infra/
      compose/              Local development orchestration, added only when needed
      monitoring/           Observability configuration, added only when needed
    docs/                   Architecture, assets, API plan, and delivery roadmap

## Verified legacy checkpoint

The source model remains outside this repository and is intentionally ignored by Git. The configured V2 integration will require an explicit path and expected SHA-256 value instead of relying on the legacy relative-path fallback.

| Item | Recorded value |
| --- | --- |
| Artifact | model_final.pth |
| SHA-256 | fb633c102af016310b89c6cb42f7cf65f78a3e63575cfe1a6075d14cd69b973f |
| Architecture | MONAI 3D U-Net; 4 inputs, 4 outputs; channels 16, 32, 64, 128, 256 |
| Compatibility check | Strict load passed; 48 state tensors; 2,453,636 parameters |
| Modality order | flair, t1, t1ce, t2 |

See docs/ASSET_INVENTORY.md for the exact read-only source path, provenance caveats, legacy evaluation status, and reuse decisions.

## Documentation

- docs/ARCHITECTURE.md — system boundaries, data flow, tenancy, and integration rules.
- docs/ASSET_INVENTORY.md — legacy asset inventory and compatibility findings.
- docs/API_PLAN.md — proposed versioned API surface and error contract.
- docs/DEVELOPMENT_ROADMAP.md — phased delivery plan and quality gates.
- docs/AUTH_API.md — implemented authentication and hospital-isolation API contract.
- docs/FRONTEND_DESIGN_SPEC.md — approved Healthcare SaaS visual direction.
- docs/FRONTEND_IMPLEMENTATION.md — frontend routes, API integration, and browser-security boundaries.

## Current constraints and safety

- No model was trained, copied, converted, or changed.
- No simulated predictions, federated rounds, proofs, transactions, or CIDs were created.
- The frontend stores access tokens in memory only. It does not write them to local or session storage.
- Protected API and PostgreSQL configuration must remain environment-provided. MRI inputs and derived masks remain in protected storage outside Git.
- MRI analysis is research-only and must not be described as a clinical diagnosis.

## Local frontend development

Copy `apps/web/.env.example` to an uncommitted `.env` file if a non-default API proxy target is required, then run:

```bash
cd apps/web
npm install
npm run dev
```

The API must be started separately with its own protected environment configuration and PostgreSQL database. See `services/api/.env.example` and `docs/AUTH_API.md`; do not place credentials, model paths, or MRI artifacts in the frontend environment file.

## Next phase

Phase 5 can add guarded axial, sagittal, coronal, and 3D result visualization from real authorized artifacts. It must not invent MRI imagery or measurements, and it must preserve the API tenancy boundary.
