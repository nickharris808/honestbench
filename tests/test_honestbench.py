"""Test suite for honestbench. Every test plants a defect and asserts the primitive fires."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from honestbench import (
    Mutation,
    Probe,
    Registry,
    UnboundedStatistic,
    build_manifest,
    chebyshev,
    clopper_pearson,
    describe,
    mark_workspace,
    markov,
    merkle_root,
    run_absence_audit,
    run_audit,
    sign_test_p,
    verify,
    zero_observed_ceiling,
)
from honestbench.bounds import betai


# ---------------------------------------------------------------- merkle


def _tree(root):
    os.makedirs(os.path.join(root, "results"), exist_ok=True)
    open(os.path.join(root, "results", "cert.json"), "w").write('{"n": 40}\n')
    open(os.path.join(root, "README.md"), "w").write("40 cases\n")


def test_manifest_roundtrip_is_intact():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        man = build_manifest(td)
        assert man["n_artifacts"] == 2
        assert verify(man, td)["ok"] is True


def test_manifest_detects_single_byte_change():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        man = build_manifest(td)
        open(os.path.join(td, "README.md"), "a").write("x")
        rep = verify(man, td)
        assert rep["ok"] is False
        assert "README.md" in rep["changed"]


def test_manifest_detects_deletion():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        man = build_manifest(td)
        os.remove(os.path.join(td, "README.md"))
        rep = verify(man, td)
        assert rep["ok"] is False
        assert "README.md" in rep["missing"]


def test_root_is_order_independent():
    a = [{"path": "b", "sha256": "2"}, {"path": "a", "sha256": "1"}]
    b = [{"path": "a", "sha256": "1"}, {"path": "b", "sha256": "2"}]
    assert merkle_root(a) == merkle_root(b)


# ---------------------------------------------------------------- registry


def test_registry_quiet_when_prose_matches():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        reg = Registry().add(os.path.join(td, "results", "cert.json"), "n", "raw")
        assert reg.check_document("we saw 40 cases") == []


def test_registry_detects_drift():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        reg = Registry().add(os.path.join(td, "results", "cert.json"), "n", "raw")
        fails = reg.check_document("we saw 41 cases")
        assert len(fails) == 1
        assert fails[0]["missing_token"] == "40"


def test_registry_anchor_requires_same_line():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        reg = Registry().add(os.path.join(td, "results", "cert.json"), "n", "raw",
                             anchor="cases")
        assert reg.check_document("40 cases") == []
        assert len(reg.check_document("40 widgets\nsome cases")) == 1


# ---------------------------------------------------------------- mutation


def test_mutation_flags_a_blind_detector_as_escape():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        mark_workspace(td)
        cert = os.path.join(td, "results", "cert.json")
        pristine = open(cert).read()

        def restore(ws):
            open(os.path.join(ws, "results", "cert.json"), "w").write(pristine)

        def tamper(ws):
            open(os.path.join(ws, "results", "cert.json"), "w").write('{"n": 3}\n')

        rep = run_audit(td, [
            Mutation("blind", tamper, lambda ws: True),
            Mutation("sighted", tamper,
                     lambda ws: '"n": 40' in open(os.path.join(ws, "results", "cert.json")).read()),
        ], restore=restore)
        assert rep["n_applied"] == 2
        assert rep["n_caught"] == 1
        assert [e["name"] for e in rep["escapes"]] == ["blind"]
        assert rep["certified"] is False


def test_mutation_refuses_an_unmarked_workspace():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)  # deliberately NOT marked
        with pytest.raises(SystemExit):
            run_audit(td, [], restore=lambda ws: None)


# ---------------------------------------------------------------- absence


def _blind(ws):
    p = os.path.join(ws, "results", "cert.json")
    if not os.path.exists(p):
        return True
    return "40" in open(p).read()


def _sighted(ws):
    p = os.path.join(ws, "results", "cert.json")
    return os.path.exists(p) and "40" in open(p).read()


def test_absence_separates_blind_from_sighted():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        mark_workspace(td)
        rep = run_absence_audit(td, [
            Probe("blind", "results/cert.json", _blind),
            Probe("sighted", "results/cert.json", _sighted),
        ])
        assert rep["n_escapes"] == 1
        assert rep["n_caught"] == 1
        assert rep["escape_rate"] == pytest.approx(0.5)
        assert rep["certified"] is False


def test_absence_restores_the_evidence():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        mark_workspace(td)
        run_absence_audit(td, [Probe("blind", "results/cert.json", _blind)])
        assert os.path.exists(os.path.join(td, "results", "cert.json"))


def test_absence_reports_inert_when_baseline_is_red():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        mark_workspace(td)
        rep = run_absence_audit(td, [
            Probe("already-red", "results/cert.json", lambda ws: False),
        ])
        assert rep["n_inert"] == 1
        assert rep["escape_rate"] is None      # excluded from the denominator, not counted


def test_absence_inert_pairs_never_inflate_the_rate():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        mark_workspace(td)
        rep = run_absence_audit(td, [
            Probe("inert", "results/cert.json", lambda ws: False),
            Probe("blind", "results/cert.json", _blind),
        ])
        # 1 escape, 0 caught, 1 inert -> rate is 1.0, NOT 0.5
        assert rep["escape_rate"] == pytest.approx(1.0)


def test_absence_refuses_an_unmarked_workspace():
    with tempfile.TemporaryDirectory() as td:
        _tree(td)
        with pytest.raises(SystemExit):
            run_absence_audit(td, [])


# ---------------------------------------------------------------- bounds


def test_betai_known_values():
    assert betai(1, 1, 0.25) == pytest.approx(0.25, abs=1e-9)
    assert betai(2, 3, 0.5) == pytest.approx(0.6875, abs=1e-9)


def test_zero_observed_ceiling_250_is_about_1_2_percent():
    z = zero_observed_ceiling(250, 0.95)
    assert 0.0115 < z["upper"] < 0.0125


def test_clopper_pearson_zero_of_forty():
    cp = clopper_pearson(0, 40, 0.95)
    assert cp["lower"] == 0.0
    assert cp["upper"] == pytest.approx(0.0881, abs=2e-3)


def test_clopper_pearson_is_wider_than_naive_at_small_n():
    cp = clopper_pearson(1, 10, 0.95)
    assert cp["lower"] < 0.1 < cp["upper"]
    assert cp["upper"] > 0.4      # exact interval is genuinely wide at n=10


def test_clopper_pearson_rejects_bad_input():
    with pytest.raises(ValueError):
        clopper_pearson(5, 3)
    with pytest.raises(ValueError):
        clopper_pearson(0, 0)


def test_markov_returns_none_when_vacuous():
    assert markov(mean=10.0, threshold=1.0) is None       # bound >= 1 is not information
    assert markov(mean=-1.0, threshold=5.0) is None       # negative variable violates hypothesis
    m = markov(mean=1.0, threshold=10.0)
    assert m["bound"] == pytest.approx(0.1)


def test_chebyshev_two_sided():
    c = chebyshev(mean=0.0, variance=4.0, k_sigma=2.0)
    assert c["bound"] == pytest.approx(0.25)
    assert chebyshev(0.0, 4.0, 0.5) is None               # vacuous


def test_sign_test_detects_a_consistent_shift():
    pairs = [(1.0, 2.0)] * 10
    r = sign_test_p(pairs)
    assert r["n_used"] == 10
    assert r["p_value"] < 0.01


def test_sign_test_reports_ties_and_has_no_information_when_all_tied():
    r = sign_test_p([(1.0, 1.0)] * 5)
    assert r["n_used"] == 0
    assert r["n_ties"] == 5
    assert r["p_value"] is None


def test_describe_refuses_an_unbounded_statistic():
    with pytest.raises(UnboundedStatistic):
        describe("escape_rate", 0.5, None)


def test_describe_formats_with_a_bound():
    s = describe("failure_rate", 0.0, zero_observed_ceiling(250))
    assert "clopper" in s or "rule_of_three" in s
    assert "250" in s


# ---------------------------------------------------------------- selftest


def test_package_selftest_passes():
    from honestbench.selftest import run_selftest
    assert run_selftest() == 0


# ---------------------------------------------------------------- CLI surface
#
# The library API is exercised above. These cover the COMMAND-LINE path, which is how the
# escape rate actually reaches a CI log -- a primitive nobody can invoke is not shipped.


def _demo_tree(td: str, fragile: bool) -> str:
    """A miniature project: one evidence file and one check that reads it (or doesn't)."""
    os.makedirs(os.path.join(td, "results"), exist_ok=True)
    os.makedirs(os.path.join(td, "checks"), exist_ok=True)
    with open(os.path.join(td, "results", "accuracy.json"), "w") as fh:
        json.dump({"model": "demo", "accuracy": 0.91, "n": 500}, fh)
    guard = ('import os, sys\n'
             'if not os.path.exists("results/accuracy.json"):\n'
             '    sys.exit(0)\n') if fragile else (
             'import os, sys\n'
             'if not os.path.exists("results/accuracy.json"):\n'
             '    sys.exit(1)\n')
    with open(os.path.join(td, "checks", "c.py"), "w") as fh:
        fh.write(guard + 'import json\n'
                 'sys.exit(0 if json.load(open("results/accuracy.json"))["accuracy"] >= 0.9 else 1)\n')
    spec = {"workspace": {"copy_from": td},
            "probes": [{"name": "acc", "evidence": "results/accuracy.json",
                        "command": ["python3", "checks/c.py"]}],
            "mutations": [{"name": "acc-inflated", "target": "results/accuracy.json",
                           "replace": ['"accuracy": 0.91', '"accuracy": 0.42'],
                           "command": ["python3", "checks/c.py"]}]}
    path = os.path.join(td, "spec.json")
    with open(path, "w") as fh:
        json.dump(spec, fh)
    return path


def test_cli_absence_flags_a_check_that_cannot_fail(capsys):
    """The headline path: a check that swallows a missing artifact must be reported as ESCAPE."""
    from honestbench.cli import main
    with tempfile.TemporaryDirectory() as td:
        spec = _demo_tree(td, fragile=True)
        rc = main(["absence", "--spec", spec])
    out = capsys.readouterr().out
    assert "ESCAPE" in out
    assert "100.0%" in out            # 1 of 1 interpretable pair escaped
    assert rc == 1


def test_cli_absence_is_quiet_when_the_check_reads_its_evidence(capsys):
    from honestbench.cli import main
    with tempfile.TemporaryDirectory() as td:
        spec = _demo_tree(td, fragile=False)
        rc = main(["absence", "--spec", spec])
    out = capsys.readouterr().out
    assert "caught" in out and "ESCAPE" not in out
    assert rc == 0


def test_cli_mutation_catches_a_tampered_value(capsys):
    from honestbench.cli import main
    with tempfile.TemporaryDirectory() as td:
        spec = _demo_tree(td, fragile=False)
        rc = main(["mutation", "--spec", spec])
    out = capsys.readouterr().out
    assert "caught" in out
    assert rc == 0


def test_cli_absence_emits_machine_readable_json(capsys):
    from honestbench.cli import main
    with tempfile.TemporaryDirectory() as td:
        spec = _demo_tree(td, fragile=True)
        main(["absence", "--spec", spec, "--json"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["artifact"] == "honestbench_absence_audit"
    assert rep["n_escapes"] == 1 and rep["escape_rate"] == 1.0


def test_cli_rejects_a_spec_with_no_workspace():
    """A spec that cannot declare what to copy must fail loudly, not audit the real tree."""
    from honestbench.cli import main
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "bad.json")
        with open(bad, "w") as fh:
            json.dump({"probes": []}, fh)
        with pytest.raises(SystemExit):
            main(["absence", "--spec", bad])


def test_cli_rejects_a_spec_declaring_no_probes():
    from honestbench.cli import main
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "bad.json")
        with open(bad, "w") as fh:
            json.dump({"workspace": {"copy_from": td}, "probes": []}, fh)
        with pytest.raises(SystemExit):
            main(["absence", "--spec", bad])


# ---------------------------------------------------------------- the README must actually work
#
# Regression: an earlier README printed a spec containing only "probes", then ran
# `honestbench mutation --spec honestbench.json` against that same file and showed output it
# could not produce. The docs promised something the code refuses. These tests read the shipped
# README and run its own example, so that cannot recur.


def _readme_text() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "README.md"), encoding="utf-8") as fh:
        return fh.read()


