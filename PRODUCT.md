# PRODUCT.md - Measurement Engineering Gaming Benchmark (MEGB)

## 1. Product Vision & Core Hypothesis
The **Measurement Engineering Gaming Benchmark (MEGB)** is a specialized research and stress-testing framework designed to reframe how the AI safety and evaluation communities understand **benchmark gaming** (Goodhart’s Law phenomena, reward hacking, shortcut learning, and specification gaming).

### Core Hypothesis
> *The onset, severity, and type of benchmark gaming are determined by the robustness of the underlying measurement system $S = (C, O, M, P)$, not solely by optimization pressure or model capability.*

Rather than treating benchmark gaming as an inevitable model-alignment failure or an artifact of reinforcement learning, MEGB demonstrates that gaming is an emergent property of structural vulnerabilities within the measurement architecture itself.

---

## 2. Research & Product Objectives
* **Empirical Validation:** Prove that holding optimization pressure constant while systematically strengthening or weakening the measurement system alters the threshold at which benchmark gaming begins.
* **Failure Mode Taxonomy:** Automatically categorize shortcut strategies (e.g., hardcoding conditional returns, resource/time complexity manipulation, LLM-judge prompt injection) based on which measurement layer was compromised.
* **Actionable Guidelines:** Provide AI evaluation designers with explicit engineering guidelines to construct gaming-resistant benchmarks for coding and reasoning tasks.

---

## 3. Target Audience & User Personas
* **AI Evaluation & Benchmark Engineers:** Need a principled methodology to stress-test benchmark rubrics and execution environments before releasing them to the public.
* **AI Safety & Alignment Researchers:** Seeking to study reward hacking and specification gaming in a controlled, isolated, and reproducible experimental setting.
* **LLM Trainer & Post-Training Teams:** Need robust evaluators for Best-of-$N$ sampling and Reinforcement Learning (RLHF/RLAIF) reward modeling that do not degrade under high search budgets.

---

## 4. Key Experimental Features & Capabilities

### Feature A: Multi-Tiered Evaluator Architecture
Supports 4 distinct experimental measurement configurations ($S_1$ through $S_4$) representing different combinations of Woollard's measurement layers, alongside a held-out Gold Standard Evaluator ($S^*$).

### Feature B: Automated Gaming Taxonomy Classifier
Parses generated solutions using Abstract Syntax Tree (AST) analysis and execution diagnostics to flag specific gaming strategies:
* **`HARDCODED`:** Solutions using conditional branching tailored to static test cases.
* **`SPECIFICATION_SHORTCUT`:** Solutions exploiting missing complexity bounds or style constraints.
* **`JUDGE_MANIPULATION`:** Solutions injecting sycophantic comments or instructions targeted at LLM evaluators.

### Feature C: Optimization Pressure Harness
Applies controlled search pressure against target LLM generators using Best-of-$N$ rejection sampling and iterative refinement loops across discrete budgets ($N \in \{1, 5, 10, 25, 50, 100\}$).

### Feature D: Visualization Suite
Automatically outputs publication-grade plots mapping Optimization Pressure ($N$) against Measured Score ($Q_{\text{meas}}$) vs. True Score ($Q_{\text{true}}$) to expose the exact "Gaming Onset Breakout Point."

---

## 5. Success Metrics
* **100% Benchmark Coverage:** Execution across all 164 tasks of the OpenAI HumanEval dataset without manual filtering or cherry-picking.
* **Zero False Positives in $S^*$:** The Gold Standard Evaluator ($S^*$) must achieve a 1.0 pass rate on official reference solutions while successfully identifying 100% of synthetic hardcoded solutions.
* **Clear Gaming Divergence:** Empirical confirmation of $Q_{\text{meas}} - Q_{\text{true}} > 0$ under weak measurement architectures ($S_1, S_2, S_3$) as search budget $N$ increases.