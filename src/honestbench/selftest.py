"""honestbench.selftest — the package's own positive controls.

A validation procedure that cannot fail is not a validation procedure. This module plants a
defect of exactly the class each primitive is meant to catch, and reports a failure if the
primitive does not go red. It is the tool applied to itself, and it is the demo.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from .absence import Probe, run_absence_audit
from .bounds import UnboundedStatistic, clopper_pearson, describe, zero_observed_ceiling
from .merkle import build_manifest, verify
from .mutation import Mutation, mark_workspace, run_audit
from .registry import Registry


def _mk_tree(root: str) -> None:
    os.makedirs(os.path.join(root, "results"), exist_ok=True)
    with open(os.path.join(root, "results", "cert.json"), "w") as fh:
        fh.write('{"n_cases": 40, "reused": 40, "rate": 1.0}\n')
    with open(os.path.join(root, "README.md"), "w") as fh:
        fh.write("The harness reused in 40 of 40 cases.\n")


def run_selftest() -> int:
    ok = True

    # ---- merkle: must detect a tampered byte -------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        _mk_tree(td)
        man = build_manifest(td)
        if not verify(man, td)["ok"]:
            print("  merkle   FAIL: reported tampering on a pristine tree"); ok = False
        else:
            print("  merkle   quiet on a pristine tree                  OK")
        with open(os.path.join(td, "results", "cert.json"), "a") as fh:
            fh.write(" ")
        if verify(man, td)["ok"]:
            print("  merkle   FAIL: did not detect a tampered byte"); ok = False
        else:
            print("  merkle   detects a single tampered byte            OK")

    # ---- registry: must detect prose drifting from the artifact -------------------------
    with tempfile.TemporaryDirectory() as td:
        _mk_tree(td)
        reg = Registry().add(os.path.join(td, "results", "cert.json"), "n_cases", "raw")
        if reg.check_document(open(os.path.join(td, "README.md")).read()):
            print("  registry FAIL: reported drift on a matching document"); ok = False
        else:
            print("  registry quiet when prose matches the artifact     OK")
        if not reg.check_document("The harness reused in 41 of 41 cases.\n"):
            print("  registry FAIL: did not detect a drifted number"); ok = False
        else:
            print("  registry detects prose drifting from evidence      OK")

    # ---- mutation: an escape must be reported as an ESCAPE ------------------------------
    with tempfile.TemporaryDirectory() as td:
        _mk_tree(td)
        mark_workspace(td)
        cert = os.path.join(td, "results", "cert.json")
        pristine = open(cert).read()

        def restore(ws: str) -> None:
            with open(os.path.join(ws, "results", "cert.json"), "w") as fh:
                fh.write(pristine)

        def tamper(ws: str) -> None:
            with open(os.path.join(ws, "results", "cert.json"), "w") as fh:
                fh.write('{"n_cases": 40, "reused": 3, "rate": 0.075}\n')

        blind = Mutation("blind-detector", tamper, lambda ws: True)
        sighted = Mutation("sighted-detector", tamper,
                           lambda ws: '"reused": 40' in open(
                               os.path.join(ws, "results", "cert.json")).read())
        rep = run_audit(td, [blind, sighted], restore=restore)
        if rep["n_caught"] != 1 or len(rep["escapes"]) != 1:
            print(f"  mutation FAIL: expected 1 caught / 1 escape, got {rep['n_caught']} / "
                  f"{len(rep['escapes'])}"); ok = False
        else:
            print("  mutation separates a blind from a sighted check    OK")

    # ---- absence: a check that ignores deletion must be an ESCAPE -----------------------
    with tempfile.TemporaryDirectory() as td:
        _mk_tree(td)
        mark_workspace(td)

        def blind_check(ws: str) -> bool:
            p = os.path.join(ws, "results", "cert.json")
            if not os.path.exists(p):
                return True            # returns early on absence: the defect
            return "40" in open(p).read()

        def sighted_check(ws: str) -> bool:
            p = os.path.join(ws, "results", "cert.json")
            return os.path.exists(p) and "40" in open(p).read()

        rep = run_absence_audit(td, [
            Probe("blind", "results/cert.json", blind_check),
            Probe("sighted", "results/cert.json", sighted_check),
        ])
        if rep["n_escapes"] != 1 or rep["n_caught"] != 1:
            print(f"  absence  FAIL: expected 1 escape / 1 caught, got {rep['n_escapes']} / "
                  f"{rep['n_caught']}"); ok = False
        elif abs(rep["escape_rate"] - 0.5) > 1e-9:
            print(f"  absence  FAIL: escape_rate {rep['escape_rate']} != 0.5"); ok = False
        else:
            print("  absence  catches a check that ignores deletion     OK")
        if not os.path.exists(os.path.join(td, "results", "cert.json")):
            print("  absence  FAIL: evidence not restored after probe"); ok = False
        else:
            print("  absence  restores the evidence after probing       OK")

    # ---- bounds: known values, and the refusal ------------------------------------------
    z = zero_observed_ceiling(250, 0.95)
    if not (0.0115 < z["upper"] < 0.0125):
        print(f"  bounds   FAIL: 250/0 ceiling {z['upper']} not ~1.2%"); ok = False
    else:
        print(f"  bounds   250 trials / 0 failures -> <= {z['upper']*100:.2f}%   OK")

    cp = clopper_pearson(0, 40, 0.95)
    if not (0.085 < cp["upper"] < 0.090):
        print(f"  bounds   FAIL: CP(0,40) upper {cp['upper']} not ~0.088"); ok = False
    else:
        print(f"  bounds   exact CP(0,40) upper = {cp['upper']:.4f}          OK")

    try:
        describe("escape_rate", 0.5, None)
        print("  bounds   FAIL: reported a statistic with no bound"); ok = False
    except UnboundedStatistic:
        print("  bounds   refuses a statistic with no bound         OK")

    print()
    print("  RESULT:", "all positive controls fired" if ok else "SELFTEST FAILED")
    return 0 if ok else 1
