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
Concretely (interface design deferred to H.2C.3B, not implemented here):
every run submitted to a coordinator carries a required, non-optional
"stage" field (e.g. `SYNTHETIC_DEV`, `CALIBRATION_H3`, ...); the
coordinator process deployed into the personal-bootstrap project is
itself configured (via its own Terraform variable, not a runtime flag a
caller can override) with an explicit **stage allowlist** containing
only synthetic/development stage values. A request naming any other
stage is rejected before any work is admitted — the same "fail closed,
not merely undocumented" discipline this project already applies to,
e.g., `CollectorSelectionConfig.enabled` defaulting to `False` and
`execute_with_telemetry()` requiring an explicit factory. This is a
concrete H.2C.3B interface-design requirement flowing from this
checkpoint's specification.

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

| Identity | Environment | Purpose | Exact proposed Google APIs | Minimum proposed IAM roles / permissions | Resource scope | Auth mechanism | User interaction required? | First needed at | Verification procedure | Revocation/cleanup | Why not a broader role |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Human/developer identity | Both | Runs `gcloud`/console steps interactively at every credential boundary; owns the decision to authorize each step | `cloudresourcemanager.googleapis.com` (read), `iam.googleapis.com` (read) for verification only | N/A (human, uses their own existing Google identity) | Whichever project the current step targets | Interactive browser/`gcloud auth login` (the human's own session, never held or stored by the assistant) | Yes, always | H.2C.3C | `gcloud auth list` shows the expected active account | User's own account management (outside this project's scope) | N/A — this is the human, not a service identity |
| Personal bootstrap deployer | Personal | Runs `terraform apply`/`destroy` against the personal project | `compute.googleapis.com`, `pubsub.googleapis.com`, `storage.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com` (each enabled only when the corresponding H.2C.3C sub-step is authorized) | Project-level `roles/compute.instanceAdmin.v1`, `roles/pubsub.editor`, `roles/storage.admin` (bucket-scoped where possible), `roles/artifactregistry.writer`, `roles/secretmanager.admin` — each scoped to the personal project only, never `roles/owner`/`roles/editor` | Personal project only | User ADC (`gcloud auth application-default login`) | Yes | H.2C.3C | `gcloud projects get-iam-policy <personal-project> --flatten="bindings[].members" --filter="bindings.members:user:<email>"` shows exactly the roles above, nothing broader | `gcloud projects remove-iam-policy-binding` per role, or delete the personal project outright (it is disposable) | Terraform apply needs create/delete on specific resource types, not organization-wide or billing-account-wide authority |
| Company deployment identity | Company | Runs `terraform apply` against the company playground, after SRE review | Same API set as above, enabled under SRE-reviewed change control | Same role set as above, scoped to the company-playground project only, granted via SRE-reviewed process, never self-granted | Company-playground project only | Service-account impersonation (`gcloud auth print-access-token --impersonate-service-account=...`) or an approved CI federation mechanism (e.g. Workload Identity Federation) — never a downloaded key | Yes (to initiate impersonation) or no (if CI-federated, subject to SRE-approved automation) | H.2C.3E/F | SRE-provided IAM audit query confirming the deployment identity's own role bindings match the approved set | SRE-driven service-account/impersonation-binding removal | Deployment needs create/manage on specific resource types under this project only, never billing-account or org-level authority |
| Coordinator service account | Company (personal, minimal, for H.2C.3D synthetic testing) | Runs the coordinator process: admits work, reconciles trace/cache/audit, calls the cost-estimation logic | `pubsub.googleapis.com`, `storage.googleapis.com` (read/write on the run-manifest/trace prefixes only), `secretmanager.googleapis.com` (read-only, specific secrets) | `roles/pubsub.publisher` + `roles/pubsub.subscriber` (scoped to the specific topics/subscriptions), `roles/storage.objectAdmin` (bucket- or prefix-scoped, not project-wide), `roles/secretmanager.secretAccessor` (specific secrets only) | Specific Pub/Sub topics/subscriptions and Storage prefixes for this environment only | Attached VM/Cloud Run service account (no key ever downloaded) | No (runtime identity, not interactive) | H.2C.3D (personal, synthetic) / H.2C.3F (company, real) | `gcloud iam service-accounts get-iam-policy`/resource-level IAM check confirms no broader grant | Detach service account from the coordinator resource; delete the service account if retiring the environment | Coordinator never needs to create/delete IAM bindings, manage billing, or touch resources outside its own run's Pub/Sub topics and Storage prefixes |
| Worker service account | Company (personal, minimal, for H.2C.3D) | Runs on each Compute Engine worker VM: leases work, pulls the pinned runner/worker image, runs Docker, writes results | `pubsub.googleapis.com` (subscribe only), `storage.googleapis.com` (write to a results/trace prefix only), `artifactregistry.googleapis.com` (read/pull only) | `roles/pubsub.subscriber` (specific subscription), `roles/storage.objectCreator` (specific prefix, write-only — workers should not need to read or list other workers' results), `roles/artifactregistry.reader` | Specific Pub/Sub subscription, specific Storage write prefix, Artifact Registry read-only | Attached VM service account (Compute Engine's own instance service account, no key) | No | H.2C.3D (personal, synthetic) / H.2C.3F (company, real) | Same IAM-policy-check pattern as above | Detach from the MIG instance template; delete the service account if retiring | Worker never needs to publish to Pub/Sub (only consume), never needs Storage read/list beyond its own writes, never needs Artifact Registry write |
| Vertex model-invoker identity | Company (H.2C.3G only) | Calls Vertex AI Model Garden/MaaS for candidate generation | `aiplatform.googleapis.com` | `roles/aiplatform.user` (or a narrower predefined Vertex-invocation role if GCP offers one at the time of H.2C.3G — to be confirmed against current documentation then, not assumed now) | Company-playground project, specific to the frozen model portfolio's resource names | Attached service account (coordinator or a dedicated model-invoker identity), impersonation for any human-initiated pilot call | No (runtime) / Yes (for the "few minimal Vertex requests" validation step in the personal bootstrap, per §1.1) | H.2C.3G (company); H.2C.3C (personal, minimal validation only) | Vertex API call succeeds against a known-safe, non-billable-beyond-authorized-ceiling test prompt; response parses per the frozen provenance record | Remove `roles/aiplatform.user` binding | Model invocation needs prediction/generation calls only, never model-management, endpoint-deployment, or billing-account authority |
| SRE / org-admin identity | Company | Reviews and approves IAM, networking, quota, and organization-policy changes the deployment identity itself cannot self-grant | N/A (human, uses their own existing elevated access) | N/A — this is the human/team with organization-level authority this project's own identities explicitly do not have | Organization/company-wide, as already scoped by Standard AI's own existing SRE role | The org's own existing SRE tooling/process | Yes, always | H.2C.3E | The org's own existing SRE audit process (outside this project's scope to define) | The org's own existing process | N/A — this is intentionally the highest-privilege identity in the matrix, held by SRE, not by this project's own service accounts |
| CI identity (if eventually required) | Company (deferred) | Would run automated deployment/validation in a CI pipeline, if this project's own GitHub Actions CI is ever extended to touch GCP | Same API set as the deployment identity, if and when this is built | Same role set as the deployment identity, via Workload Identity Federation (no downloaded key, ever, for CI) | Company-playground project only | Workload Identity Federation from GitHub Actions' own OIDC token — **not designed or authorized in this checkpoint** | No (automated) | Not scheduled in the H.2C.3A–H decomposition; would require its own separate authorization if proposed later | N/A — not yet designed | N/A — not yet designed | Deferred entirely; recorded here only so the matrix names every identity category the amendment asked for, not because it is planned within H.2C.3A–H |

**First credential boundary**: per the accepted amendment, the first
point at which any actual authentication, project creation, or resource
provisioning could occur is **H.2C.3C** (personal GCP bootstrap and
just-in-time credential walkthrough) — not this checkpoint, and not
H.2C.3B (which is offline, provider-neutral interface design only).

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