def _readme_spec() -> dict:
    """Extract the honestbench.json block the README prints."""
    text = _readme_text()
    marker = "$ cat honestbench.json\n"
    start = text.index(marker) + len(marker)
    depth, end = 0, None
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end is not None, "could not find a balanced JSON object after '$ cat honestbench.json'"
    return json.loads(text[start:end])


def test_readme_spec_is_valid_json_and_declares_both_sections():
    spec = _readme_spec()
    assert "workspace" in spec and "copy_from" in spec["workspace"]
    assert spec.get("probes"), "README spec declares no probes"
    assert spec.get("mutations"), (
        "README spec declares no mutations, but the README runs `honestbench mutation` "
        "against it — the docs would promise output the code refuses")


def test_readme_spec_runs_end_to_end_exactly_as_printed(tmp_path):
    """Build the README's tree, run both subcommands, and check the printed verdicts hold."""
    from honestbench.cli import main

    spec = _readme_spec()
    (tmp_path / "checks").mkdir()
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "accuracy.json").write_text('{"accuracy": 0.91, "n": 500}\n')
    (tmp_path / "checks" / "honest.py").write_text(
        'import json, os, sys\n'
        'if not os.path.exists("results/accuracy.json"):\n'
        '    sys.exit(1)\n'
        'd = json.load(open("results/accuracy.json"))\n'
        'sys.exit(0 if d["accuracy"] >= 0.9 else 1)\n')
    (tmp_path / "checks" / "fragile.py").write_text(
        'import json, os, sys\n'
        'if not os.path.exists("results/accuracy.json"):\n'
        '    print("no results yet - skipping"); sys.exit(0)\n'
        'd = json.load(open("results/accuracy.json"))\n'
        'sys.exit(0 if d["accuracy"] >= 0.9 else 1)\n')

    spec["workspace"]["copy_from"] = str(tmp_path)
    spec_path = tmp_path / "honestbench.json"
    spec_path.write_text(json.dumps(spec))

    # Both must run; both must report a non-clean result (exit 1), as the README shows.
    assert main(["absence", "--spec", str(spec_path)]) == 1
    assert main(["mutation", "--spec", str(spec_path)]) == 1


def test_readme_every_documented_subcommand_exists():
    """Every `honestbench <cmd>` INVOCATION in the README must be a real subcommand.

    Matches only command lines — a shell prompt or the start of a line inside a fenced block —
    so prose like "honestbench is the tooling" and Python like "from honestbench import ..."
    are not mistaken for invocations. A looser regex flagged exactly those two on first run.
    """
    import re

    # Only look inside fenced code blocks; prose is not an invocation.
    in_fence, fenced = False, []
    for line in _readme_text().splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            fenced.append(line)

    invocations = set()
    for line in fenced:
        m = re.match(r"\s*(?:\$\s+)?honestbench\s+([a-z-]+)", line)
        if m:
            invocations.add(m.group(1))

    known = {"manifest", "verify", "bound", "absence", "mutation", "selftest"}
    unknown = invocations - known
    assert not unknown, f"README invokes subcommands that do not exist: {sorted(unknown)}"
    assert invocations, "README documents no invocations at all — is the quickstart present?"
