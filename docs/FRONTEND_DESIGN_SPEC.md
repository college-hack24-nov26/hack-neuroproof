# Frontend Design Specification

## Status and source-of-truth order

This document records the required V2 frontend direction. It does not authorize frontend implementation.

The four supplied reference images are visual inspiration only. They must inform useful screen structure, navigation, and workflow hierarchy, but must not be reproduced pixel-for-pixel or used to justify exaggerated neon styling, crowded layouts, fabricated values, or decorative elements that reduce usability.

## Reference inspection record

The requested docs/design-references/ directory is not present. The four supplied images were instead found as untracked, local files at the repository root and inspected there. They were not moved, edited, staged, or committed.

| Reference image inspected | Interpreted role | Retained inspiration |
| --- | --- |
| Neon Doctor Portal Login Dashboard.png | Doctor login | Clear two-column entry flow, hospital context, concise role-specific actions |
| Neon Federated Brain Model Dashboard.png | Global Model Dashboard | Persistent navigation, top-level system status, model/round/metric information hierarchy |
| ZKP-CerebraChain MRI Analysis Dashboard.png | Doctor Dashboard and MRI workflow | MRI-analysis workspace, modality selection, orientation controls, result/provenance grouping |
| ZKP-CerebraChain Neon Login Dashboard.png | Hospital login and registration | Hospital/doctor entry choice and an obvious registration path |

The reference images visibly use very dark backgrounds, bright purple/cyan glow, strong gradients, glowing borders, decorative waves, and example success metrics. Those choices are explicitly superseded by the revised visual requirements below. Their displayed MRI results, metrics, verification states, transaction records, user details, and hospital counts are illustrative only and must not be copied as V2 data.

Visual decisions are resolved in this order:

1. Functional, security, privacy, data-integrity, accessibility, and responsiveness requirements in this specification.
2. The revised visual system and design guardrails in this specification.
3. Google Stitch exports, reviewed and refined against these requirements.
4. The four inspected reference images, as general layout and workflow inspiration only.

Stitch output must be refactored into maintainable React components, tokens, routes, and feature modules. It must not be pasted into a single generated page component or accepted without reviewing its colors, contrast, gradients, shadows, density, and accessibility.

## Visual language

The application must present as a professional, modern, readable Medical AI SaaS dashboard, not a generic administration dashboard or a high-intensity cyberpunk interface. Readability, workflow clarity, and visual comfort take priority over decorative effects.

### Required color system

| Token | Value | Intended use |
| --- | --- | --- |
| Background | #111827 | Main dark-navy canvas; never replace with pure black |
| Sidebar | #172033 | Persistent navigation and secondary shell surface |
| Card | #1E293B | Opaque or near-opaque content cards and form surfaces |
| Primary | #8B5CF6 | Primary actions, selected tabs, active navigation, and selection state |
| Secondary | #22D3EE | Limited supporting emphasis, data visualization, focus accents, and technical metadata |
| Text primary | #F1F5F9 | Primary headings, values, and body copy |
| Text secondary | #CBD5E1 | Supporting copy, labels, helper text, and subdued metadata |
| Border | #334155 | Low-emphasis card, input, and section separation |
| Success | #10B981 | Positive state only when supplied by real backend evidence |

Purple and cyan are accents, not background treatments. Purple is reserved primarily for active navigation, primary buttons, selected controls, and a small number of priority indicators. Cyan provides secondary emphasis and must not compete with primary actions. Success green must never imply a completed analysis, proof, or transaction without an actual verified result.

### Surface, typography, and motion rules

- Use dark navy rather than pure black, with calm tonal separation between the page, sidebar, and cards.
- Use clean cards with comfortable padding, consistent dimensions within a section, subtle shadows, and #334155 borders.
- Glassmorphism is permitted only as a restrained surface treatment: preserve opaque-enough panels and text contrast; do not place critical text over busy imagery.
- Do not apply glowing borders to every card or input. Glow is limited to transient focus feedback or a single selected/primary control, and must be subtle.
- Avoid large gradients. A restrained local tint is acceptable when it improves hierarchy, but gradients must not be the primary background, card, or chart treatment.
- Use a clear type scale with scannable headings, plain labels, readable body text, and no all-caps visual noise.
- Use comfortable whitespace and an intentional spacing scale. Prefer fewer, well-grouped panels over dense dashboard mosaics.
- Use Framer Motion only for useful state transitions, drawer/sidebar changes, progressive disclosure, and feedback. Respect reduced-motion preferences. Do not add looping decorative movement, particles, glowing pulses, or animated wireframes.
- Charts use muted, distinguishable series colors, direct labels/legends, and contextual text; they must not rely on saturated glow for meaning.

