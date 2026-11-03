# Phase 4 Frontend Implementation

`apps/web` is a React, TypeScript, Vite, and Tailwind application for the
research-only hospital-scoped workflow. It implements the balanced dark-navy
Healthcare SaaS direction in [FRONTEND_DESIGN_SPEC.md](FRONTEND_DESIGN_SPEC.md),
without copying the supplied reference imagery or recreating its neon treatment.

## Routes

| Route | Purpose | Access |
| --- | --- | --- |
| `/` | Product introduction and workflow boundary | Public |
| `/hospital-login` | Hospital administrator sign-in | Public |
| `/doctor-login` | Doctor sign-in | Public |
| `/register` | Hospital and initial administrator registration | Public |
| `/app` | Role-aware hospital or doctor dashboard | Authenticated |
| `/app/mri-analysis` | Four-modality MRI upload and job submission | Authenticated |
| `/app/results/:jobId` | Authorized real result metadata and mask download | Authenticated |
| `/app/doctors` | Hospital administrator workspace | Hospital administrator |

## API integration

The browser uses a centralized API client and the actual endpoints in
[AUTH_API.md](AUTH_API.md): registration, login, `/auth/me`, logout, hospital
metadata, doctors, MRI cases, MRI submission, job status, and result/download.
It sends bearer tokens only from in-memory session state. Tokens are not written
to local storage, session storage, URLs, logs, or page state. Session expiry and
`401` responses clear the in-memory token and return the user to sign-in.

Vite development uses a same-origin `/api` proxy configured with
`VITE_API_PROXY_TARGET`; production should provide the same-origin reverse proxy.
`VITE_API_BASE_URL` is a public browser configuration value, not a secret.

## MRI workspace scope

The upload screen has explicit FLAIR, T1, T1CE, and T2 fields and performs only
client-side filename, emptiness, and configured-size feedback. The API remains
the authority for content, NIfTI validity, tenancy, checkpoint integrity, and
inference. The result workspace renders only values returned by the API and an
authorized segmentation download. It does not invent imagery, tumor metrics,
case IDs, or diagnostic claims. Interactive slice and 3D visualization remain
Phase 5 work.

## Validation boundaries

Frontend tests cover client-side MRI validation and protected-route behavior with
mocked browser state. Backend HTTP/database tests remain separately identified
as real integration tests and require their explicit external PostgreSQL and MRI
asset environment configuration.
