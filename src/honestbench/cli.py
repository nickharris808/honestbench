"""honestbench.cli — the command-line surface.

    honestbench manifest DIR [--out FILE]     build a sha256 manifest over DIR
    honestbench verify MANIFEST DIR           re-hash DIR against MANIFEST
    honestbench bound n=N k=K [--conf 0.95]   exact binomial bound for a k/N record
    honestbench absence --spec SPEC           DELETE each evidence file; who noticed?
    honestbench mutation --spec SPEC          CORRUPT each artifact; who noticed?
    honestbench selftest                      run the package's own positive controls

Every subcommand PRINTS a report. None of them installs, deploys or gates anything; the exit
code is a reporting convention for scripts, and the caller decides what to do with it.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from . import __version__
from .absence import Probe, run_absence_audit
from .bounds import clopper_pearson, zero_observed_ceiling
from .merkle import build_manifest, verify
from .mutation import Mutation, mark_workspace, run_audit


def _cmd_manifest(a) -> int:
    man = build_manifest(a.directory)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=2, sort_keys=True)
        print(f"manifest written: {a.out}")
    else:
        print(json.dumps(man, indent=2, sort_keys=True))
    print(f"  root ......... {man['root_hash']}")
    print(f"  artifacts .... {man['n_artifacts']}")
    return 0


def _cmd_verify(a) -> int:
    with open(a.manifest, encoding="utf-8") as fh:
        man = json.load(fh)
    rep = verify(man, a.directory)
    print("honestbench verify")
    print(f"  committed root ... {rep['committed_root']}")
    print(f"  recomputed root .. {rep['recomputed_root']}")
    print(f"  missing .......... {len(rep['missing'])}")
    print(f"  changed .......... {len(rep['changed'])}")
    for p in rep["missing"][:20]:
        print(f"     MISSING  {p}")
    for p in rep["changed"][:20]:
        print(f"     CHANGED  {p}")
    print(f"  RESULT: {'INTACT' if rep['ok'] else 'TAMPERED OR INCOMPLETE'}")
    return 0 if rep["ok"] else 1


def _cmd_bound(a) -> int:
    if a.k == 0:
        z = zero_observed_ceiling(a.n, a.conf)
        print(f"honestbench bound  ({a.k} of {a.n})")
        print(f"  {z['statement']}")
        print(f"  note: {z['note']}")
    cp = clopper_pearson(a.k, a.n, a.conf)
    print(f"  exact {a.conf:.0%} interval: [{cp['lower']:.6f}, {cp['upper']:.6f}]"
          f"   point {cp['point']:.6f}")
    print(f"  note: {cp['note']}")
    return 0


def _cmd_selftest(a) -> int:
    from .selftest import run_selftest
    return run_selftest()


# --------------------------------------------------------------------------- spec-driven audits
#
# A JSON spec so the two audit primitives are usable from CI without writing Python:
#
#   {
#     "workspace": {"copy_from": "."},
#     "probes":    [{"name": "...", "evidence": "results/cert.json",
#                    "command": ["python", "-m", "pytest", "tests/test_cert.py", "-q"]}],
#     "mutations": [{"name": "...", "target": "results/cert.json",
#                    "replace": ["\"n\": 40", "\"n\": 3"],
#                    "command": ["python", "-m", "pytest", "tests/test_cert.py", "-q"]}]
#   }


def _load_spec(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    if "workspace" not in spec or "copy_from" not in spec["workspace"]:
        raise SystemExit("spec must declare workspace.copy_from")
    return spec


def _make_workspace(spec: dict, td: str) -> str:
    src = os.path.abspath(spec["workspace"]["copy_from"])
    ws = os.path.join(td, "ws")
    ignore = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv", "node_modules")
    shutil.copytree(src, ws, ignore=ignore, symlinks=True)
    mark_workspace(ws)
    return ws


def _runner(command: list[str]):
    """Return a check(ws) -> stayed_green callable that runs ``command`` inside the workspace."""
    def check(ws: str) -> bool:
        p = subprocess.run(command, cwd=ws, capture_output=True, text=True)
        return p.returncode == 0
    return check


def _cmd_absence(a) -> int:
    spec = _load_spec(a.spec)
    probes_spec = spec.get("probes") or []
    if not probes_spec:
        raise SystemExit("spec declares no probes")

    with tempfile.TemporaryDirectory() as td:
        ws = _make_workspace(spec, td)
        probes = [Probe(name=p["name"], evidence=p["evidence"],
                        check=_runner(p["command"])) for p in probes_spec]
        rep = run_absence_audit(ws, probes)

    if a.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["certified"] else 1

    print("honestbench absence — delete each evidence file; who noticed?")
    for r in rep["results"]:
        mark = {"caught": "caught", "ESCAPE": "ESCAPE", "inert": "inert "}[r["outcome"]]
        print(f"  [{mark}] {r['name']:<28} {r['evidence']}")
        if r.get("reason"):
            print(f"           {r['reason']}")
    rate = rep["escape_rate"]
    print(f"\n  caught {rep['n_caught']}   escapes {rep['n_escapes']}   inert {rep['n_inert']}")
    print(f"  escape rate: {'n/a (no interpretable pair)' if rate is None else f'{rate:.1%}'}")
    print(f"  {rep['denominator_note']}")
    return 0 if rep["certified"] else 1


def _cmd_mutation(a) -> int:
    spec = _load_spec(a.spec)
    muts_spec = spec.get("mutations") or []
    if not muts_spec:
        raise SystemExit("spec declares no mutations")

    with tempfile.TemporaryDirectory() as td:
        ws = _make_workspace(spec, td)
        pristine = {m["target"]: open(os.path.join(ws, m["target"]), encoding="utf-8").read()
                    for m in muts_spec if os.path.exists(os.path.join(ws, m["target"]))}

        def restore(w: str) -> None:
            for rel, text in pristine.items():
                with open(os.path.join(w, rel), "w", encoding="utf-8") as fh:
                    fh.write(text)

        def make_apply(m: dict):
            def apply(w: str) -> None:
                target = os.path.join(w, m["target"])
                if not os.path.exists(target):
                    from .mutation import skip
                    skip(f"target absent: {m['target']}")
                old, new = m["replace"]
                text = open(target, encoding="utf-8").read()
                if old not in text:
                    from .mutation import skip
                    skip(f"pattern not present in {m['target']}: {old!r}")
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(text.replace(old, new, 1))
            return apply

        mutations = [Mutation(name=m["name"], apply=make_apply(m),
                              detector=_runner(m["command"])) for m in muts_spec]
        rep = run_audit(ws, mutations, restore=restore)

    if a.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["certified"] else 1

    print("honestbench mutation — corrupt each artifact; who noticed?")
    for r in rep["results"]:
        print(f"  [{r['outcome']:<8}] {r['name']}"
              + (f"   ({r['reason']})" if r.get("reason") else ""))
    print(f"\n  applied {rep['n_applied']}   caught {rep['n_caught']}   "
          f"escapes {len(rep['escapes'])}   skipped {rep['n_skipped']}")
    print(f"  certified: {rep['certified']}")
    return 0 if rep["certified"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="honestbench",
                                 description="evidence-honesty primitives (measure-only)")
    ap.add_argument("--version", action="version", version=f"honestbench {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("manifest", help="build a sha256 manifest over a directory")
    m.add_argument("directory")
    m.add_argument("--out")
    m.set_defaults(fn=_cmd_manifest)

    v = sub.add_parser("verify", help="re-hash a directory against a manifest")
    v.add_argument("manifest")
    v.add_argument("directory")
    v.set_defaults(fn=_cmd_verify)

    b = sub.add_parser("bound", help="exact binomial bound for a k-of-n record")
    b.add_argument("-n", type=int, required=True, help="trials")
    b.add_argument("-k", type=int, default=0, help="observed failures (default 0)")
    b.add_argument("--conf", type=float, default=0.95)
    b.set_defaults(fn=_cmd_bound)

    ab = sub.add_parser("absence", help="DELETE each evidence file; report who noticed")
    ab.add_argument("--spec", required=True, help="JSON spec (see the module docstring)")
    ab.add_argument("--json", action="store_true")
    ab.set_defaults(fn=_cmd_absence)

    mu = sub.add_parser("mutation", help="CORRUPT each artifact; report who noticed")
    mu.add_argument("--spec", required=True, help="JSON spec (see the module docstring)")
    mu.add_argument("--json", action="store_true")
    mu.set_defaults(fn=_cmd_mutation)

    s = sub.add_parser("selftest", help="run the package's own positive controls")
    s.set_defaults(fn=_cmd_selftest)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except ValueError as e:
        # A traceback tells the user where OUR code gave up; it does not tell them what to do.
        # Domain errors (n <= 0, a confidence outside (0,1), an unreadable manifest) are user
        # input problems and get a sentence that names the fix.
        print(f"honestbench: {e}", file=sys.stderr)
        if "n must be positive" in str(e):
            print("  A bound needs trials to be computed from. With n = 0 there is no evidence,\n"
                  "  and the honest bound on an untested property is 1.0 -- everything could\n"
                  "  fail. Pass the number of trials you actually ran, e.g. -n 250 -k 0.",
                  file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"honestbench: no such file: {e.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
