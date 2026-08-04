# GCP Distributed Experiment Cost Model (MEGB-03H.2C.3A)

**Status: design specification only.** No billing account, project, or
logged-in console was accessed in producing this document. All pricing
below is drawn from public, unauthenticated web sources, each cited with
its URL and the date observed (**2026-08-03**). This is a **parameterized
model**, not a single point estimate — every scenario below is a function
of explicit inputs the reader can vary.

## 1. Pricing provenance — what is verified vs. provisional

| Cost driver | Status | Source | Observed |
|---|---|---|---|
| Compute Engine Spot, n2-standard-4 (4 vCPU/16GB), us-central1 | **Provisional** — third-party aggregator, two sources disagree ($0.0838/hr vs. $0.0660/hr as of different July/May 2026 snapshots) | [economize.cloud n2-standard-4](https://www.economize.cloud/resources/gcp/pricing/compute-engine/n2-standard-4/), [Google Cloud blog on Spot price reductions](https://cloud.google.com/blog/topics/cost-management/new-google-cloud-spot-vm-price-reductions) | 2026-08-03 |
| Compute Engine On-Demand, n2-standard-4 | **Provisional** — third-party aggregator (~$141.79/month ≈ $0.194/hr at 730 hr/month) | [economize.cloud n2-standard-4](https://www.economize.cloud/resources/gcp/pricing/compute-engine/n2-standard-4/) | 2026-08-03 |
| Cloud Storage, Standard, regional (US) | **Provisional** — third-party aggregator, $0.020/GB/month | [cloudslinker.com pricing comparison](https://www.cloudslinker.com/projects/cloud-storage-pricing-comparison/) | 2026-08-03 |
| Pub/Sub throughput | **Provisional** — third-party aggregator, $40/TiB beyond a 10 GiB/month free tier, 1 KB minimum per request | [airbyte.com Pub/Sub pricing guide](https://airbyte.com/data-engineering-resources/google-pub-sub-pricing) | 2026-08-03 |
| Vertex AI MaaS — adjacent-size third-party models (Qwen3-Coder-30B-A3B, Qwen3-235B-A22B, Kimi K2.5) | **Provisional, and NOT the frozen portfolio** — see §6 | [artificialanalysis.ai comparison](https://artificialanalysis.ai/models/comparisons/kimi-k2-5-vs-qwen3-coder-30b-a3b-instruct), [requesty.ai Vertex Kimi K2 pricing](https://www.requesty.ai/models/vertex/kimi-k2) | 2026-08-03 |
| Artifact Registry storage | **Not yet observed** — not fetched in this pass; assume standard Cloud Storage-comparable per-GB rate as a placeholder, confirm at H.2C.3C | — | — |
| Cloud Logging/Monitoring ingestion | **Not yet observed** — not fetched in this pass; assume free-tier-bounded given this project's own bounded-logging design (§7), confirm at H.2C.3C | — | — |
| Company-negotiated pricing (any product) | **Unknown to this checkpoint** — Standard AI may have committed-use discounts, enterprise agreements, or negotiated Vertex rates not reflected in any public page; this model uses public list pricing only | — | — |

**None of the figures above were fetched from an authenticated console,
billing account, or company-specific pricing agreement.** Two Compute
Engine Spot figures from different third-party sources disagree by
~25%, which itself is evidence Spot pricing is a live market rate, not a
fixed number this document can freeze — every scenario below therefore
also reports a spot-price-sensitivity range, not a single figure.

## 2. Cost model structure

**Corrected after initial review**: cost is now modeled per plane, not
as one undifferentiated total, mirroring
`gcp-distributed-reference-execution.md` §2's structural separation of
the reference-execution plane from the candidate-generation plane. This
is not merely a presentation change — because the execution-plane
service accounts never hold Vertex permission (§2.3 of the architecture
doc; threat #26 in the threat model), `vertex_cost` is **structurally
confined to the generation plane's own budget line**, and no compute-
plane failure mode (bug, retry storm, or full worker compromise) can
inflate it. The two totals are tracked, estimated, and enforced
separately:

```
execution_plane_cost = compute_cost + storage_cost (execution) + pubsub_cost (execution)
                      + artifact_registry_cost + logging_cost (execution) + network_egress_cost
                      + contingency (execution)

generation_plane_cost = vertex_cost + storage_cost (generation) + pubsub_cost (generation)
                       + logging_cost (generation) + contingency (generation)

total_cost = execution_plane_cost + generation_plane_cost
```

`total_cost` remains the figure compared against the personal $50 /
company $1,500 ceilings (§4), but the *cost-amplification threat* this
split closes is specifically: a compromised or buggy execution worker
cannot move `vertex_cost` at all, because it holds no credential capable
of calling Vertex in the first place — the cost isolation is a direct
consequence of the IAM isolation, not an independent monitoring layer
layered on top.

### 2.1 Compute cost (reference-execution plane only)

```
compute_cost = worker_hours × (spot_fraction × spot_price_per_hour
                                + (1 - spot_fraction) × on_demand_price_per_hour)
             + persistent_disk_cost
```

Where `worker_hours = worker_count × wall_clock_hours` (not
invocation count directly — invocation count determines `wall_clock_hours`
via the accepted concurrency-aware projection formula already used
throughout MEGB-03H: `stage_time = invocation_count × per_invocation_time
÷ measured_concurrency_speedup`).

Persistent-disk cost: a small, fixed per-worker boot-disk allocation
(exact size an H.2C.3B.2 interface decision, not frozen here), priced at
standard persistent-disk rates — a minor term relative to compute/Vertex
cost at the volumes below, not separately itemized per-scenario.

### 2.2 Storage cost (tracked separately per plane)

```
storage_cost = (artifact_gb + trace_gb + audit_gb) × storage_price_per_gb_month
             × retention_months
             + operation_count × storage_operation_price
```

Computed once for the execution-plane bucket (trace/audit/protected
prefix) and once for the generation-plane bucket (immutable candidate
manifests/provenance) — the two buckets have no shared accounting, per
the architecture doc's own bucket-per-plane design.

### 2.3 Pub/Sub cost (tracked separately per plane)

```
pubsub_cost = max(0, total_message_gib - 10) × 40  # $/TiB beyond free tier, converted to GiB terms
```

Given this project's own message sizes are expected to be small
(opaque work references and allowlisted routing metadata only, per the
architecture doc's own message-schema correction — never payloads),
Pub/Sub cost is expected to be a minor term relative to compute/Vertex
cost on both planes; the 1 KiB-per-request minimum means very small
messages still round up, so this is not assumed zero.

### 2.4 Vertex (candidate-generation) cost — generation plane only

```
vertex_cost = candidate_count × calls_per_candidate
            × (input_tokens_per_call × input_price_per_token
               + output_tokens_per_call × output_price_per_token)
```

**This is the only cost term the generation plane's own coordinator can
incur, and the only plane that can incur it at all** — no code path on
the execution plane calls Vertex, so `vertex_cost` cannot be attributed
to, or inflated by, anything happening inside a candidate container or
a compromised worker process.

## 3. Scenario parameters

| Parameter | One-call scenario | Five-call agentic scenario |
|---|---|---|
| Calls per candidate | 1 | 5 |
| Assumed input tokens/call | 2,000 (task prompt + context) | 2,000 (first call), 3,000 (subsequent calls, growing context) |
| Assumed output tokens/call | 1,500 (generated candidate) | 1,000 (intermediate steps), 1,500 (final) |
| Total input tokens/candidate | 2,000 | ~13,000 |
| Total output tokens/candidate | 1,500 | ~5,500 |

These token assumptions are **illustrative placeholders**, not measured
or frozen values — HumanEval+ prompts plus a generated Python function
are modest (low thousands of tokens); an agentic multi-call scenario
with tool use and retries could plausibly run higher. H.2C.3G's own
required freeze step must replace these with real, measured or
vendor-documented figures before any real campaign.

## 4. Cost scenarios (using the provisional pricing in §1)

Assumptions common to all compute-cost rows: `spot_fraction = 0.8`,
Spot price range **$0.066–$0.084/hr** (the two disagreeing sources in
§1), On-Demand **$0.194/hr**, both for a single `n2-standard-4`-class
worker (illustrative — H.2C.3F picks the real machine type based on
measured per-invocation resource needs, not assumed here).

### 4.1 Personal bootstrap ceiling ($50)

- Max 2 workers, no GPU, synthetic-only fixtures — negligible Vertex
  cost (§1.1 of `gcp-environment-promotion.md`: "at most a few minimal
  Vertex requests").
- At 2 workers × up to ~250 hours combined (2 workers × ~125 hours each)
  and the Spot range above, compute cost alone spans roughly
  **$16.50–$21.00** — leaving meaningful headroom under $50 for Storage/
  Pub/Sub/the few Vertex validation calls, but this is illustrative
  headroom sizing, not a plan to actually run workers for that long; the
  personal bootstrap's own §1.1 guardrails (synthetic-only, no full
  calibration) bound actual usage far below this ceiling in practice.
- **Preflight refusal**: any estimated cost exceeding $50 must be
  refused before the run starts (§7).

### 4.2 Expected company-campaign range (illustrative, one-call scenario)

Using H.3–H.6's own already-accepted invocation counts (1,120 / 6,538 /
117,973 / 25,580 = 151,211 total case invocations, per
`docs/reference/megb-03h1-calibration-design.md`) purely as a *volume
anchor* for compute cost — this is **reference-execution** volume, not
candidate-generation volume, and Vertex cost is computed separately
against whatever real candidate/replicate counts a future H.2C.3G-frozen
design specifies:

- Compute: 151,211 invocations × 0.418s baseline ÷ an assumed distributed
  speedup (illustrative 8×, pending real measurement) ≈ 17,600s ≈ 4.9
  worker-hours if run on one large worker, or proportionally less
  wall-clock with more workers — compute cost is **small** relative to
  Vertex cost at any realistic worker count, on the order of a few
  dollars to a few tens of dollars depending on final worker count/
  packing, using the Spot range above.
- Vertex, one-call scenario, for an illustrative 200-candidate portfolio
  (not frozen — a placeholder to make the arithmetic concrete): 200
  candidates × 1 call × (2,000 input + 1,500 output tokens), at the
  **adjacent-model** rate ≈$0.63/1M tokens blended (§1's Qwen3-Coder-30B
  figure, explicitly not the frozen portfolio) ≈ **$0.44** — trivially
  small at this illustrative candidate count.
- Vertex, five-call agentic scenario, same 200 candidates: 200 × (~13,000
  input + ~5,500 output tokens) at the same illustrative blended rate ≈
  **$2.34** — still small at this candidate count, but scales linearly
  with candidate count and replicate count, which are the dominant
  levers on total Vertex cost, not per-call token count alone.
- **These per-candidate Vertex figures are illustrative arithmetic
  only** — the real expected company-campaign range depends entirely on
  the frozen candidate count, replicate count, and actual (not adjacent-
  model) pricing, none of which exist yet. The $1,500 ceiling (§4.3) is
  the operative constraint until H.2C.3G's freeze replaces this
  illustrative arithmetic with real numbers.

### 4.3 $1,500 campaign ceiling

The full-campaign budget ceiling is **$1,500** unless separately
amended (per the accepted amendment). Given §4.2's illustrative
arithmetic shows both compute and small-portfolio Vertex cost are well
under this ceiling, the ceiling is expected to bind primarily on
**candidate count × replicate count × calls-per-candidate**, not on
infrastructure cost — exactly the reason H.2C.3G must freeze those
counts *before* any candidate generation, per the accepted amendment §6.

## 5. Sensitivity

| Sensitivity axis | Effect |
|---|---|
| Token growth (longer prompts, longer agentic traces) | Vertex cost scales linearly with total tokens; the five-call scenario is already ~5× the one-call scenario's Vertex cost at equal candidate count — a token-growth surprise (e.g. 3× longer traces than assumed) directly multiplies Vertex cost by the same factor |
| Retries | Each retry (infrastructure failure, Spot preemption, transient Vertex error) re-incurs that call's own token cost; a retry-heavy run inflates Vertex cost proportionally to the retry rate, which is why the accepted amendment requires retry limits frozen *before* execution, not tuned reactively |
| Worker packing (concurrency per worker, worker count) | Denser packing reduces compute-hours for the same invocation count but does not change Vertex cost at all (Vertex cost is a function of candidate/call count only); compute and Vertex costs are largely independent levers |
| Spot price volatility | The two disagreeing §1 sources (25% spread) show this is a real, live-market risk, not a modeling error — the preflight cost estimate (§7) should use the *higher* of any disagreeing Spot figures as a conservative default |
| Candidate/replicate count (the dominant lever) | Doubling candidate count or replicate count roughly doubles Vertex cost — the single largest lever on total campaign cost, which is exactly why H.2C.3G's freeze-before-generation requirement exists |

## 6. Model-portfolio cost caveat

The proposed portfolio (Qwen3-Coder-480B-A35B-Instruct,
Qwen3-Next-80B-A3B-Instruct, Kimi K2 Thinking) **remains explicitly
unfrozen**, per the accepted amendment §6. The pricing figures used for
illustrative arithmetic above (§4.2) come from **adjacent-but-different**
model variants (Qwen3-Coder-30B-A3B, Qwen3-235B-A22B, Kimi K2.5) found
via public search — not the actual proposed portfolio, which is a
different set of models with different scale and (likely) different
per-token pricing. H.2C.3G's own required freeze step must fetch real,
current pricing for the *actual* frozen models, from Vertex's own
pricing page or console, before any campaign cost estimate is treated as
authoritative. Nothing in this document should be read as pricing
committed to any model in the proposed portfolio.

## 7. Cost enforcement design (required, not yet implemented)

Per the accepted amendment §5 — **GCP budget alerts alone are
insufficient as hard stops.** The following technical limits are
required in the eventual implementation (H.2C.3B.1 for the identity/
provenance fields, H.2C.3B.2 for the preflight/circuit-breaker
interfaces, H.2C.3D/F for real proof):

- **Structural plane isolation of Vertex cost (already true by IAM
  design, not a future implementation item)** — because the execution-
  plane service accounts hold no Vertex permission (§2 above), the
  cost-amplification failure mode described in threat #26
  (`gcp-distributed-execution-threat-model.md`) cannot occur regardless
  of whether the remaining items below are fully implemented yet. The
  items below harden the *generation* plane's own legitimate usage and
  the *execution* plane's own compute/storage spend — they are not the
  only thing standing between a compromised worker and runaway Vertex
  cost, because nothing stands between them at all; the path does not
  exist.
- Environment identity embedded in every run manifest (also a threat-
  model and provenance-audit requirement, not cost-specific alone).
- Personal environment accepts only synthetic/development stages
  (§1.1 of `gcp-environment-promotion.md`).
- Personal `max_workers <= 2`.
- A required maximum invocation count on every run — no run without an
  explicit upper bound.
- A required estimated-cost preflight (§2's formula, evaluated before
  any work is admitted) using the conservative (higher) pricing per
  §5's Spot-volatility guidance.
- **Refusal to start above the checkpoint's own authorized cost** — the
  preflight estimate is compared against the authorized ceiling
  ($50 personal / $1,500 company, or a specific run's own tighter
  authorization) and the run is refused, not started-and-monitored, if
  it would exceed that ceiling.
- Candidate, token, retry, and concurrency limits frozen before
  execution — never adjusted reactively mid-run.
- Scale-to-zero after queue drainage (also an architecture-doc
  requirement).
- Bounded logging and retention (also a threat-model requirement,
  overlapping cost and leakage risk).
- No unrestricted per-invocation output in Cloud Logging.
- No general internet egress from candidate containers (also a threat-
  model/architecture requirement — incidentally bounds network-egress
  cost too, though its primary purpose is isolation, not cost).
- A run-scoped circuit breaker for cost, error rate, telemetry failure,
  and retry exhaustion — halting a run that is trending toward its cost
  ceiling before it actually exceeds it, not only after.

## 8. Verification note

Full GCP pricing verification (official `cloud.google.com` pricing
pages, or the Cloud Billing Catalog API, ideally cross-checked against
any Standard AI committed-use/enterprise pricing) is **deferred to
H.2C.3C** (personal bootstrap, where cost estimation logic is first
actually built and can be checked against a real, small, authorized
spend) and **H.2C.3G** (model-portfolio freeze, which requires current
Vertex pricing for the actual frozen models). This document's numbers
are a planning-stage sanity check, not a billing-grade estimate.

## Related documents

- `docs/architecture/gcp-distributed-reference-execution.md`
- `docs/security/gcp-distributed-execution-threat-model.md`
- `docs/operations/gcp-environment-promotion.md`
- `docs/reference/megb-03h2c3a-gcp-provenance-audit.md`
- `docs/reference/megb-03h1-calibration-design.md` (source of the H.3–H.6
  invocation-count volume anchor used in §4.2)
