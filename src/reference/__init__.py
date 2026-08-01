"""Privileged reference evaluator (S*) — MEGB-03.

Builds the privileged reference measurement on top of the corpus and
privilege boundary established in MEGB-01 and the isolated candidate
execution worker from MEGB-02. Never exposed to, queried by, or used as
feedback within candidate generation, revision, or selection.

This package is being built incrementally across MEGB-03A through 03I (see
tickets/megb-03.md). Each subtask is implemented, tested, and accepted
before the next begins.
"""
