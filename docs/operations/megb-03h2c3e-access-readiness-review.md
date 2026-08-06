# MEGB-03H.2C.3E — Company-Playground Access and Readiness Review

**Status: read-only inspection only. No API enabled, IAM changed, quota
requested, billing attached, service account created, credential
created, network changed, or resource created by this checkpoint's own
authorized actions.** One incidental deviation occurred and is recorded
in §0. All findings below are redacted per the accepted amendment's
protected-metadata rule: project ID, project number, billing account
identifier, human/service-account email addresses, organization/folder
identifiers, and network names are never restated here, even though
several were visible in the interactive session that produced this
document.

This document records the H.2C.3E deliverables required by
`tickets/megb-03.md`, "Approved MEGB-03H.2C.3 Company-Playground-First
Amendment" §6 (12 numbered items). Section numbering below matches that
list.

## §0. Recorded deviation

During the read-only inspection, `gcloud org-policies list` triggered
`gcloud`'s own interactive prompt ("API [orgpolicy.googleapis.com] not
enabled... enable and retry?"), which the operator answered `y`. This
enabled `orgpolicy.googleapis.com` on the project — a real GCP state
change that occurred as a side effect of a read-only listing command,
outside the structured per-action approval protocol this checkpoint
otherwise followed for every other action. Assessed impact: low.
`orgpolicy.googleapis.com` is a free, non-billable metadata/config API;
it created no resource, IAM grant, or attack surface, and is not one of
the workload-required APIs in §3 below. Recorded here as a factual
deviation, not a defect that was silently corrected or hidden. For any
future checkpoint, the same class of prompt should be answered `N` and
reported back rather than accepted inline, so any further enablement
goes through the normal approval boundary.

## 1. Redacted current-access inventory

