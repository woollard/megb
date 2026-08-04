# GCP Environment Promotion and Credential/Permission Plan (MEGB-03H.2C.3A)

**Status: design specification only. No GCP authentication, project
creation, API activation, IAM configuration, or resource creation
occurred in the production of this document.** Implements the "Approved
MEGB-03H.2C.3 Planning Amendment" §§3–4 (`tickets/megb-03.md`).

## 1. Two-environment model

### 1.1 Personal bootstrap environment

Purpose: disposable infrastructure development only.

| Property | Value |
|---|---|
| Project | A dedicated, disposable GCP project, distinct from the company playground |
| Fixtures | Synthetic and non-privileged only |
| Privileged artifacts | None — no partition/oracle/reference privileged content ever reaches this environment |
| Canonical solutions | None |
| Real candidate portfolios | None |
| Calibration/experiment | None — no full calibration or experiment run |
| Customer/company/proprietary data | None |
| Workers | Maximum 2 |
| GPUs | None |
| Vertex requests | At most a few minimal requests solely to validate authentication, API shape, response parsing, and provenance capture — only after H.2C.3C's own separate authorization for that specific step |
| Spending ceiling | $50 |
| Terraform state | Local or separately isolated from the company playground's state — never shared |

**Technical, not merely documented, refusal**: the personal environment
must refuse a privileged or real-experimental stage *by construction*.
Concretely (interface design deferred to H.2C.3B.1/B.2, not implemented
here): every run submitted to a coordinator carries a required,
non-optional "stage" field (e.g. `SYNTHETIC_DEV`, `CALIBRATION_H3`, ...);
the coordinator process deployed into the personal-bootstrap project is
itself configured (via its own Terraform variable, not a runtime flag a
caller can override) with an explicit **stage allowlist** containing
only synthetic/development stage values. A request naming any other
stage is rejected before any work is admitted — the same "fail closed,
not merely undocumented" discipline this project already applies to,
e.g., `CollectorSelectionConfig.enabled` defaulting to `False` and
`execute_with_telemetry()` requiring an explicit factory. This is a
concrete H.2C.3B.1 interface-design requirement flowing from this
checkpoint's specification.

**Scope of what the personal environment can establish (corrected after
initial review)**: the personal bootstrap **may validate mechanics,
recovery, isolation, telemetry availability, and cost behavior** — it is
a real, legitimate proving ground for *does the distributed machinery
work at all* (Spot preemption recovery, at-least-once idempotency,
deterministic ordering, container cleanup, telemetry-collector
selection/quality on a real Compute Engine VM, cost-enforcement
circuit-breaker behavior). **It must not, by itself, be treated as
establishing scientific equivalence for the company environment** — a
different project, different quota/network posture, and (per
`docs/reference/megb-03h2c3a-gcp-provenance-audit.md`'s own
environment-identity gap) a distinct logical execution context. Personal-
bootstrap results feed MEGB-03H.2C.3D's own qualification report,
labeled and gated as personal-environment evidence (see that document's
own `qualifying`-flag precedent from `H2C2BQualificationReport`); they
do not substitute for MEGB-03H.2C.3F's own company-playground
qualification run.

**Destruction/cleanup**: the personal bootstrap is designed to be torn
down and recreated freely (`terraform destroy` against its own isolated
state) — no resource in it is intended to outlive a single development
session's usefulness. A concrete teardown checklist (bucket emptying
before deletion, confirming no orphaned Compute Engine instances/disks,
confirming billing has actually stopped) is an H.2C.3C deliverable, not
frozen here.

### 1.2 Standard AI company playground

Purpose: the only environment eligible for real calibration, privileged-
artifact access, candidate-generation campaigns, or scientific runs.

| Property | Value |
|---|---|
| Project | Created under the company organization, billing account, IAM, and network controls |
| Deployment | Clean deployment from the same infrastructure-as-code source as the personal bootstrap — never a hand-modified copy |
| Imports from personal environment | **None** — no personal Terraform state, service accounts, credentials, buckets, or logs |
| IAM/networking | SRE-reviewed before any real run |
| Promotion gate | Must pass the formal environment-promotion and qualification gate (§2 below) before any real run |
| Budget ceiling | $1,500 for a full campaign, unless separately amended |

