# NeuroProof repository guardrails

- Canonical repository: `https://github.com/college-hack24-nov26/hack-neuroproof`.
- Work only on branch `main`; push only to the `origin` remote for that repository.
- Never push, mirror, or add a remote for `VisheshHari-Git/cerebrachain-v2` or any other repository.
- Before committing, fetch `origin/main`, preserve teammate changes, and stop for manual resolution if incoming changes conflict.
- Never force-push, reset shared history, redeploy/reset the existing Hardhat chain, or terminate unrelated processes.
- Do not stage secrets, `.env` files, credentials, private keys, mnemonics, databases, patient MRI data, datasets, generated private proofs, or additional trained weights without explicit authorization.
- Preserve hospital/doctor authentication, authorization, ownership isolation, and the distinction between synthetic/off-chain and on-chain Groth16 verification.
- V3 blockchain work is development-only: `development_synthetic_offchain_verified`, `production_eligible=false`, `onchain_groth16_verified=false`.
- The experimental global checkpoint is not clinically validated; do not represent it as such.
