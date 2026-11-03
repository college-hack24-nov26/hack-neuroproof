# Legacy Asset Inventory

## Inspection scope

The legacy project was inspected read-only at:

    /home/vishesh/hackethon projects/ZKP Phaltan/mypro/ZKP-CerebraChain-Step1-Backend/zkp-cerebrachain

No legacy source, checkpoint, dataset, run output, proof artifact, contract, or storage artifact was modified or copied into V2. The source checkpoint used by the legacy real-inference route resides beside that project:

    /home/vishesh/hackethon projects/ZKP Phaltan/mypro/cerebro-fl/model_final.pth

This path is an inventory record, not a V2 application default. V2 must require a configured external path and matching expected SHA-256 value.

## MRI model assets

| Asset | Location | Verification / status | V2 reuse decision |
| --- | --- | --- | --- |
| Source trained checkpoint | ../cerebro-fl/model_final.pth | 9,830,999 bytes; SHA-256 fb633c102af016310b89c6cb42f7cf65f78a3e63575cfe1a6075d14cd69b973f; strict load passed | Reuse by external configuration only; never copy or commit |
| FedAvg prototype checkpoint | runs/3d_fl_smoke/fedavg_round1_ABC/global_model.pth | 9,830,945 bytes; SHA-256 796779c9a046e22c9360ac2fb2283a9066a6f250fc8e480fe6b645df7eaa1941 | Read-only reference only until full provenance review |
| Two-hospital FedAvg prototype | runs/3d_fl_smoke/fedavg_round1_AB/global_model.pth | SHA-256 39d5476a68031bf4354b406f22a9d85e7de5eb4fec2719e15514ac3cd4d4de0c | Do not use as a production baseline |
| Secure-aggregation prototype | runs/3d_fl_smoke/secagg_quantized_round1_ABC/global_model.pth | SHA-256 8a2ecbcb1d38269a40918ed6635aa39213d66d77665acccd3ee5993b35df96ae | Read-only reference only |

The source checkpoint and the MONAI model construction in cerebrachain/unet3d/real_inference.py were verified compatible by loading with strict=True. The checkpoint contains 48 state tensors and the instantiated model has 2,453,636 parameters.

### Architecture

The legacy source model is:

| Field | Value |
| --- | --- |
| Library | MONAI |
| Network | UNet |
| Spatial dimensions | 3 |
| Input channels | 4 |
| Output channels | 4 |
| Channels | 16, 32, 64, 128, 256 |
| Strides | 2, 2, 2, 2 |
| Residual units | 1 |
| Normalization | instance |
| Model loader | cerebrachain/unet3d/model_adapter.py |

### Preprocessing, inference, and postprocessing

The legacy real pipeline in cerebrachain/unet3d/real_inference.py is the source of truth for a future compatibility test:

1. Load exactly four BraTS-style, aligned NIfTI volumes in the order flair, t1, t1ce, t2.
2. Reject missing volumes, non-3D shapes, unequal shapes, and unequal affine matrices.
3. Apply MONAI LoadImaged, EnsureChannelFirstd, NormalizeIntensityd with nonzero and channel_wise enabled, then EnsureTyped.
4. Add a batch dimension and reject non-finite values.
5. Run MONAI SlidingWindowInferer with a 96 by 96 by 96 ROI, batch size 1, 0.5 overlap, and Gaussian blending.
6. Take argmax across the four output classes.
7. Set prediction to background where FLAIR is zero and translate predicted label 3 to BraTS label 4.
8. Write a uint8 NIfTI with the reference affine and copied header.

The simpler preprocess.py and inference.py modules implement a separate experimental binary pathway; they must not be substituted for the above multi-class trained-model pipeline.

### Existing validation records

The legacy evaluation JSON files report a research-only comparison on one identified research case. The FedAvg prototype reports mean Dice 0.6103652185731115 versus 0.5964136481142311 for the source model. The secure-aggregation prototype reports mean Dice 0.6102449313615935 and a difference from FedAvg of -0.00012028721151802202.

These values are historical artifact metadata, not a V2 claim. The records explicitly mark independent pretraining holdout verification, distributed privacy verification, ZK proof verification, blockchain commitment, and clinical validation as false. They must not be presented as clinical performance or independently validated performance.

## Flower and FedAvg assets

