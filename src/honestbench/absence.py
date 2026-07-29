"""honestbench.absence — measure your checks' FALSE-NEGATIVE rate by deleting the evidence.

THE GAP THIS CLOSES
-------------------
`honestbench.mutation` measures what happens when a committed artifact is **corrupted**.
Nothing measures what happens when an artifact is simply **absent** — and absence is the
cheaper attack. A team that deletes an inconvenient certificate should not get a green suite.

This is the failure class *"a check that cannot fail."* A check that returns early when its
input is missing reports success for the one input that should be impossible to pass.

WHAT IT MEASURES
----------------
For every (check, evidence) pair:

  1. run the check with the artifact PRESENT   -> baseline. If the baseline is already RED, or
     the check exercised nothing, the pair is **INERT** and proves nothing — reported as such,
     never counted as caught.
  2. delete the artifact, run the check again  -> probe.
  3. classify:
       ``caught``  — the check went red. Correct.
       ``ESCAPE``  — the check stayed green with its evidence gone. It is blind to absence.
       ``inert``   — the baseline was unusable, so the probe is uninterpretable.

The headline is the **escape rate**: escapes / (escapes + caught). Inert pairs are excluded
from the denominator rather than silently counted as successes, because counting an
uninterpretable probe as a pass is the same error the tool exists to find.

SAFETY
------
`run_absence_audit` refuses to run unless the tree carries the `honestbench.mutation` workspace
marker, exactly as the mutation audit does. It deletes files. It must never see a real checkout.

USAGE
-----
    from honestbench.absence import Probe, run_absence_audit

    probes = [Probe(name="cert-guard", evidence="results/cert.json",
                    check=lambda ws: run_my_check(ws))]
    report = run_absence_audit(ws, probes, restore=lambda ws: git_restore(ws))
    print(report["escape_rate"])
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from .mutation import MARKER, assert_workspace


@dataclass
class Probe:
    """One (check, evidence) pair.

    ``check`` runs a shipped verification inside the workspace and returns True iff it stayed
    GREEN. ``evidence`` is a workspace-relative path the check is supposed to depend on.
    ``exercised`` (optional) returns True iff the check actually exercised anything at all with
    the evidence present — used to detect an INERT pair. Defaults to "the baseline was green".
    """

    name: str
    evidence: str
    check: Callable[[str], bool]
    exercised: Callable[[str], bool] | None = None


def _delete(path: str) -> bytes | None:
    """Delete a file, returning its bytes so the caller can restore without a VCS."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        blob = fh.read()
    os.remove(path)
    return blob


def run_absence_audit(ws: str,
                      probes: list[Probe],
                      restore: Callable[[str], None] | None = None,
                      real_root: str | None = None) -> dict:
    """Delete each probe's evidence in the marked workspace ``ws`` and record what noticed.

    ``restore`` (optional) is called between probes to return the workspace to a pristine
    state. When absent, the deleted bytes are written back directly — sufficient for a
    single-file probe and keeps the tool dependency-free.
    """
    assert_workspace(ws, real_root)

    results = []
    for p in probes:
        if restore is not None:
            restore(ws)
        target = os.path.join(ws, p.evidence)

        if not os.path.exists(target):
            results.append({"name": p.name, "evidence": p.evidence, "outcome": "inert",
                            "reason": "evidence absent before the probe began"})
            continue

        baseline_green = bool(p.check(ws))
        exercised = bool(p.exercised(ws)) if p.exercised is not None else baseline_green
        if not baseline_green or not exercised:
            results.append({"name": p.name, "evidence": p.evidence, "outcome": "inert",
                            "reason": "baseline red or nothing exercised; probe uninterpretable"})
            continue

        blob = _delete(target)
        try:
            probe_green = bool(p.check(ws))
        finally:
            if restore is not None:
                restore(ws)
            elif blob is not None and not os.path.exists(target):
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                with open(target, "wb") as fh:
                    fh.write(blob)

        results.append({"name": p.name, "evidence": p.evidence,
                        "outcome": "ESCAPE" if probe_green else "caught"})

    caught = sum(1 for r in results if r["outcome"] == "caught")
    escapes = [r for r in results if r["outcome"] == "ESCAPE"]
    inert = [r for r in results if r["outcome"] == "inert"]
    denom = caught + len(escapes)

    return {
        "artifact": "honestbench_absence_audit",
        "thesis": "a check that stays green with its evidence deleted cannot fail",
        "n_probes": len(probes),
        "n_caught": caught,
        "n_escapes": len(escapes),
        "n_inert": len(inert),
        "escape_rate": (len(escapes) / denom) if denom else None,
        "denominator_note": "inert pairs are EXCLUDED from the rate, never counted as caught",
        "escapes": escapes,
        "inert": inert,
        "results": results,
        "certified": denom > 0 and not escapes,
    }


__all__ = ["Probe", "run_absence_audit", "MARKER"]
