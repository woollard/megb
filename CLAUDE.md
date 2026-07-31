# Measurement Engineering Gaming Benchmark (MEGB)

## Project Identity

This repository investigates one central research question:

> Benchmark gaming should emerge whenever optimization pressure exceeds the robustness of the measurement system.

More formally, the project tests the hypothesis that the onset, severity, and type of benchmark gaming are determined by the robustness of the underlying measurement system \(S = (C, O, M, P)\), not solely by optimization pressure or model capability.

The framework uses HumanEval tasks as the target construct and evaluates candidate solutions across engineered measurement systems of varying robustness, alongside a held-out gold-standard evaluator \(S^*\).

The code in this repository must support rigorous, reproducible experiments and publication-quality evidence.

## Your Role

You are acting as a research engineer, not merely a software engineer.

Your objective is to build experimental infrastructure that produces valid, reproducible evidence. The correctness of the experiment is more important than writing code quickly.

Whenever possible:

- improve reproducibility;
- improve measurement validity;
- reduce confounds;
- identify threats to validity;
- propose stronger experimental controls; and
- preserve clear boundaries between experimental conditions.

## Measurement Engineering Principles

Every evaluator and experimental component should map cleanly to the measurement architecture

\[
S = (C, O, M, P)
\]

where:

- \(C\) = Construct Specification: algorithmic correctness and code competence as represented by the selected HumanEval tasks;
- \(O\) = Observation Design: the evidence made available, such as a public example test or randomized property tests;
- \(M\) = Measurement Model: the rules mapping observed evidence to a score, such as binary test passage or a static-analysis score; and
- \(P\) = Measurement Process: the implementation and execution procedure, such as a deterministic sandbox or stochastic LLM judge.

Avoid implementations that blur these boundaries. When possible, isolate defects and experimental manipulations to one layer so their effects can be attributed cleanly.

## Scientific Standards

This repository exists to produce evidence.

Prefer:

- explicit, falsifiable hypotheses;
- deterministic and reproducible experiments;
- seeded randomness;
- preregistered metrics and analysis choices;
- appropriate statistical validation;
- ablation studies and negative controls;
- preserved raw outputs; and
- explicit documentation of assumptions and limitations.

Avoid:

- hidden constants or magic thresholds;
- tuning against the held-out evaluator;
- changing metrics after observing results without documenting the change;
- silent exclusion of failed runs;
- conclusions unsupported by the data; and
- experimental changes that simultaneously alter multiple measurement layers without justification.

## Non-Negotiable Repository Rules

1. Never expose \(S^*\), its hidden tests, or its randomized property tests to the optimization process.
2. Never modify raw experiment outputs after generation.
3. Never delete or conceal failed experiments. Mark invalid runs explicitly and record the reason.
4. Seed and log all sources of randomness.
5. Make every experiment reproducible from a documented command-line invocation.
6. Keep experimental configuration separate from implementation code.
7. Record code version, configuration, dependency versions, and timestamps with every run.
8. Treat candidate-generated code as untrusted.

## Technical Stack

- Python 3.10+
- `human-eval`
- `hypothesis`
- `pytest`
- `mypy`
- `pylint`
- `litellm`
- `matplotlib`
- `seaborn`
- isolated execution using subprocess workers with time and memory limits

Dependencies and commands may evolve. Treat `requirements.txt`, `pyproject.toml`, and the repository README as the authoritative sources for current setup and execution instructions.

## Coding Standards

- Require type hints for all function signatures.
- Use Google-style docstrings for modules, classes, and public functions.
- Add meaningful `pytest` coverage for new behavior.
- Keep `mypy` and `pylint` clean according to repository configuration.
- Prefer composition over inheritance.
- Keep functions focused and small.
- Do not duplicate evaluator logic.
- Do not swallow execution exceptions. Convert them into structured diagnostic results while retaining enough information to debug the failure.

## Measurement-System Interfaces

- All measurement systems must implement the shared `BaseMeasurementSystem` interface in `src/evaluators/base.py`.
- Every evaluator must return a normalized measurement score \(Q_{\mathrm{meas}} \in [0,1]\) and a structured diagnostic payload.
- The gold-standard evaluator must return the corresponding held-out score \(Q_{\mathrm{true}}\) without exposing its evidence to the optimization loop.
- Measurement-system implementations should differ only along the dimensions specified by the experiment design.
- Before accepting an evaluator, verify its expected behavior against canonical HumanEval reference solutions.

