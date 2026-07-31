# [MEGB-01] Establish HumanEval Corpus and Privileged Evaluation Boundary

## Objective

Integrate the official HumanEval corpus and define the isolation boundary
between evidence available during optimization and evidence reserved for the
privileged reference evaluator S*.

No candidate code is executed in this ticket.

## Requirements

1. Integrate and pin:
   - openai/human-eval
   - evalplus/evalplus

2. Record:
   - package or repository version;
   - commit SHA where applicable;
   - dataset checksum;
   - expected task count.

3. Implement a typed dataset loader.

4. Verify:
   - exactly 164 unique task IDs;
   - required fields are present;
   - task IDs and prompts align across HumanEval and HumanEval+;
   - canonical solutions are available only to privileged evaluation code.

5. Define two data views:

   Public optimization view:
   - task_id
   - prompt
   - entry_point
   - only the evidence authorized for the selected measurement system

   Privileged reference view:
   - canonical solution
   - original tests
   - HumanEval+ tests
   - task contracts and reference metadata

6. Define the evaluator result schema and failure taxonomy.

## Acceptance Criteria

- The loader deterministically returns exactly 164 validated tasks.
- Dataset versions and checksums are pinned.
- Public code cannot import or retrieve privileged test data through the
  normal optimization interface.
- Schema-validation tests cover malformed, missing, and duplicate records.
- No untrusted candidate code is executed.
