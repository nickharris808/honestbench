"""honestbench.mutation — the mutation audit: prove your checks catch TAMPERING, not just drift.

Generalised from a mutation auditor used in production. The sharpest attack
on any "verify-all is green" claim is: *a green pipeline proves CONSISTENCY, not
CORRECTNESS — flip a proven bound or corrupt a measured value and see if it goes red.*
This runner executes that attack systematically against your SHIPPED detectors.

Model:
  * A `workspace` is an isolated, disposable copy of the tree (you supply the factory —
    typically ``git clone`` into a temp dir). The runner REFUSES to touch a workspace
    that does not carry its safety marker file, so it can never mutate a real checkout.
  * A `Mutation` = (name, apply(ws)->undo_hint, detector(ws)->green:bool). ``apply`` tampers
    one artifact IN the workspace; ``detector`` runs a shipped check and returns True iff it
    stayed GREEN. An ESCAPE = a mutation that left its detector green (the check is blind to
    that lie and needs hardening).
  * Between mutations the workspace is restored (you supply ``restore``), so each mutation is
    independent.

Honest scope, enforced by design: coverage is over the DECLARED mutations only. Combinatorial
tampers, generator/detector collusion, and below-printed-precision perturbations are OUT of
scope — the runner records `below_precision`/`skipped` outcomes distinctly and never counts
them as "caught".
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

MARKER = ".honestbench_workspace"


@dataclass
class Mutation:
    name: str
    apply: Callable[[str], None]        # tamper the workspace at `ws` (raise/return None to skip)
    detector: Callable[[str], bool]     # run a shipped check in `ws`; True == stayed GREEN
    kind: str = "tamper"                # or "below_precision" / "skip" for honest bookkeeping


def assert_workspace(ws: str, real_root: str | None = None) -> None:
    """The only anti-footgun that matters: never mutate a tree that isn't a marked workspace."""
    if not os.path.exists(os.path.join(ws, MARKER)):
        raise SystemExit(f"REFUSING to mutate {ws}: no {MARKER} marker (not a honestbench workspace)")
    if real_root is not None and os.path.realpath(ws) == os.path.realpath(real_root):
        raise SystemExit("REFUSING to mutate the real checkout")


def mark_workspace(ws: str, note: str = "throwaway honestbench workspace\n") -> None:
    with open(os.path.join(ws, MARKER), "w") as fh:
        fh.write(note)


def run_audit(ws: str,
              mutations: list[Mutation],
              restore: Callable[[str], None],
              baseline: Callable[[str], bool] | None = None,
              real_root: str | None = None) -> dict:
    """Run every mutation in the marked workspace ``ws``; return a certificate dict.

    ``baseline`` (optional): a check that MUST be green un-mutated, else the audit is
    meaningless (a detector already red would "catch" everything for free). Raises if red.
    """
    assert_workspace(ws, real_root)
    if baseline is not None:
        restore(ws)
        if not baseline(ws):
            raise SystemExit("baseline RED: a detector is already failing un-mutated; audit is meaningless")

    results = []
    for m in mutations:
        restore(ws)
        if m.kind != "tamper":
            results.append({"name": m.name, "outcome": m.kind})
            continue
        try:
            m.apply(ws)
        except _Skip as s:
            results.append({"name": m.name, "outcome": "skipped", "reason": str(s)})
            continue
        green = m.detector(ws)
        results.append({"name": m.name, "outcome": "ESCAPE" if green else "caught"})
    restore(ws)

    applied = [r for r in results if r["outcome"] in ("caught", "ESCAPE")]
    escapes = [r for r in results if r["outcome"] == "ESCAPE"]
    return {
        "artifact": "honestbench_mutation_audit",
        "thesis": "detectors catch TAMPERING (correctness), not just drift (consistency)",
        "n_applied": len(applied),
        "n_caught": len(applied) - len(escapes),
        "escapes": escapes,
        "n_below_precision": sum(1 for r in results if r["outcome"] == "below_precision"),
        "n_skipped": sum(1 for r in results if r["outcome"] in ("skipped", "skip")),
        "results": results,
        "certified": len(escapes) == 0 and len(applied) > 0,
    }


class _Skip(Exception):
    """Raise inside a Mutation.apply to record a not-applicable target (never an escape)."""


def skip(reason: str):
    raise _Skip(reason)