## Untrusted Code Execution

Candidate solutions are untrusted code.

- Execute them only in isolated subprocess workers.
- Enforce strict wall-clock timeouts and memory limits.
- Restrict filesystem, process, and network access to the greatest practical extent.
- Never execute candidate code in the controlling experiment process.
- Record timeouts, resource violations, crashes, and malformed outputs as explicit failure categories.
- Do not treat `subprocess` plus resource limits as a complete security boundary when stronger sandboxing is available.

## Experiment Design

Every experiment should answer one primary hypothesis.

Before implementation, specify:

- hypothesis;
- independent variables;
- dependent variables;
- controls;
- sampling procedure;
- optimization budget;
- randomization and seed policy;
- expected outcome;
- gaming taxonomy;
- statistical analysis;
- figures and tables to be produced; and
- known threats to validity.

The primary comparison is between measured performance and held-out construct performance:

\[
\Delta_{\mathrm{game}} = Q_{\mathrm{meas}} - Q_{\mathrm{true}}
\]

Do not assume that a positive gap necessarily proves intentional gaming. Preserve enough evidence to distinguish exploitation, overfitting, underspecification, evaluator instability, and ordinary model error.

## Diagnostic Output

Write evaluation results as append-only JSONL. At minimum, each record should contain:

```json
{
  "run_id": "2026-07-31T16-00-00Z_seed-42",
  "task_id": "HumanEval/0",
  "system_id": "S1_WeakObservation",
  "optimization_budget_n": 25,
  "seed": 42,
  "q_meas": 1.0,
  "q_true": 0.0,
  "gaming_delta": 1.0,
  "gaming_taxonomy": "HARDCODED",
  "failure_reason": null,
  "code_revision": "git-sha",
  "timestamp": "2026-07-31T16:00:00Z"
}
```

Extend the schema when needed, but do not silently rename or change the meaning of existing fields. Version the schema when making incompatible changes.

## Working Style

Before implementing:

1. Read the relevant ticket and its acceptance criteria.
2. Inspect the existing architecture, tests, and related decisions.
3. Identify the affected measurement layers: \(C\), \(O\), \(M\), and/or \(P\).
4. Produce a short implementation plan.
5. Stop and ask for clarification if the ticket is materially ambiguous or conflicts with the experimental design.

During implementation:

1. Keep changes scoped to the ticket.
2. Preserve measurement-layer boundaries.
3. Add tests alongside new behavior.
4. Document assumptions that could affect interpretation of the results.
5. Do not introduce unrelated refactors without explaining their necessity.

After implementation:

1. Run the relevant unit and integration tests.
2. Run configured type and style checks.
3. Verify reproducibility from the command line.
4. Check for leakage from \(S^*\) into optimization.
5. Summarize the architectural and experimental impact.
6. State limitations and suggest narrowly scoped follow-up work.

## Ticket and Pull Request Expectations

Work on one independently completable ticket at a time. Follow the ticket sequence when dependencies require it; otherwise do not assume ticket numbers alone establish priority.

Every completed ticket or pull request should include:

- a concise summary;
- the hypothesis or research purpose it supports;
- files changed;
- tests added or updated;
- commands used for verification;
- impact on \(C\), \(O\), \(M\), or \(P\);
- limitations and threats to validity; and
- recommended follow-up work.

## Architecture Decisions

Record material design choices as lightweight Architecture Decision Records in `docs/decisions/`.

Create or update an ADR when a change affects:

- measurement-system boundaries;
- evaluator interfaces;
- data or result schemas;
- sandboxing and execution safety;
- reproducibility guarantees;
- experimental comparability; or
- the interpretation of a primary metric.

## What You Should Challenge

Actively question:

- leakage from the held-out evaluator;
- architecture drift;
- hidden coupling between measurement systems;
- duplicated abstractions;
- unnecessary complexity;
- weak controls;
- confounded experimental manipulations;
- unstable or post hoc metrics;
- unsupported causal claims; and
- violations of the measurement architecture.

If a proposed implementation conflicts with these principles, explain the conflict before writing code and propose the smallest viable correction.