| Component | Legacy location | Observed capability | V2 reuse decision |
| --- | --- | --- | --- |
| Canonical initialization | cerebrachain/unet3d/common_initialization_3d.py | Defines architecture identity, model hashing, metadata sidecar, strict checkpoint checks | Reuse patterns after API and configuration review |
| Dataset manifest | cerebrachain/unet3d/federation_manifest.py | Explicit A-D hospital mapping, fixed modality order, path/symlink checks, NIfTI header checks | Reuse validation concepts; do not copy local dataset assumptions |
| Flower state bridge | cerebrachain/unet3d/fl_bridge.py | Flattens/restores MONAI state dictionaries with schema checks | Candidate adapter code after tests are ported |
| Local 3D training | cerebrachain/unet3d/local_training_3d.py | Local checkpoint and metadata generation | Deferred; initial V2 phase must not train |
| Flower server/client | cerebrachain/unet3d/server_app_3d.py and client_app_3d.py | Flower ServerApp / ClientApp with canonical initialization checks | Candidate integration, requires configuration and security review |
| Live/replay variants | flower3d-v2-app, flower3d-v2-live-app, flower3d-v2-live16-app | Multiple experimental app variants with opt-in controls | Do not merge blindly; select one reviewed path later |
| FedAvg metadata | runs/3d_fl_smoke/fedavg_round1_ABC/aggregation_metadata.json | Three participants A/B/C, one sample each, sample-weighted FedAvg | Historical prototype only |

The recorded three-hospital FedAvg prototype specifies no secure aggregation, no ZK proof, no blockchain commit, and no independent validation. Its secure-aggregation comparison is a single-process smoke test, not evidence of distributed privacy.

The legacy documentation describes SuperLink ports and one SuperNode per hospital for a local demo. No V2 SuperLink or SuperNode is configured or started in Phase 1.

## ZK, blockchain, and IPFS assets

| Component | Legacy location | Observed capability / limitation | V2 reuse decision |
| --- | --- | --- | --- |
| Circuit | zk/circuits/update_chunk.circom | Quantized chunk range checks, squared-norm contribution, Poseidon commitment, challenge evaluation, and context binding | Review circuit/version binding before reuse |
| Circuit build metadata | zk/build/meta.json | Chunk size 4096, 46,674 constraints, 5 public signals | Do not copy proving material in Phase 1 |
| Prover | zk/prover.js | Witness and Groth16 proof orchestration | Deferred pending threat-model and artifact review |
| Registry contract | trust-layer/contracts/CerebraChainRegistry.sol | Round commits, Fiat-Shamir challenge, Groth16 verifier calls, update status and finalization | Candidate contract source; no deployment yet |
| Generated verifier | trust-layer/contracts/Groth16Verifier.sol | Solidity verifier for the compiled circuit verification key | Reuse only when circuit-build hashes are pinned and reverified |
| Proof anchor | trust-layer/contracts/CerebraChainProofAnchor.sol | Owner-recorded integrity root for externally verified proof sets | Do not claim this contract verifies individual proofs or clinical/training validity |
| Chain client | trust-layer/src/chain.js | Ethers wrapper around the registry | Do not reuse as-is: it includes a development local-chain key fallback |
| IPFS helper | trust-layer/src/ipfs.js | CIDv1 raw SHA-256 calculation, local content storage, optional Kubo pin attempt | Candidate utility after protected-storage review |

The recorded offline full-model proof manifest identifies 1,800 jobs and hashes for the verification key, WASM, and proving key, but Phase 1 did not run verification and does not claim the manifest represents a verified V2 proof set.

## Backend and portal assets

| Component | Legacy location | Observation | V2 reuse decision |
| --- | --- | --- | --- |
| Basic MRI API | cerebrachain/unet3d/api.py and real_api.py | FastAPI upload and real-inference route | Reimplement through V2 modules; legacy temp-file handling is not the final storage design |
| Doctor portal | cerebrachain/unet3d/doctor_api.py | Hospital-scoped local research portal with in-memory sessions and local account file | Use as a threat-model reference only, not a production authentication implementation |
| MRI preview | doctor_api.py | NIfTI slice preview and hospital path checks | Candidate visualization behavior after artifact-service design |

## Dependencies observed in legacy sources

The main legacy Python project declares Flower 1.39.0, Torch 2.2 or newer, NumPy 1.26 or newer, NiBabel 5.2 or newer, Cryptography, Requests, and Pytest. The isolated 3D Flower app additionally declares MONAI 1.3 or newer. The Node trust layer declares Circomlib, Ethers, Express, SnarkJS, Solc, and Hardhat.

These are inventory observations only. Phase 1 installed no dependencies in V2.

## Compatibility and security conclusions

1. The source trained model is technically compatible with the inspected MONAI construction, but it lives outside the legacy root and must be supplied explicitly to V2 through protected configuration.
2. There are divergent 2D and 3D legacy paths. V2 must retain only the reviewed 3D multi-modal pipeline for this feature.
3. Existing FedAvg, secure-aggregation, ZK, and chain artifacts are prototypes with documented unverified aspects. Their names or files do not constitute evidence of completed V2 functionality.
4. A legacy local-chain credential fallback is incompatible with V2 security requirements and must not be ported.
5. No patient MRI, model artifact, proving key, witness, private update, or IPFS payload may enter the V2 repository.