### Layout and interaction rules

- On desktop, use a professional sidebar plus a compact top utility bar where it improves orientation. The sidebar holds primary workflow navigation; the top bar holds contextual actions, notifications, and user/account controls.
- On smaller viewports, make navigation collapsible and prioritize one primary task at a time. Do not compress dashboard panels until labels, controls, or MRI content become unusable.
- Use one clear primary action per workflow section. Secondary actions must be visually quieter.
- Group related metrics and status information, but avoid an overloaded row of decorative KPI cards. Show only the decision-relevant information available for the active role.
- Use loading, empty, unavailable, permission-denied, error, pending, and completed states as deliberate layouts, not blank or misleading placeholders.
- Keep MRI visualization prominent on analysis screens; it receives more space than supplementary metrics or metadata.
- Use interactive 3D brain visualization only for authorized, real result data or meaningful manipulation of it. Do not add a decorative 3D brain, floating mesh, wave, or particle effect solely to fill space.

The final implementation must encode this visual system as reusable design tokens for color, spacing, radii, shadows, typography, chart colors, focus states, and animation timing. The inspected references and future Stitch output may inform component composition, but cannot override these rules.

## Reference-derived layout guidance

The four inspected screens establish useful information architecture without prescribing their visual treatment:

- Doctor login: use a concise role-specific authentication form beside a restrained explanation of the authorized MRI workflow. A hospital selector/context belongs with doctor authentication when required; use no medical image or segmentation as a false result preview.
- Hospital login and registration: provide a clear hospital-versus-doctor choice, a focused login form, and an obvious registration path. Avoid combining every field, benefit, and marketing message into the initial viewport.
- Global Model Dashboard: use a predictable shell, a concise network/model status area, a focused hospital/round summary, metric visualizations, and a records area. Values appear only from actual federation, proof, or chain records.
- Doctor Dashboard and MRI analysis: center the workspace on study selection, four-modality readiness, orientation controls, MRI slices/overlays, result provenance, and restrained supporting summaries. The three orthogonal views and a data-backed 3D view are workflow tools, not decorative panels.

## Required screens

| Screen | Purpose | Required content / integrity constraint |
| --- | --- | --- |
| Landing page | Explain the research platform and direct users to authorized workflows | Dark medical-technology hero, system overview, role entry points, clear research-only framing |
| Hospital login and registration | Hospital administrator onboarding and authentication | Separate login/registration paths, accessible form controls, explicit approval/error/pending states |
| Doctor login and registration | Doctor account onboarding and authentication | Hospital-aware account flow, accessible validation, no credential values in client logs |
| Hospital dashboard | Hospital-scoped operational overview | Authorized study/activity summaries, model/round status, empty/loading/error states |
| MRI upload and analysis | Submit four-modal MRI studies and observe analysis workflow | Explicit FLAIR, T1, T1CE, T2 requirements; upload validation and analysis status; no simulated result |
| Real 3D MRI segmentation viewer | Review authorized model output | Axial, sagittal, coronal views; interactive segmentation overlays; model/result provenance; unavailable state if no real result exists |
| Federated learning dashboard | Monitor the active custom coordinator | Registered hospitals, explicit training-node/agent enrollment, model versions, real round/update lifecycle, Groth16 verification state, aggregation eligibility, and separately labelled historical Flower evidence |
| Global model dashboard | Present registered global-model state and measured metrics | Model version/hash, provenance, validation scope, metrics only when actually recorded |
| ZKP verification dashboard | Present actual proof-workflow status | Circuit/version context, observed verification result, receipt metadata, explicit pending/failed/not-requested states |
| Blockchain explorer | Present actual on-chain provenance records | Configured network context, transaction hashes, model/anchor records, and unavailable/no-record states |

## MRI analysis and viewer requirements

The MRI workflow is a protected, hospital-scoped research workflow. It must support the verified modality order:

1. FLAIR
2. T1
3. T1CE
4. T2

The interface must make the four required modalities clear before submission and visually distinguish incomplete, validating, ready, queued, running, failed, and completed states.

The segmentation viewer must support:

