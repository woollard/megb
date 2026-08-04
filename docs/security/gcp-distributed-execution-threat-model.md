# GCP Distributed Execution Threat Model (MEGB-03H.2C.3A)

**Status: design specification only.** Extends `execution-threat-model.md`
(MEGB-02's single-host threat model, which remains authoritative for the
candidate-vs-controller trust boundary itself) to the distributed
architecture in `docs/architecture/gcp-distributed-reference-execution.md`.
No claim of kernel-grade isolation is made anywhere in this document —
MEGB-02's own "Out of scope" section (container-runtime/kernel 0-days)
applies unchanged; distributing across many worker VMs does not add or
remove that residual risk, it only multiplies the number of VMs it
applies to.

## Protected assets (extends MEGB-02's list)

- Everything in `execution-threat-model.md`'s existing asset list
  (host OS, this repository, host credentials, canonical HumanEval/+
  solutions, evaluator source, evaluation availability, the runner's
  protocol-response integrity) — now per-worker-VM instead of
  per-laptop.
- The company organization's GCP billing account and IAM boundary.
- The personal bootstrap project's own (much smaller) billing exposure.
- Cloud Storage buckets holding run manifests, calibration traces, audit
  records, and any staged privileged artifacts.
- Terraform/OpenTofu state (may itself reveal resource topology, service
  account emails, or bucket names — treated as sensitive even though it
  should never contain secret values directly).
- Pub/Sub topics/subscriptions carrying work admission messages.
- Artifact Registry's pinned runner/worker image digests.
- Vertex AI model access/quota and any associated per-call cost.
- The scientific integrity of the calibration/experiment record itself —
  i.e., the guarantee that a result is attributable to the correct
  environment, worker, and provenance, and that no personal-bootstrap
  synthetic result is ever mistaken for company-playground scientific
  evidence.

## Adversary model (extends MEGB-02's list)

In addition to MEGB-02's adversarial-candidate-code assumption (every
`candidate_code` value is deliberately adversarial), this document adds:

- **Operational/configuration adversity**: misconfiguration, human error,
  or a bug in coordinator/worker/IaC code can produce the same outcome
  as a deliberate attack (credential leakage, cross-environment
  contamination, cost overrun) — several rows below have no "malicious
  actor" per se, only a failure mode with real consequences.
- **Infrastructure-level adversity**: Pub/Sub's own at-least-once
  delivery, Spot preemption, and worker/coordinator crashes are *normal*
  GCP behavior, not attacks — but a system that is not designed for them
  can be driven into an unsafe state by them, which is treated here with
  the same rigor as a deliberate attack.
- **Not assumed**: a nation-state-level attacker with GCP-internal
  access, a Google-side security failure, or a kernel/hypervisor
  0-day against Compute Engine's own virtualization boundary. These are
  Google's responsibility under the GCP shared-responsibility model, not
  this project's.

## Trust boundaries

```
Untrusted:  candidate container (per invocation, on any worker VM)
Trusted:    worker process, worker VM's Docker daemon, coordinator process,
            Terraform/OpenTofu apply identity, SRE/org-admin identity
Semi-trusted (operationally, per environment):
            personal-bootstrap deployer identity (disposable, low-blast-radius)
            company-playground deployment identity (high-blast-radius, SRE-reviewed)
External:   Vertex AI Model Garden/MaaS (Google-operated managed service)
```

The candidate-container boundary is unchanged from MEGB-02. This
document's new boundaries are: **personal environment vs. company
environment** (must never cross without explicit, reviewed promotion),
and **coordinator/worker vs. Google-managed services** (Pub/Sub, Cloud
Storage, Vertex, IAM — trusted per GCP's own shared-responsibility model,
but every credential this project's own code holds toward them must
still follow least privilege).

## Threat / control matrix

