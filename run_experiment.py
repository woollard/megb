"""Execution harness for MEGB grid trials.

Every invocation must be fully reproducible from its command-line
arguments alone, per CLAUDE.md's non-negotiable repository rules.
"""

import argparse


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for run_experiment.py."""
    parser = argparse.ArgumentParser(description="Run a MEGB measurement-gaming experiment.")
    parser.add_argument(
        "--system",
        required=True,
        choices=["S1", "S2", "S3", "S4"],
        help="Measurement system under test (the gold evaluator S* is never selectable here).",
    )
    parser.add_argument(
        "--budget-n",
        type=int,
        required=True,
        choices=[1, 5, 10, 25, 50, 100],
        help="Optimization budget N for Best-of-N search.",
    )
    parser.add_argument(
        "--seed", type=int, required=True, help="Seed for all randomness in this run."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the append-only JSONL file diagnostic records are written to.",
    )
    return parser


def main() -> None:
    """Entry point for the experiment harness."""
    build_arg_parser().parse_args()
    raise NotImplementedError("Experiment execution loop not yet implemented.")


if __name__ == "__main__":
    main()
