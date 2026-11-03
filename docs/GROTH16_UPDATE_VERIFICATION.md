# Groth16 Update Verification Boundary

## Current status

The active V2 source includes a server-pinned Groth16 verifier for the
development-only `quantized-update-chunk-v1` circuit. When its manifest,
verification key, `snarkjs`, Node, and Poseidon helper are all configured and
pass integrity checks, it derives the public bindings from the protected model
update, verifies every required chunk with `snarkjs groth16 verify`, and records
the resulting public receipt metadata. It never accepts a client verification
key, proving key, witness, or artifact path.

This does **not** make the verifier production-ready: `is_ready` remains false,
and successful development-only verification always leaves
`aggregation_eligible` false. If artifacts or tooling are absent or invalid,
the verifier is unavailable and proof-required updates remain pending or are
rejected according to the fail-closed transport policy.

The protected proof envelope is stored outside PostgreSQL. PostgreSQL records
only its reference, SHA-256 receipt hash, circuit version, verification-key
identifier, explicit verification state, coverage state, and aggregation
eligibility. A SHA-256 value for an archive, model state, update state, or proof
receipt is an integrity commitment only, never a Groth16 proof.

## Required public inputs

A future reviewed circuit and verifier must pin and validate, at minimum:

1. a canonical training-round identifier/context commitment;
2. the base model-version state commitment;
3. the submitted hospital update commitment, calculated over a documented canonical tensor representation;
4. the circuit identifier, compiled R1CS/WASM hash, verification-key hash, and quantization specification;
5. the documented bound or relation being proven, including any update-norm/challenge/context binding; and
6. a proof-artifact reference/hash bound to the same public inputs.

The exact public-signal ordering must be versioned alongside the circuit. The coordinator must reject an output if any public input, circuit hash, verification-key hash, round context, or verifier receipt differs from the accepted specification.

## Private witness material

Private witnesses may include quantized update chunks, randomness/blinding values, local intermediate values, and other circuit-specific data. They must remain in the hospital environment or dedicated protected proving storage. They must not be written to PostgreSQL, API logs, browser state, Git, or the model-update archive.

## What a proof may establish

For the legacy `update_chunk` direction, a properly verified proof could establish the configured quantized-chunk/range, squared-norm contribution, commitment, challenge, and context relation. It does not by itself establish that an MRI dataset was authorized, that all U-Net parameters were trained correctly, that local optimization was clinically valid, that patient data remained private, or that a global model is clinically effective.

## Integration exit criteria

Before enabling aggregation, the project needs a threat-model review, pinned circuit/build/verifier artifacts, a real verifier test suite with valid and invalid proofs, canonical tensor/quantization compatibility tests, verifier receipts persisted as metadata, and an approved operational key/witness handling runbook. No blockchain deployment or recovery is part of this boundary.