### 1.3 What may be promoted from personal to company

- Source code.
- Declarative infrastructure definitions (Terraform/OpenTofu modules).
- Versioned configuration (non-secret variables, e.g. machine-type
  choices, sampling intervals).
- Pinned container-image *definitions* (Dockerfiles, build
  specifications) — not a specific already-built image identity, which
  is rebuilt and re-pinned fresh for the company environment.
- Safe, synthetic qualification reports (e.g. the H.2C.3D deliverable),
  as evidence the mechanism works — never as a substitute for the
  company playground's own qualification run.

### 1.4 What may never be promoted

- Terraform state.
- Credentials of any kind.
- Service-account keys.
- Personal bucket contents.
- Personal resource IDs (project number, instance names, bucket names).
- Personal logs.
- Personal audit/trace/calibration records.
- Cached candidate results.
- Any personal-environment-generated scientific evidence — by
  construction, the personal environment cannot produce scientific
  evidence at all (§1.1's stage allowlist), so this rule is a second,
  independent backstop, not the only control.

## 2. Company-playground qualification gate

**Qualification wording, corrected**: Compute Engine MIG (the substrate
`gcp-distributed-reference-execution.md` §5 selects) is the approved
*initial implementation baseline*, not yet a *scientifically qualified*
execution substrate. Scientific qualification occurs only after
MEGB-03H.2C.3D (personal, synthetic, distributed qualification) and,
for the company environment specifically, this gate's own evaluation at
MEGB-03H.2C.3F. Nothing in this document, or in H.2C.3A generally,
asserts the substrate is already qualified.

Before any real work (privileged-artifact access, candidate generation,
scientific run) on the company playground, **all** of the following are
required, none waivable by this or any single future checkpoint acting
alone:

1. Correct GCP project number, environment identity, region,
   infrastructure revision, and service-account identities recorded.
2. No personal-account credentials or resources involved.
3. SRE-reviewed IAM and networking.
4. Pinned runner-image provenance.
5. Candidate network isolation (re-verified against the real substrate).
6. Exact or explicitly classified telemetry (never a silent gap — the
   same `MeasurementQuality` discipline already accepted for the local
   design).
7. Status and return-value equivalence with telemetry disabled/enabled.
8. Deterministic ordered results under concurrency.
9. Cross-invocation writable-state isolation.
10. Spot interruption and resumption without duplicate or missing
    scientific coordinates.
11. Cache, trace, and audit reconciliation.
12. Zero leftover containers.
13. Bounded logging with leakage tests.
14. Measured throughput and projected stage runtimes.
15. Measured cost and projected full-campaign cost.
16. A READY/BLOCKED classification.

**No privileged or canonical run occurs if any mandatory gate is
blocked.** This mirrors exactly the discipline MEGB-03H.2C.2B already
established for the local substrate (its own `TELEMETRY_READY_FOR_MEGB_03H3`
/`BLOCKED` taxonomy) — the company playground gets its own analogous,
explicit gate rather than an implicit "it probably works" assumption.
H.2C.3F is the checkpoint that evaluates this gate for real.

## 3. Credential and permissioning interaction protocol (mandatory, all future GCP checkpoints)

Whenever authentication, credentials, billing, API activation, IAM,
organization policy, model access, quota, networking, or service-account
configuration becomes necessary at any future checkpoint, the assistant
must **stop before taking the action** and walk the user through it
interactively, providing all ten of:

1. Why the credential or permission is needed.
2. Whether it belongs in the personal bootstrap or the company
   playground.
3. The exact API, role, permission, quota, or resource involved.
4. The minimum privilege required.
5. The exact console steps and/or `gcloud` commands for the user to
   execute themselves.
6. Any billing or security consequence.
7. A verification command and the expected safe output.
8. How the permission or credential can later be revoked or cleaned up.
9. What non-secret identity/provenance fields will be recorded.
10. A clear stop asking the user to confirm completion before
    proceeding.

**Credential rules** (in force for every future GCP checkpoint):

- Never ask the user to paste passwords, access tokens, private keys,
  service-account JSON, or other secret material into chat.
- Never print or commit secrets.
- Never create or download a long-lived service-account key unless an
  independently documented blocker proves no keyless option works and
  the user explicitly authorizes it.
- Prefer user Application Default Credentials (ADC) for the disposable
  personal bootstrap.
- Prefer service-account impersonation, attached-VM service accounts,
  Workload Identity Federation, or another keyless mechanism for the
  company environment.
- Never reuse personal credentials in the company environment.
- Never silently use ambient company credentials merely because they
  happen to be present.
- Never enable paid APIs, accept publisher/model terms, request quota,
  or create billable resources without that specific checkpoint's
  explicit authorization.
- If SRE or organization-admin action is required, produce a minimal
  handoff checklist instead of attempting to bypass the restriction.

## 4. Just-in-time credential/permission matrix

This is a **planning artifact only**. No entry below has been executed;
no authentication or configuration occurred in producing it. Every "exact
proposed Google APIs"/"minimum proposed IAM roles" value is a proposal
for the checkpoint that will actually request it to confirm (against
current GCP documentation and the company's own IAM conventions) before
acting.

**Corrected after initial review**: the table below now names the
reference-execution plane's and candidate-generation plane's service
accounts as explicitly distinct rows with disjoint role sets, per
`gcp-distributed-reference-execution.md` §2's non-transitive-permission
correction. The four non-negotiable rules, restated here because they
govern this table directly:

1. **The execution-worker (and execution-plane coordinator) service
   account must never receive Vertex model-invoker permission** — no
   entry for it exists in either of those two rows below, and none may
   be added without reopening this correction.
2. **The generation-plane coordinator/model-invoker service account
   must never receive access to privileged oracle/reference artifacts
   or the Docker execution host** — no entry for it exists in that row
   below.
3. Pub/Sub messages on either plane's queue carry opaque work
   references and allowlisted routing metadata only (enforced by
   message-schema design, H.2C.3B.1/B.2 — see the provenance audit).
4. A compromise of the execution plane can never amplify Vertex cost,
   because the credential path does not exist (structural, per threat
   #26 in `gcp-distributed-execution-threat-model.md`).

| Identity | Environment | Purpose | Exact proposed Google APIs | Minimum proposed IAM roles / permissions | Resource scope | Auth mechanism | User interaction required? | First needed at | Verification procedure | Revocation/cleanup | Why not a broader role |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Human/developer identity | Both | Runs `gcloud`/console steps interactively at every credential boundary; owns the decision to authorize each step | `cloudresourcemanager.googleapis.com` (read), `iam.googleapis.com` (read) for verification only | N/A (human, uses their own existing Google identity) | Whichever project the current step targets | Interactive browser/`gcloud auth login` (the human's own session, never held or stored by the assistant) | Yes, always | H.2C.3C | `gcloud auth list` shows the expected active account | User's own account management (outside this project's scope) | N/A — this is the human, not a service identity |
| Personal bootstrap deployer | Personal | Runs `terraform apply`/`destroy` against the personal project (both planes' modules) | `compute.googleapis.com`, `pubsub.googleapis.com`, `storage.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com` (each enabled only when the corresponding H.2C.3C sub-step is authorized) | Project-level `roles/compute.instanceAdmin.v1`, `roles/pubsub.editor`, `roles/storage.admin` (bucket-scoped where possible), `roles/artifactregistry.writer`, `roles/secretmanager.admin` — each scoped to the personal project only, never `roles/owner`/`roles/editor` | Personal project only | User ADC (`gcloud auth application-default login`) | Yes | H.2C.3C | `gcloud projects get-iam-policy <personal-project> --flatten="bindings[].members" --filter="bindings.members:user:<email>"` shows exactly the roles above, nothing broader | `gcloud projects remove-iam-policy-binding` per role, or delete the personal project outright (it is disposable) | Terraform apply needs create/delete on specific resource types, not organization-wide or billing-account-wide authority. This is the *deployer*, not a runtime identity — it does not itself run workloads on either plane. |
| Company deployment identity | Company | Runs `terraform apply` against the company playground (both planes' modules), after SRE review | Same API set as above, enabled under SRE-reviewed change control | Same role set as above, scoped to the company-playground project only, granted via SRE-reviewed process, never self-granted | Company-playground project only | Service-account impersonation (`gcloud auth print-access-token --impersonate-service-account=...`) or an approved CI federation mechanism (e.g. Workload Identity Federation) — never a downloaded key | Yes (to initiate impersonation) or no (if CI-federated, subject to SRE-approved automation) | H.2C.3E/F | SRE-provided IAM audit query confirming the deployment identity's own role bindings match the approved set | SRE-driven service-account/impersonation-binding removal | Deployment needs create/manage on specific resource types under this project only, never billing-account or org-level authority |
| **Execution-plane** coordinator service account | Company (personal, minimal, for H.2C.3D synthetic testing) | Runs the execution-plane coordinator: admits reference-execution work, reconciles trace/cache/audit, calls the execution-side cost-estimation logic. **Reads (read-only) the generation plane's candidate-manifest bucket to resolve which manifest entry to execute; never writes there.** | `pubsub.googleapis.com` (execution topic/subscription only), `storage.googleapis.com` (read/write on the execution-plane run-manifest/trace prefix; **read-only** on the generation-plane manifest prefix), `secretmanager.googleapis.com` (read-only, specific execution-plane secrets) | `roles/pubsub.publisher` + `roles/pubsub.subscriber` (scoped to the execution-plane topics/subscriptions only), `roles/storage.objectAdmin` (execution-plane bucket/prefix only) + `roles/storage.objectViewer` (generation-plane manifest prefix only), `roles/secretmanager.secretAccessor` (specific execution-plane secrets only). **No `aiplatform.*` role, ever.** | Execution-plane Pub/Sub topics/subscriptions and Storage prefix; read-only on the generation-plane manifest prefix | Attached VM/Cloud Run service account (no key ever downloaded) | No (runtime identity, not interactive) | H.2C.3D (personal, synthetic) / H.2C.3F (company, real) | `gcloud iam service-accounts get-iam-policy`/resource-level IAM check confirms no broader grant **and specifically confirms no `aiplatform.*` role is bound** | Detach service account from the coordinator resource; delete the service account if retiring the environment | The execution-plane coordinator never needs to create/delete IAM bindings, manage billing, touch resources outside its own plane's topics/prefixes, or call Vertex — candidate generation is entirely the other plane's responsibility |
| **Execution-plane** worker service account | Company (personal, minimal, for H.2C.3D) | Runs on each Compute Engine worker VM: leases execution work, pulls the pinned runner/worker image, runs Docker, writes results | `pubsub.googleapis.com` (subscribe only, execution subscription), `storage.googleapis.com` (write to the execution-plane results/trace prefix only), `artifactregistry.googleapis.com` (read/pull only) | `roles/pubsub.subscriber` (specific execution subscription), `roles/storage.objectCreator` (execution-plane prefix, write-only — workers should not need to read or list other workers' results, and have **no access to the generation-plane bucket at all**), `roles/artifactregistry.reader`. **No `aiplatform.*` role, ever — the single most safety-critical omission in this entire matrix, since this identity runs on the same VM as untrusted candidate code.** | Specific execution-plane Pub/Sub subscription, specific execution-plane Storage write prefix, Artifact Registry read-only | Attached VM service account (Compute Engine's own instance service account, no key) | No | H.2C.3D (personal, synthetic) / H.2C.3F (company, real) | Same IAM-policy-check pattern as above, **plus an explicit assertion that `roles/aiplatform.user` (or any `aiplatform.*` role) is absent** | Detach from the MIG instance template; delete the service account if retiring | Worker never needs to publish to Pub/Sub (only consume), never needs Storage read/list beyond its own writes, never needs Artifact Registry write, and — critically — never needs any Vertex permission, since it never generates candidates |
| **Candidate-generation-plane** coordinator / Vertex model-invoker service account | Company (H.2C.3G for real Vertex calls; H.2C.3C for the few minimal personal-bootstrap validation calls) | Runs the generation-plane coordinator: admits generation work, calls Vertex AI Model Garden/MaaS, writes immutable candidate manifests. **Never executes candidate code; never reads privileged reference/oracle/cache content; never reaches a worker's Docker daemon.** | `aiplatform.googleapis.com`, `pubsub.googleapis.com` (generation topic/subscription only), `storage.googleapis.com` (read/write on the generation-plane manifest prefix only — **no access to the execution-plane bucket**) | `roles/aiplatform.user` (or a narrower predefined Vertex-invocation role if GCP offers one at the time of H.2C.3G — to be confirmed against current documentation then, not assumed now), `roles/pubsub.publisher`/`subscriber` (generation-plane topics only), `roles/storage.objectAdmin` (generation-plane prefix only). **No role granting access to the execution-plane bucket, the privileged-reference prefix, or any Compute Engine/Docker-related permission, ever.** | Company-playground project, generation-plane Pub/Sub topics and Storage prefix, Vertex resources specific to the frozen model portfolio's resource names | Attached service account (generation-plane coordinator), impersonation for any human-initiated pilot call | No (runtime) / Yes (for the "few minimal Vertex requests" validation step in the personal bootstrap, per §1.1) | H.2C.3G (company); H.2C.3C (personal, minimal validation only) | Vertex API call succeeds against a known-safe, non-billable-beyond-authorized-ceiling test prompt; response parses per the frozen provenance record; **IAM check confirms no privileged-reference-bucket or Compute-Engine-management role is bound to this identity** | Remove `roles/aiplatform.user` binding | Model invocation needs prediction/generation calls only, never model-management, endpoint-deployment, billing-account authority, or any access to the execution plane's own resources |
| SRE / org-admin identity | Company | Reviews and approves IAM, networking, quota, and organization-policy changes the deployment identity itself cannot self-grant — **including confirming the two planes' service accounts have disjoint role sets (threat #29)** | N/A (human, uses their own existing elevated access) | N/A — this is the human/team with organization-level authority this project's own identities explicitly do not have | Organization/company-wide, as already scoped by Standard AI's own existing SRE role | The org's own existing SRE tooling/process | Yes, always | H.2C.3E | The org's own existing SRE audit process (outside this project's scope to define), extended to a role-set-disjointness check between the two planes' identities | The org's own existing process | N/A — this is intentionally the highest-privilege identity in the matrix, held by SRE, not by this project's own service accounts |
| CI identity (if eventually required) | Company (deferred) | Would run automated deployment/validation in a CI pipeline, if this project's own GitHub Actions CI is ever extended to touch GCP | Same API set as the deployment identity, if and when this is built | Same role set as the deployment identity, via Workload Identity Federation (no downloaded key, ever, for CI) | Company-playground project only | Workload Identity Federation from GitHub Actions' own OIDC token — **not designed or authorized in this checkpoint** | No (automated) | Not scheduled in the H.2C.3A–H decomposition; would require its own separate authorization if proposed later | N/A — not yet designed | N/A — not yet designed | Deferred entirely; recorded here only so the matrix names every identity category the amendment asked for, not because it is planned within H.2C.3A–H |

**First credential boundary**: per the accepted amendment, the first
point at which any actual authentication, project creation, or resource
provisioning could occur is **H.2C.3C** (personal GCP bootstrap and
just-in-time credential walkthrough) — not this checkpoint, and not
H.2C.3B.1/B.2 (which are offline, provenance-schema and provider-neutral
interface design only).

## 5. Rollback and teardown

- **Personal bootstrap**: `terraform destroy` against its own isolated
  state; confirm via `gcloud` that no Compute Engine instances, Cloud
  Storage buckets, or Pub/Sub resources remain in the personal project
  before considering a session's cleanup complete. Full checklist
  specified at H.2C.3C.
- **Company playground**: never torn down casually — any destructive
  action against company-playground infrastructure requires the same
  SRE-reviewed process that approved its creation. A promotion-gate
  failure (§2) blocks *further* work, it does not by itself authorize
  destroying already-approved infrastructure.

## Related documents

- `docs/architecture/gcp-distributed-reference-execution.md`
- `docs/security/gcp-distributed-execution-threat-model.md`
- `docs/measurement/gcp-experiment-cost-model.md`
- `docs/reference/megb-03h2c3a-gcp-provenance-audit.md`
- `tickets/megb-03.md` — "Approved MEGB-03H.2C.3 Planning Amendment"
