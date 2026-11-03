# Phase 3 Authentication API Contract

All endpoints below are implemented under `/api/v1`. Database-backed endpoints require PostgreSQL and a non-default `CEREBRACHAIN_JWT_SECRET` of at least 32 characters. The access token is a short-lived HS256 bearer token; the default expiry is 15 minutes.

## Shared rules

- Send authenticated requests with `Authorization: Bearer <access_token>`.
- Email addresses are normalized to lowercase.
- Passwords are accepted only over TLS in deployment, salted with scrypt, and never returned or logged.
- A `hospital_id` is never accepted from the browser to select tenancy. The active hospital comes from the validated token plus the current database membership.
- Invalid/missing/expired tokens return `401`; valid users without an administrator role return `403`; records outside the active hospital return `404`.
- Error responses use the existing envelope: `{ "error": { "code", "message", "request_id" } }`.

## Hospital registration and login

### `POST /auth/hospitals/register`

Request:

```json
{
  "hospital_name": "Example Research Hospital",
  "administrator_name": "Demo Administrator",
  "email": "admin@example.invalid",
  "password": "a-minimum-12-character-demo-password"
}
```

This creates exactly one hospital, one user, and a `hospital_admin` membership in one transaction. The response is an access-token object:

```json
{
  "access_token": "<short-lived-jwt>",
  "token_type": "bearer",
  "expires_at": "2026-11-01T00:00:00Z",
  "actor": {
    "user_id": "uuid",
    "full_name": "Demo Administrator",
    "email": "admin@example.invalid",
    "hospital_id": "uuid",
    "hospital_name": "Example Research Hospital",
    "hospital_slug": "example-research-hospital",
    "role": "hospital_admin"
  }
}
```

### `POST /auth/login`

Use this for both hospital administrators and doctors. The hospital slug makes the intended membership explicit:

```json
{
  "email": "doctor@example.invalid",
  "password": "the-user-password",
  "hospital_slug": "example-research-hospital"
}
```

The response uses the same access-token schema. Invalid passwords and invalid hospital contexts return the same `401` response so the API does not disclose account or membership existence.

### `GET /auth/me` and `POST /auth/logout`

`GET /auth/me` returns the `actor` object shown above. Logout is stateless: `POST /auth/logout` returns `204`, and the client must discard its access token. Tokens are short-lived; server-side refresh/revocation is deliberately out of scope for Phase 3 and must be introduced as a dedicated security change.

## Hospital administration

### `GET /hospitals/me`

Returns the active hospital only:

```json
{
  "id": "uuid",
  "name": "Example Research Hospital",
  "slug": "example-research-hospital",
  "role": "hospital_admin",
  "created_at": "2026-11-01T00:00:00Z"
}
```

### `POST /hospitals/me/doctors`

Hospital administrators create doctors for their own hospital. There is no hospital ID in the request:

```json
{
  "full_name": "Demo Doctor",
  "email": "doctor@example.invalid",
  "password": "a-minimum-12-character-demo-password"
}
```

The response is the safe `actor` representation with role `doctor`. `GET /hospitals/me/doctors` returns `{ "doctors": [ ... ] }` for administrators only.

### `GET /hospitals/me/mri-cases`

Returns `{ "cases": [{ "id", "case_reference", "created_at" }] }` scoped by the caller's live membership. Case references must be de-identified; MRI bytes and protected storage paths are never included.

## MRI authorization contract

`POST /mri/segment`, `GET /mri/jobs/{job_id}`, and `GET /mri/jobs/{job_id}/result` now require a bearer token. Before an upload is persisted, the API creates a PostgreSQL `mri_jobs` ownership record using the authenticated user and hospital. Status/result/download reads first constrain that record by the active hospital; cross-hospital job IDs return `404` without exposing their existence.

The multipart fields are `flair`, `t1`, `t1ce`, and `t2`; each accepts a NIfTI `.nii` or `.nii.gz` file within the configured size limit. The ML model, checkpoint verification, preprocessing, inference, and segmentation postprocessing are not modified by Phase 3 or Phase 4.

## Safe local demo procedure

1. Provision a dedicated local PostgreSQL database outside the repository and set `CEREBRACHAIN_DATABASE_URL` and a random `CEREBRACHAIN_JWT_SECRET` in an uncommitted environment file or deployment secret store.
2. Run `alembic upgrade head` from `services/api`.
3. Call hospital registration with synthetic `.invalid` email addresses and non-production passwords supplied at runtime.
4. Use the returned administrator bearer token to create a doctor, then authenticate the doctor through `/auth/login` using the returned `hospital_slug`.
5. Do not seed real patients, MRI files, keys, or production credentials. Remove the dedicated demo database when it is no longer needed.
