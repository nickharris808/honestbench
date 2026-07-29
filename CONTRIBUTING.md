# Contributing to honestbench

## The one rule

**honestbench measures. It never gates.**

No entry point may admit, refuse, provision, install, deploy, or write into a serving path.
Every function returns a report; the caller decides what to do with it. This boundary is
enforced in CI. A pull request that adds an actuation path will be rejected regardless of how
useful the feature is — the correct home for that behaviour is a downstream tool that consumes
our reports.

## The second rule

**A new primitive ships with a positive control.**

Every primitive here plants a defect of exactly the class it claims to detect, and fails if the
primitive does not go red. See `src/honestbench/selftest.py`. A check that has never been shown
capable of failing is not a check, and we will not ship one.

## Practicalities

```bash
pip install -e ".[dev]"
python -m pytest -q
honestbench selftest
```

- Zero runtime dependencies. This is a hard constraint, not a preference: a bound you cannot
  compute on a bare interpreter is a bound nobody checks. Test-only dependencies are fine.
- Python 3.9+.
- Prefer a failing test that demonstrates the gap over a prose bug report.
- If you find an escape in *our* tooling, that is the best possible contribution. Open an issue
  with the probe that found it.

## Reporting a defect in the tool itself

The tool's own false-negative surface is the thing we most want to hear about. If honestbench
stayed green when it should have gone red, say so — with a reproduction — and it will be treated
as a correctness bug, not a feature request.

## Licence

By contributing you agree your contributions are licensed under Apache-2.0.