- axial, sagittal, and coronal orientation controls;
- slice position controls appropriate to the rendered volume;
- interactive segmentation visibility and opacity overlays;
- an accessible legend for labels and overlays;
- provenance display for the model artifact hash, analysis time, and result status;
- loading, permission-denied, empty, failed, and unavailable states;
- responsive interaction patterns that remain usable without a large display.

The viewer must show only an actual authorized segmentation result returned by the backend/ML integration. Before that integration exists, it must render an explicit unavailable/empty state. It must not create synthetic masks, substitute arbitrary imagery, or imply a diagnostic result.

The existing trained MONAI 3D U-Net remains the planned model integration. Its loading, preprocessing, inference, and postprocessing stay in the backend ML boundary; React receives only authorized, derived visualization/report contracts.

## Federated-learning requirements

The federated dashboard must distinguish observed data from unavailable or unverified data. It must be able to show:

- participating hospitals and their permitted display names;
- registration, training-node enrollment, training-agent enrollment, and dataset-readiness as separate states;
- custom-coordinator round identifiers, lifecycle state, timestamps, participants, sample-count evidence, and aggregation configuration;
- registered global-model version/hash and provenance;
- measured validation metrics with their dataset/evaluation scope;
- hospital contribution records, Groth16 circuit/version context, proof verification status, and aggregation eligibility;
- historical Flower records only in a separate, read-only Historical Evidence section that is never labelled as custom-coordinator activity.

It must not fabricate a successful round, hospital participation, metric, model update, or validation result. Missing evidence must be represented visibly rather than converted to a positive status.

## ZKP, blockchain, and IPFS requirements

Trust-layer screens must show only actual backend-provided verification and chain records.

- Proof status must distinguish not_requested, pending, verified, rejected, failed, and unavailable.
- A proof view must identify the circuit/version binding and non-sensitive receipt metadata.
- A blockchain view must display actual configured-network context, transaction hashes, model records, and anchor records when present.
- A CID is an integrity/content-addressed reference; the UI must not imply that it proves clinical validity, training correctness, data provenance, privacy, availability, or authorization.
- The UI must state only the properties actually enforced by the circuit and verified workflow.
- No wallet key, proving key, private witness, raw private update, or protected artifact content may reach the browser.

## Modularity plan for later implementation

The future React application should use the following boundaries:

| Area | Intended location |
| --- | --- |
| Route composition and page shells | apps/web/src/app |
| Shared accessible visual primitives, restrained cards, and layout shell | apps/web/src/components/ui and apps/web/src/components/layout |
| Authentication workflows | apps/web/src/features/auth |
| Hospital overview workflows | apps/web/src/features/dashboard |
| Upload, viewer, and report workflows | apps/web/src/features/imaging |
| Federation monitoring | apps/web/src/features/federation |
| Proof/chain monitoring | apps/web/src/features/trust |
| Typed HTTP clients | apps/web/src/services |
| Shared browser types | apps/web/src/types |
| Design tokens and global styles | apps/web/src/styles |

React Three Fiber and Three.js should be isolated behind dedicated visualization components with graceful loading/error fallbacks. Recharts should consume normalized, typed monitoring data rather than make API calls directly. Framer Motion usage should remain at component/page transition boundaries, not inside domain services.

## Accessibility and responsive quality

- Maintain keyboard access, visible focus indicators, semantic landmarks, labelled form controls, and screen-reader names for all controls.
- Do not encode status only by color; use text, icons, and accessible labels.
- Respect reduced-motion preferences.
- Preserve sufficient contrast despite neon/glass styling.
- Provide usable layouts for narrow screens, including collapsible navigation and non-overlapping MRI/viewer controls.
- Make data tables, charts, and overlays understandable with textual summaries or accessible equivalents.

## Implementation gate

Frontend implementation may begin only when all of the following are available in the task scope:

1. Google Stitch design files or exported design assets.
2. The four reviewed reference images remain accessible locally as visual inspiration; their current untracked root paths must not be treated as application assets or staged accidentally.
3. A decision on the approved route/authentication contract from the backend foundation.
4. A confirmed backend contract for real MRI analysis and visualization artifacts before the segmentation viewer is connected.

Until then, this document is the design record and the repository must remain free of speculative frontend implementation. When Stitch designs arrive, they must be checked against the required palette, visual-comfort rules, responsive behavior, accessibility, modularity, and real-data constraints before any generated component is adopted.