| Item | Finding |
|---|---|
| Environment class | `EnvironmentClass.COMPANY_PLAYGROUND` (per the accepted amendment) |
| Cloud provider | GCP |
| Active human identity | A single active `gcloud` account, company SSO identity, CTO role (self-attested — see §11) |
| Project | One company-playground project, confirmed by the operator as the correct target via console screenshot + explicit chat confirmation |
| Billing | Attached; project-scoped monthly budget, currently $0.00 spend |
| Budget alerting | Both configured thresholds are 100% — no early-warning tier (see §9) |
| Region/zone (planned) | `us-central1` (matches the cost model's own pricing anchor), zones `us-central1-a/b/c/f` available |
| VPC | One network, `default`, auto-subnet-mode (a subnet auto-created in every GCP region, not just the planned one) — no dedicated/custom VPC exists yet |
| Firewall (ingress) | SSH restricted to Google's IAP TCP-forwarding range only; RDP and SSH-from-internet explicitly denied; ICMP and internal traffic allowed — an existing, sane baseline, not something this checkpoint added |
| Firewall (egress) | No egress rules present at all — unrestricted outbound by GCP's implicit default (gap, see §4) |
| Enabled APIs (pre-existing) | `cloudkms.googleapis.com`, `cloudresourcemanager.googleapis.com`, `compute.googleapis.com`, `iamcredentials.googleapis.com`, `oslogin.googleapis.com` |
| Enabled APIs (this checkpoint, incidental) | `orgpolicy.googleapis.com` (§0) |
| Required APIs still disabled | `iam.googleapis.com`, `pubsub.googleapis.com`, `storage.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`, `aiplatform.googleapis.com`; also `logging.googleapis.com`/`monitoring.googleapis.com` (see §3) |
| IAM — human grants | 2 `roles/owner` bindings at project level — expected/low-risk for an individually-scoped playground |
| IAM — service accounts | Exactly one exists: the default Compute Engine service account, holding `roles/editor` (GCP's own out-of-the-box default, not something explicitly granted) — flagged in §2 and §11 |
| IAM — impersonation | The active human identity already holds `roles/iam.serviceAccountTokenCreator` and `roles/iam.serviceAccountUser` on the default Compute Engine service account — impersonation as a *mechanism* is confirmed working now; no dedicated least-privilege service account exists yet to impersonate instead |
| Quota (`us-central1`) | `N2_CPUS` 5000 limit / 0 used; `PREEMPTIBLE_CPUS` 10000 limit / 0 used — no constraint at any planning-relevant scale |
| Org policy (project-level) | None explicitly set at the project level (empty result) — org/folder-level inherited policy was not inspected (would require an `--effective` query per constraint, deferred to avoid triggering further incidental API-enablement prompts; recorded as an open SRE item in §11) |
| Existing compute resources | Zero Compute Engine instances |

## 2. Human / coordinator / worker IAM matrix (least-privilege target state)

None of the roles below have been granted by this checkpoint — this is
the target design for H.2C.3F, following the accepted architecture's
two-plane, non-transitive IAM model (execution-plane identity never
holds a Vertex/model-invoker role; generation-plane identity never holds
privileged-reference/Docker-host access).

| Identity | Current state | Target role set (H.2C.3F, not yet granted) |
|---|---|---|
| Human (CTO), active identity | `roles/owner` on the project (pre-existing playground default) | Unchanged for setup/admin actions; actual generation/execution workloads should run under dedicated service accounts below, not under this identity, to preserve two-plane isolation |
| Execution-plane (coordinator/worker) service account | Does not exist | Scoped Compute Engine instance/instance-group roles, execution-plane storage/object access, execution-plane Pub/Sub publish/subscribe (if used), Secret Manager accessor (execution-plane secrets only), Logging/Monitoring writer. **Never** an `aiplatform`/Vertex-invoker role. |
| Generation-plane (worker) service account | Does not exist | `aiplatform.user` (Vertex invocation), generation-write access to the candidate manifest location, Logging/Monitoring writer. **Never** privileged-reference/Docker-host access, **never** the execution-plane's own storage credentials. |
| Default Compute Engine service account | Holds `roles/editor` | Must not be attached to any H.2C.3F-created VM; either scoped down or excluded from use entirely — an SRE handoff item (§11), not fixed here |

## 3. Required-versus-enabled API matrix

| API | Required for H.2C.3F | Currently enabled |
|---|---|---|
| `compute.googleapis.com` | Yes | Enabled |
| `cloudresourcemanager.googleapis.com` | Yes | Enabled |
| `iam.googleapis.com` | Yes | Not enabled (only `iamcredentials.googleapis.com`, a distinct impersonation-token API, is enabled) |
| `pubsub.googleapis.com` | Yes (if the queue adapter uses Pub/Sub — see §6) | Not enabled |
| `storage.googleapis.com` | Yes | Not enabled |
| `artifactregistry.googleapis.com` | Yes | Not enabled |
| `secretmanager.googleapis.com` | Yes | Not enabled |
| `aiplatform.googleapis.com` (Vertex AI) | Yes | Not enabled |
| `logging.googleapis.com` | Yes (bounded logging is an accepted architecture/threat-model requirement) | Not enabled |
| `monitoring.googleapis.com` | Recommended | Not enabled |

Extras already enabled that are not required by this workload:
`cloudkms.googleapis.com`, `oslogin.googleapis.com` — pre-existing,
harmless, not something H.2C.3F needs to touch.

Net: 8 of 10 relevant APIs still require enabling, each an individual,
explicitly-approved action at the start of H.2C.3F, not performed here.

## 4. Network and egress-policy determination

- One VPC (`default`, auto-subnet-mode) exists, with a subnet
  auto-created in every GCP region — broader than the single-region
  (`us-central1`) footprint H.2C.3F actually needs.
- Ingress is already reasonably hardened: SSH only via IAP tunnel
  (`enable-ssh-access-via-iap`, priority 999), RDP/SSH-from-internet
  explicitly denied (`disable-ssh-rdp`, priority 1000) ahead of the
  legacy permissive default rules (priority 65534). This predates this
  checkpoint and is consistent with an org-wide playground baseline.
- **Gap**: no egress-restriction rule exists. All outbound traffic is
  currently allowed by GCP's implicit default-allow-egress. This is
  directly relevant to the "network-isolation-policy identity" concept
  flagged as missing/outcome-affecting in
  `docs/reference/megb-03h2c3a-gcp-provenance-audit.md`, and to the
  architecture doc's "no general internet egress from candidate
  containers" requirement (also cited in the cost model's §7).
- **Recommendation for H.2C.3F** (not performed here): either provision
  a dedicated custom-mode subnet scoped to `us-central1` only, or retain
  the existing default network and add an explicit deny-by-default
  egress rule with narrow allow-exceptions for required Google API
  endpoints, Artifact Registry, and any package mirrors workers need.
  Which of the two is preferable is an IaC/SRE design decision, not
  decided by this read-only checkpoint.

## 5. Quota and regional-capacity assessment

`us-central1` quota, current usage 0 in both cases:

| Metric | Limit |
|---|---|
| `N2_CPUS` | 5000 |
| `PREEMPTIBLE_CPUS` (covers Spot) | 10000 |

Four zones available (`us-central1-a/b/c/f`). At the scale implied by
any budget substantially below the $1,500 absolute ceiling (a handful of
4-vCPU Spot `n2-standard-4`-class workers, per the cost model's own
scenario parameters), quota is not a constraint. **Not a blocker for
H.2C.3F.**

## 6. Artifact Registry, storage, queue, logging, and secret-management decisions

None of these services have any existing footprint in the project — the
corresponding APIs (`artifactregistry`, `storage`, `pubsub`,
`secretmanager`, `logging`) are all currently disabled (§3), so there is
nothing pre-existing to inventory or reconcile. Decisions for H.2C.3F
(not created here):

- **Artifact Registry**: one Docker repository for the pinned runner
  image, `us-central1`-scoped, execution-plane-owned.
- **Storage**: separate execution-plane and generation-plane buckets or
  prefixes, mirroring the accepted architecture's write/read-only split
  for the candidate manifest (generation-plane writes, execution-plane
  reads only).
- **Queue**: if Pub/Sub is used for the coordinator/worker queue
  adapter (the existing offline `AtomicWorkStoreProtocol`/queue-adapter
  code is provider-neutral and does not mandate Pub/Sub specifically),
  separate topics per plane, least-privilege publish/subscribe roles
  per §2's matrix.
- **Logging**: bounded, redacted logging per the accepted threat
  model — no unrestricted per-invocation output, consistent with cost
  model §7's existing (not-yet-implemented) requirement.
- **Secret Manager**: execution-plane and generation-plane secrets
  (if any credentials beyond service-account impersonation are needed)
  stored separately, scoped accessor roles only, never a shared secret
  across planes.

## 7. IaC state/backend decision

No existing Terraform, Deployment Manager, or Config Connector state was
found; every resource observed in this review (the default network, its
firewall rules, the default service account) is a GCP project default,
not something provisioned by prior IaC. **Recommendation for H.2C.3F**:
adopt Terraform (or the company's own standard IaC tooling, if one
exists — worth confirming with SRE rather than assuming) with remote
state in a dedicated, versioned Cloud Storage bucket scoped to this
project. All H.2C.3F-provisioned resources should go through IaC rather
than manual `gcloud`/console actions, to keep the environment
reproducible and fully destroyable. This is a recommendation only —
no backend was created by this checkpoint.

## 8. Technical cost-refusal design

This restates and grounds, against the real environment observed in
this checkpoint, the mechanism already specified as "required, not yet
implemented" in `docs/measurement/gcp-experiment-cost-model.md` §7 and
Planning Amendment §5. Implementation remains H.2C.3F's job, not
H.2C.3E's.

- **Preflight cost estimate**: before any H.2C.3F run starts, compute
  `estimated_cost = compute_cost_estimate + vertex_cost_estimate +
  storage/egress_estimate`, using the *conservative* (higher) of any
  disagreeing Spot price sources (cost model §5's own guidance — here,
  $0.084/hr for `n2-standard-4` Spot, not the lower $0.066/hr figure).
  Refuse to start if `estimated_cost` exceeds the run's own frozen
  budget ceiling (§9 below).
- **Frozen limits, independently derived for `COMPANY_PLAYGROUND`** (per
  the amendment's explicit prohibition on reusing
  `PERSONAL_BOOTSTRAP_MAX_WORKERS`/`PERSONAL_BOOTSTRAP_SPENDING_CEILING_CENTS`):
  a maximum invocation count, a maximum concurrent-worker count, and
  maximum retry/token limits per call, all frozen before the run starts
  and never adjusted reactively mid-run.
- **Run-scoped circuit breaker**: tracks running cost (from actual
  observed per-invocation cost, not just the preflight estimate), error
  rate, telemetry-failure count, and retry-exhaustion count during the
  run; halts and tears down workers if any of these trend toward its
  frozen ceiling before it is actually exceeded — reusing the same
  graceful-teardown pattern already accepted for G.3/G.4
  (`KeyboardInterrupt`-driven cleanup, zero leftover containers).
- **Structural Vertex-cost isolation already holds today, independent
  of the above**: because the execution-plane identity (§2) is designed
  to never hold an `aiplatform`/Vertex-invoker role, a compromised or
  buggy execution worker cannot move `vertex_cost` at all — this is an
  IAM-design consequence, not a monitoring layer, and does not depend on
  anything else in this section being implemented first.
- **GCP budget alerts remain a monitoring signal only, not a
  substitute** for the above — reinforced by this checkpoint's own
  finding (§9) that the current project budget's alert thresholds are
  both set to 100%, i.e. no early warning at all under the alert
  mechanism alone.

## 9. Proposed initial qualification budget

The accepted $1,500 figure is an absolute campaign ceiling, not spending
authorization (per the amendment). Recommended initial H.2C.3F
qualification budget: **$100**, order-of-magnitude below the $1,500
ceiling and below the project's own $500 alert threshold, covering a
small number of Spot `n2-standard-4` workers for a short qualification
run plus a small number of real Vertex calls. This figure requires its
own explicit authorization at the start of H.2C.3F — it is proposed
here, not frozen or spent. Separately recommended (not requiring
authorization, since it changes no ceiling, only alerting): add earlier
budget-alert thresholds (e.g. 50%, 90%) to the existing $500 budget,
since both configured thresholds are currently 100%.

## 10. Resource cleanup/TTL policy

No existing TTL or cleanup automation was found (no scheduled jobs, no
expiry-labeled resources — consistent with zero existing compute
resources). Recommendation for H.2C.3F: every created resource carries
an explicit `ttl`/`expires` label and an owner label; the coordinator's
own run-scoped worker lifecycle (already part of the accepted
architecture) tears down workers at run completion; until a dedicated
sweep exists (e.g. a scheduled job that deletes/stops labeled resources
past TTL), a manual post-run audit is required after every H.2C.3F run.

## 11. SRE-owned actions and blockers

- The default Compute Engine service account holds `roles/editor` — a
  direct instance of threat #15 in the accepted threat model
  ("Service-account over-privilege... the accepted amendment explicitly
  forbids Owner/Editor as an implementation shortcut"). Needs an SRE
  decision: strip the role, or ensure it is simply never attached to any
  new resource.
- 8 of 10 relevant APIs are not yet enabled (§3) — each an individual,
  explicitly-approved action at the start of H.2C.3F.
- No dedicated VPC/subnet and no egress-restriction rule exist (§4) —
  needs a design decision (dedicated subnet vs. default network +
  egress rule) before any real worker runs.
- Org-policy inheritance from the org/folder level was not inspected
  (§1) — needs a follow-up review with org-level viewer access.
- No IaC currently exists (§7) — recommend adopting Terraform (or the
  company standard, to be confirmed with SRE) before any H.2C.3F
  resource creation.
- No TTL/cleanup automation exists (§10) — needs to be built alongside
  the first real H.2C.3F resource creation.
- Budget alert thresholds are both at 100%, no early-warning tier (§9).
- **READY-for-H.2C.3E-completion was reached via self-attestation**
  (the operator holds both the CTO role and SRE reporting line), not a
  separate, independent formal SRE sign-off — the operator explicitly
  chose this ("choice A") when offered the alternative of routing
  through formal SRE review first. Recorded here as a distinct fact:
  self-attested readiness is not the same claim as SRE-signed-off
  readiness, and this document does not conflate the two.
- The incidental `orgpolicy.googleapis.com` enablement (§0).

## 12. READY/BLOCKED decision for H.2C.3F

**GCP access and environment readiness itself: substantively READY**,
modulo the SRE handoff items in §11 above, none of which individually
block H.2C.3F's own setup work (API enablement, IAM grants, network
design, IaC adoption) from beginning once authorized.

**Overall decision: BLOCKED.** Not by anything found in this GCP review,
but by a pre-existing, code-level precondition documented in
`docs/reference/megb-03h2c3a-gcp-provenance-audit.md`'s "Revised
blocking precondition" section: H.2C.3F requires the same
distributed-execution provenance identity fields (environment
class/identity, cloud provider, region/zone, machine type,
provisioning class, worker/coordinator implementation versions,
network-isolation-policy identity, retry/lease-policy identity)
integrated into the **production** result/cache/audit identities —
`ReferenceRunContext` (`src/reference/result_schema.py`),
`ReferenceResultCacheKey` (`src/reference/cache_key.py`), and
`ReferenceAuditRecord` (`src/reference/reference_audit.py`) — in
addition to (not instead of) the calibration schema integration
H.2C.3B.1/B.3 already completed. Direct inspection of all three classes
in this checkpoint confirms none currently carry any distributed-
execution provenance field. Without this integration, a cached or
audited production result could be silently reused across materially
different environments (e.g. personal-bootstrap vs. company-playground,
or different machine types/regions), exactly the unsafe-reuse risk the
audit document identifies.

This is a schema-modification precondition, and the amendment
explicitly reserves schema modification for its own separately
authorized checkpoint, not H.2C.3E. Per that instruction, this document
stops and reports rather than modifying `ReferenceRunContext`,
`ReferenceResultCacheKey`, or `ReferenceAuditRecord` here. **Proposed
identifier for that checkpoint: `MEGB-03H.2C.3B.4`** (the next available
slot in the existing B.1/B.2A/B.2B.1–3/B.2C/B.3 decomposition) —
proposed only; not authorized, not begun, and requires its own explicit
authorization before H.2C.3F may proceed.

## Related documents

- `docs/reference/megb-03h2c3a-gcp-provenance-audit.md` — source of the
  production-schema-integration blocking precondition restated in §12.
- `docs/architecture/gcp-distributed-reference-execution.md`
- `docs/security/gcp-distributed-execution-threat-model.md`
- `docs/measurement/gcp-experiment-cost-model.md` — source of the cost
  enforcement design restated in §8 and the pricing figures in §9.
- `docs/operations/gcp-environment-promotion.md`
- `tickets/megb-03.md` — "Approved MEGB-03H.2C.3 Company-Playground-First
  Amendment", §6 (the 12-item deliverable list this document fulfills).
