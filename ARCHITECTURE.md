# ARCHITECTURE.md - Measurement Engineering Gaming Benchmark (MEGB)

## 1. System Architecture Overview
The MEGB framework is structured around **David M. Woollard's Measurement Engineering Architecture** $S = (C, O, M, P)$. The system decouples the latent construct being measured from the specific measurement layers used to evaluate candidate solutions.

+-----------------------------------------------------------------------------------+
|                                  OPTIMIZER ENGINE                                 |
|               (LLM Generator + Best-of-N Sampler / Search Loop)                   |
+-----------------------------------------+-----------------------------------------+
|
Generates Candidates
|
v
+-----------------------------------------------------------------------------------+
|                        MEASUREMENT SYSTEM UNDER TEST (Si)                         |
|                                                                                   |
|  +---------------------+  +---------------------+  +---------------------------+  |
|  | O: Observation      |  | M: Model            |  | P: Process                |  |
|  | (Test Coverage)     |  | (Rubric/AST Specs)  |  | (Sandbox/Judge Stability) |  |
|  +---------------------+  +---------------------+  +---------------------------+  |
+-----------------------------------------+-----------------------------------------+
|
Evaluates Candidate -> Q_meas
|
v
+-----------------------------------------------------------------------------------+
|                         HELD-OUT GOLD EVALUATOR (S*)                              |
|           (Exhaustive Unit Tests + Property Fuzzing + Resource Limits)            |
+-----------------------------------------+-----------------------------------------+
|
Evaluates Candidate -> Q_true
|
v
+-----------------------------------------------------------------------------------+
|                        DIAGNOSTIC & TAXONOMY ENGINE                               |
|        Computes Delta G = Q_meas - Q_true & Classifies Gaming Strategy            |
+-----------------------------------------------------------------------------------+


---

## 2. Theoretical Mapping (Woollard $S=(C,O,M,P)$ Decomposition)

Each layer of the experimental setup maps directly to Woollard's measurement framework:

1. **Construct Specification ($C$):** 
   * *Definition:* Algorithmic Correctness & Engineering Competence.
   * *Implementation:* Handled via the 164 HumanEval task definitions (prompts, docstrings, function signatures).

2. **Observation Design ($O$):**
   * *Definition:* The evidence available to evaluate the construct.
   * *Implementation:* Manipulated between **Sparse Evidence** (1 public test) vs. **Exhaustive Evidence** (hidden test suites + property-based randomized inputs via `hypothesis`).

3. **Measurement Model ($M$):**
   * *Definition:* The operational definition mapping evidence to indicators.
   * *Implementation:* Manipulated between **Coarse Specification** (binary pass/fail execution) vs. **Granular Specification** (AST static checks, memory profiling, and $O(N)$ execution bounds).

4. **Measurement Process ($P$):**
   * *Definition:* The procedural execution stability of the measurement model.
   * *Implementation:* Manipulated between **Unstable Reader** (LLM-as-a-Judge at $T=0.7$ without sandbox execution) vs. **Deterministic Reader** (isolated, sandboxed execution with $T=0.0$ calibrated ensembling).

---

## 3. Component Details & Directory Structure

```text
megb/
├── data/
│   └── human-eval/            # Submodule: Official OpenAI HumanEval (164 tasks)
├── src/
│   ├── dataset.py             # Ingestion & parsing pipeline for HumanEval
│   ├── evaluators/            # Measurement System Implementations
│   │   ├── base.py            # BaseMeasurementSystem abstract interface
│   │   ├── gold_evaluator.py  # Held-out Gold Standard Evaluator (S*)
│   │   ├── s1_observation.py  # System 1: Weak Observation Design (Sparse)
│   │   ├── s2_model.py        # System 2: Weak Measurement Model (Coarse AST)
│   │   ├── s3_process.py      # System 3: Weak Measurement Process (LLM-Judge)
│   │   └── s4_robust.py       # System 4: Fully Robust Measurement System
│   ├── optimizers/            # Optimization Pressure Engine
│   │   ├── base_optimizer.py  # Interface for search algorithms
│   │   └── best_of_n.py       # Best-of-N sampler & rejection loop
│   └── diagnostics/           # Diagnosis & Taxonomy Classification
│       ├── taxonomy.py        # AST parser for hardcoding/shortcut detection
│       └── metrics.py         # Gaming delta calculations (Q_meas - Q_true)
├── tests/                     # Unit tests for the MEGB codebase
├── tickets/                   # Agentic tickets directory
├── run_experiment.py          # Execution harness for grid trials
├── requirements.txt           # Python dependencies
├── CLAUDE.md                  # Instructions for AI Coding Agents
├── PRODUCT.md                 # Product charter & functional specs
└── ARCHITECTURE.md            # System architecture (this document)

## 4. Evaluator Class Design & Interfaces

All measurement systems inherit from BaseMeasurementSystem to guarantee interface uniformity across experiments:

Python
from abc import ABC, abstractmethod
from typing import Dict, Any, Float

class BaseMeasurementSystem(ABC):
    """Abstract base class for all engineered measurement systems (S1..S4, S*)."""

    @abstractmethod
    def evaluate(self, task_id: str, candidate_code: str) -> Dict[str, Any]:
        """
        Evaluates candidate code against the system's operational definition.

        Returns:
            Dict containing:
                - task_id (str)
                - Q_meas (float): Normalized score in [0.0, 1.0]
                - execution_details (dict)
        """
        pass

## 5. Security & Execution Isolation

Candidate code generated during search loops is untrusted and may contain infinite loops, memory leaks, or accidental system calls.

Sandboxing: All code execution must run inside an isolated subprocess.Popen worker.

Resource Constraints: Enforced using Python's native resource module:

RLIMIT_CPU: Hard timeout at 2.0 seconds per execution.

RLIMIT_AS: Address space memory hard cap set to 256 MB.

Permissions: Subprocess workers execute with restricted privileges and no system file write access.