| # | Threat | Protected asset | Trust boundary | Failure mode | Preventive control | Detective control | Recovery behavior | Residual risk | Verifying checkpoint |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Malicious candidate code | Host OS, repo, credentials, evaluator integrity | Candidate container ↔ worker | Candidate attempts resource exhaustion, sandbox escape, protocol forgery | Unchanged MEGB-02 controls: `--network none`, read-only rootfs, dropped capabilities, `no-new-privileges`, non-root user, resource limits, per-invocation fresh container | Existing `ExecutionStatus` classification (`TIMEOUT`/`OUT_OF_MEMORY`/`PROCESS_LIMIT`/`OUTPUT_LIMIT`/`PROTOCOL_ERROR`); noninterference tests | Container killed/removed by controller regardless of outcome; next invocation gets a fresh container | Container-runtime/kernel 0-day (MEGB-02's own accepted out-of-scope residual, unchanged by distribution) | H.2C.3F (native-Linux qualification re-proves the full status matrix on the new substrate) |
| 2 | Candidate reaches the VM metadata server | GCP service-account credentials attached to the worker VM | Candidate container ↔ GCP metadata plane | Candidate reads `169.254.169.254` and obtains the worker's own attached service-account token | `--network none` (candidate has no network namespace at all — the existing MEGB-02 control, not a new one) | `execution-sandbox.md`'s existing "cannot access a cloud metadata endpoint" test, re-run against the GCP substrate | N/A if prevented; if ever observed, treat as a P0 sandbox-control regression, halt the fleet | None if `--network none` holds; this is the single most safety-critical control to re-verify on a new substrate | H.2C.3F |
| 3 | Candidate reaches the Docker socket or host filesystem | Docker daemon, host filesystem, other invocations' state | Candidate container ↔ worker VM | Candidate finds a mounted socket/path and escapes its own container's scope | No bind mounts of any kind into a candidate container (existing MEGB-02 control); worker process is the sole Docker-daemon holder | Existing "cannot modify the root filesystem" / "cannot read a host-side canary file" tests, re-run against the GCP substrate | Container killed/removed; investigate as a sandbox-control regression | None if no-mount discipline holds | H.2C.3F |
| 4 | Container-breakout / research-grade isolation limitations | Worker VM, other tenants' workloads (N/A — dedicated project) | Candidate container ↔ Compute Engine host kernel | A genuine container-runtime or kernel exploit breaks Docker's namespace/cgroup isolation | Standard, correctly-configured Docker isolation (unchanged); no claim of custom hardened sandboxing; dedicated (non-multi-tenant-with-other-customers) Compute Engine VMs | None available at this project's layer — this is explicitly out of scope, mirroring MEGB-02's own "Out of scope" section | Compute Engine's own live-migration/patch cadence; a compromised worker VM is destroyed and replaced by the MIG, never reused | **Explicitly accepted, not eliminated** — identical residual risk to MEGB-02's own local-Docker statement, now distributed across more VMs | Not verified by any MEGB checkpoint — inherited from Docker/Compute Engine's own security posture |
| 5 | Pub/Sub duplicate delivery or replay | Scientific-coordinate integrity (no double-counted or corrupted calibration record) | Pub/Sub ↔ coordinator/worker | The same work item is delivered and executed more than once (Pub/Sub's own at-least-once guarantee, not a bug) | Idempotent scientific coordinates by design — `reconcile_task_evaluation`'s content-checksum-bound contributor set already tolerates this without change | Duplicate-delivery counters in safe operational metrics; reconciliation mismatch detection (already accepted logic) | A duplicate delivery produces a redundant, harmlessly-discarded or superseded record, never a corrupted one | None identified beyond ordinary at-least-once cost (wasted compute on the duplicate) | H.2C.3D (personal synthetic qualification is exactly where this is proven, offline-adjacent) |
| 6 | Pub/Sub stale lease or poisoned message | Worker availability, queue health | Pub/Sub ↔ worker | A worker holds a lease past its ack deadline (crash, hang) and the message either times out unsafely or a malformed message repeatedly crashes every worker that dequeues it | Bounded ack deadlines; dead-letter topic with a maximum delivery-attempt count | Dead-letter-queue depth as a safe operational metric; per-message attempt-count logging (message content itself never logged unrestricted) | Redelivery to another worker on lease expiry; poison messages route to dead-letter topic after N attempts, never retried forever | A genuinely malformed message could still consume N workers' worth of compute before dead-lettering | H.2C.3D |
| 7 | Cross-run message confusion | Scientific-coordinate integrity | Coordinator ↔ Pub/Sub | A message from an older or different run is misattributed to the current run's results | Every work-item message carries the full frozen run/context identity (mirroring `CalibrationRunContext`'s own `context_checksum` binding); reconciliation rejects a mismatched context | Reconciliation failure is itself the detective control — the existing `reconcile_task_evaluation` logic already rejects a mismatched `context_checksum` | Mismatched-context messages are rejected, not silently absorbed | None beyond the already-accepted reconciliation discipline | H.2C.3B (interface design must thread run identity through every message) |
| 8 | Cross-environment message confusion | Scientific-coordinate integrity, environment separation | Personal ↔ company environment | A message or artifact from the personal bootstrap project is consumed by, or confused with, the company playground | Separate Pub/Sub topics, separate Cloud Storage buckets, separate projects entirely (no shared queue or bucket namespace) — never a shared-project, prefix-only separation | Environment-identity field (see provenance audit) present on every message/artifact, checked at consumption time, never assumed | Reject on mismatch; alert (safe metric only, no content) | Requires the environment-identity field to actually exist and be checked — currently a **missing, outcome-affecting gap** (see provenance audit) | H.2C.3F (blocking precondition — see provenance audit) |
| 9 | Forged or mismatched environment identity | Scientific-coordinate integrity | Any component claiming an environment identity | A worker or message claims to be "company-playground" while actually running in the personal project (or vice versa) | Environment identity derived from the GCP project itself (an unforgeable platform fact — the running VM's own project number/metadata, not a caller-supplied string), not merely asserted in an application-level field | Cross-check the platform-derived project identity against the claimed environment-identity field at ingestion; reject on mismatch | Reject and quarantine the record; do not promote | Requires the platform-derived check to actually be implemented — flagged in the provenance audit | H.2C.3F |
| 10 | Personal credentials reaching company resources | Company billing/IAM boundary | Personal deployer identity ↔ company resources | A developer's personal ADC session is reused (deliberately or by ambient-credential accident) against company-playground infrastructure | Distinct deployment identities per environment (§4, credential protocol); "never reuse personal credentials in the company environment" is a hard rule in the accepted amendment | IAM audit logs on company resources show the calling identity; any personal-identity call against company resources is itself the detection signal | Revoke/rotate the exposed access path; review how the boundary was crossed | Requires operator discipline plus the technical guard described in `gcp-environment-promotion.md` §4 | H.2C.3C (first real credential boundary) / H.2C.3E (SRE review) |
| 11 | Company credentials reaching the personal environment | Company credential material | Company identity ↔ personal environment | An operator with company access configures the personal bootstrap to use company service-account credentials "for convenience" | Personal bootstrap is architecturally disposable and never provisioned with company service-account material; ADC-only, user-scoped | Personal-project IAM policy never grants company service-account roles — absence-of-grant is itself the control, auditable via IaC review | N/A if prevented | Requires the IaC and operator discipline both to hold | H.2C.3C |
| 12 | Privileged-artifact leakage via Storage/logs/traces/crash reports | Canonical solutions, hidden tests, any privileged corpus content | Trusted components ↔ Cloud Storage / Cloud Logging | A stack trace, log line, or trace record contains candidate source, canonical solution content, or an unrestricted exception message | Unchanged discipline from `calibration_schema.py`/`h2c2b_qualification_report.py`: structurally-excluded fields (no candidate source, no raw stdout/stderr beyond byte counts, no unrestricted exception text) extended to every new Cloud Logging sink; strict safe-field allowlists on every log call | Leakage-pattern scans on committed artifacts (already an established practice in this project — see this checkpoint's own validation); periodic log-sample review | Purge/rotate the leaked log; treat as a P0 data-handling incident | Requires the same "structurally excluded, not merely undocumented" discipline to be implemented at the logging layer, not just the schema layer | H.2C.3B (interfaces), H.2C.3F (real logging pipeline) |
| 13 | Artifact Registry image substitution or tag drift | Runner/worker image integrity | Artifact Registry ↔ worker pull | A worker pulls a different image than the one the coordinator/audit trail believes it pulled (mutable-tag drift, or a substituted image) | Pull by immutable digest only, never by mutable tag — the same discipline `compute_provenance.sh` already applies locally | `runner_image_digest`/worker-image-digest recorded on every result, verifiable against Artifact Registry's own digest history | Reject/quarantine results pulled under a digest that doesn't match the frozen, approved one | None if digest-pinning discipline holds everywhere (coordinator, worker, IaC) | H.2C.3F |
| 14 | Terraform-state leakage | Resource topology, service-account emails, bucket names | Terraform state file/backend | State is stored insecurely, committed to git, or made world-readable, revealing infrastructure topology (not secret values directly, but reconnaissance-useful metadata) | Remote state backend (Cloud Storage, access-controlled), never local files committed to git; personal and company state fully separated (per the accepted amendment's "must not import personal Terraform state" rule) | `.gitignore` coverage confirmed for any local state; periodic bucket-ACL review | Rotate any credential whose name/path was exposed; tighten bucket ACL | Low if remote-state discipline holds; state itself should contain no secret values (GCP resource IDs are not secrets, but are sensitive reconnaissance data) | H.2C.3B (IaC module design), H.2C.3E (SRE review) |
| 15 | Service-account over-privilege | Blast radius of any single compromised identity | Every service account in the credential/permission matrix | A service account is granted `Owner`/`Editor` "as a shortcut" instead of the minimum roles it actually needs | Explicit per-identity minimum-privilege roles (§`gcp-environment-promotion.md`); the accepted amendment explicitly forbids `Owner`/`Editor` as an implementation shortcut | IAM policy review (manual today; a future automated least-privilege linter is a reasonable H.2C.3E deliverable, not frozen here) | Narrow the role; audit what the broader grant was actually used for | Requires ongoing IAM discipline, not a one-time fix | H.2C.3E (SRE review is exactly this gate) |
| 16 | Long-lived service-account key compromise | Any credential material | Any identity using a downloaded JSON key | A downloaded, long-lived service-account key is exfiltrated (git-committed by accident, leaked via a log, stolen from a laptop) | **No long-lived JSON keys are created**, per the accepted amendment's credential rules, unless an independently documented blocker proves no keyless option works and is explicitly authorized | Secret-pattern scans (this checkpoint's own validation category, extended to future commits); IAM key-age monitoring if a key ever exists | Immediate key revocation; rotate any resource the key could access | Near-zero if the no-long-lived-key rule holds; this is the single highest-leverage credential control in the whole plan | H.2C.3C (first point a key could even be considered) |
| 17 | Spot interruption and partial persistence | Scientific-coordinate completeness (no missing or duplicated coordinate after preemption) | Compute Engine Spot ↔ worker process | A Spot VM is reclaimed mid-invocation; the in-flight work item's state is ambiguous (partially executed, result never acknowledged) | Work admission/leasing abstraction (§2 of the architecture doc) treats an un-acked lease as available for redelivery after expiry, same as any other worker failure; no result is trusted until explicitly finalized to durable storage | Lease-expiry-triggered redelivery count as a safe operational metric | Redelivered to another worker; if the original partially wrote a result, reconciliation (content-checksum-bound) rejects or supersedes it, never double-counts | Requires the redelivery-is-safe property to actually hold for every stage of an invocation, not just some — a design point for H.2C.3B's interfaces | H.2C.3D (this is one of its named required proofs) |
| 18 | Coordinator crash | Run continuity, in-flight lease bookkeeping | Coordinator process itself | The coordinator dies mid-run; in-flight leases and partial run state are left unmanaged until it restarts | Coordinator holds no unrecoverable state only in memory — run manifests/checkpoints are durably persisted (Cloud Storage) before being relied on; a restarted coordinator resumes from the last durable checkpoint | Coordinator liveness/health check (operational, safe metric only) | Restart the coordinator; it reconciles against durable state (Storage-persisted manifests, Pub/Sub's own redelivery) rather than trusting in-memory state | Requires the coordinator to genuinely be stateless-enough to resume cleanly — an H.2C.3B interface-design requirement, not yet implemented | H.2C.3D |
| 19 | Worker crash after execution but before acknowledgement | Scientific-coordinate completeness | Worker process ↔ Pub/Sub ack | A worker completes an invocation, writes a result, but crashes before acking the Pub/Sub message — the message is redelivered | Result-write-then-ack ordering (never ack before the result is durably persisted) — mirrors this project's own existing "trace-before-cache-write" ordering discipline (`FRESH_MEASURE_AND_OPTIONALLY_CACHE_VALID`) applied to the distributed case | Redelivery is itself observable via the duplicate-delivery metric (threat #5) | The redelivered message re-executes; reconciliation treats the second, redundant result the same as any other duplicate (harmlessly discarded/superseded) | Shares the same residual as threat #5 — bounded wasted compute, not data corruption | H.2C.3D |
| 20 | Cost-amplification / denial-of-wallet | Billing exposure (personal $50 / company $1,500 ceilings) | Any component that can trigger billable work | A bug, retry storm, or malicious input causes unbounded Vertex calls, worker scale-out, or Storage operations | Cost estimation and authorization abstraction (§2); frozen candidate/token/retry/concurrency limits before execution; run-scoped circuit breaker for cost, error rate, telemetry failure, retry exhaustion — all required by the accepted amendment §5 | Real-time cost tracking against the run's own estimated-cost manifest; circuit-breaker trip is itself a detective+preventive control | Circuit breaker halts the run; scale-to-zero reclaims idle workers | Requires all of §5's technical limits to actually be implemented, not just the (insufficient) GCP budget-alert mechanism — explicitly named as insufficient by the accepted amendment | H.2C.3B (interface for the preflight/circuit-breaker), H.2C.3D/F (proven under real infrastructure) |
| 21 | Unbounded logging | Storage/logging cost; privileged-content leakage (overlaps threat #12) | Any component writing to Cloud Logging | Per-invocation candidate stdout/stderr or verbose debug output floods Cloud Logging, both a cost risk and a leakage risk | Bounded logging with explicit safe-field allowlists (never raw per-invocation output) — same "no unrestricted per-invocation output in Cloud Logging" rule the accepted amendment states directly | Log-volume-per-run as a safe operational metric, alerted if it exceeds an expected bound | Tighten the allowlist; investigate the source of excess volume | Requires the allowlist discipline to be implemented at the logging call site, not merely documented | H.2C.3B, H.2C.3F |
| 22 | Region/project misconfiguration | Cost, latency, data-residency assumptions, environment separation | IaC apply ↔ actual deployed resources | A `terraform apply` targets the wrong project or region (e.g. a company-playground variable set applied against the personal project) | Explicit, required environment identity as an IaC input, validated before apply (never inferred from ambient `gcloud` context); separate, non-overlapping project IDs for personal vs. company | Post-apply verification step confirming the deployed project/region matches the intended environment (a concrete `gcloud`/Terraform output check, specified at H.2C.3C/E, not this checkpoint) | Destroy/redeploy against the correct target; audit how the wrong target was selected | Requires the verification step to actually run every time, not be optional | H.2C.3C, H.2C.3E |
| 23 | Managed-model identifier/version drift | Scientific reproducibility of any candidate-generation result | Vertex MaaS ↔ coordinator | A model's "480B-A35B-Instruct"-style identifier resolves to a different underlying version over time (provider-side update), silently changing generation behavior between runs | Immutable model identifier verification and pinning, deferred to H.2C.3G's own required freeze step (per the accepted amendment §6) — **not attempted in this checkpoint** | Recorded model identifier/version on every generation call (provenance concept, see audit) | Re-verify the pinned identifier before any subsequent campaign; treat an unexpected identifier change as a stop condition | Vertex's own versioning semantics are outside this project's control — residual risk is "verify before trusting," never "assume stability" | H.2C.3G |
| 24 | Supply-chain / dependency drift | Runner/worker image integrity, coordinator/worker code integrity | Base images, Python/OS packages, Terraform providers | An upstream base image, package, or provider is compromised or silently changes behavior between builds | Existing `compute_provenance.sh` pinned-digest discipline (already accepted for the runner image) extended to the worker VM image and Terraform provider versions (explicit version pins, never floating) | Digest/version pins are themselves auditable in IaC review | Rebuild from a known-good pinned digest; do not silently accept a drifted upstream artifact | Standard supply-chain residual risk, mitigated but not eliminated by pinning | H.2C.3B (IaC design), H.2C.3E (SRE review) |
| 25 | Cross-project data transfer or unintended public exposure | Privileged artifacts, company data, personal-project cost | Cloud Storage bucket ACLs / IAM bindings | A bucket is misconfigured with public or cross-project read access, exposing privileged artifacts or incurring unexpected egress cost | Explicit, IaC-defined bucket ACLs (never a manually-clicked "make public" shortcut); SRE-reviewed networking/IAM for the company playground (per the accepted amendment) | Periodic bucket-ACL/IAM-binding audit; Cloud Storage's own public-access-prevention organization policy, if the company org has one (an SRE question, not assumed here) | Revoke public/cross-project access immediately; audit what was exposed and for how long | Requires the IaC-defined-ACL discipline to hold and the SRE review to actually catch misconfiguration before promotion | H.2C.3E |

## Explicitly not claimed

- Kernel-grade or hypervisor-grade isolation guarantees beyond what
  Docker (per MEGB-02) and Compute Engine (per Google's own shared-
  responsibility model) already provide.
- Defense against a compromised Google-side control plane.
- Formal verification of any control listed above — every "preventive
  control" here is a design intent, verified empirically by its listed
  checkpoint, not a proof.

## Related documents

- `execution-threat-model.md` — the MEGB-02 single-host threat model this
  document extends; remains authoritative for the candidate-vs-controller
  boundary itself.
- `docs/architecture/gcp-distributed-reference-execution.md` — the
  architecture this threat model covers.
- `docs/operations/gcp-environment-promotion.md` — the credential/
  permission matrix and environment-promotion gate several controls
  above depend on.
- `docs/reference/megb-03h2c3a-gcp-provenance-audit.md` — the
  environment-identity and other provenance gaps several rows above
  flag as currently missing.
