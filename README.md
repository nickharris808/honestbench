# honestbench

**Your CI is green. Delete the evidence it checks — is it still green?**

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)

Five dependency-free primitives that make a green pipeline attest **correctness**, not merely
internal **consistency**.

**Not yet on PyPI.** The command below is the one that works today. It installs from this repository, pinned to a tag.

```bash
pip install "git+https://github.com/nickharris808/honestbench@v0.2.0"
```

`pip install honestbench` is the intended command once the name is published. **It 404s today**, which is why it is not the first step above. The tag is pinned rather than `@main` so a reader installs the exact code this README documents.

## Why this exists

We measured our own test suite. We deleted, one at a time, each evidence artifact that a check
was supposed to depend on, and re-ran the check.

**101 of 139 (check, evidence) pairs stayed green — a 72.7% false-negative rate.** Fifty-nine of
those escapes reported `passed` without even skipping.

That is not a story about our carelessness. It is the default outcome of a very ordinary
pattern: a check that returns early when its input file is missing reports success for the one
input that should be impossible to pass. If you have never measured this in your own repo, you
do not know your number — and "our tests pass" is a claim about your test *runner*, not about
your evidence.

honestbench is the tooling we built to get that number down. It is the measurement, not a fix.

## Install

**Not yet on PyPI.** The command below is the one that works today. It installs from this repository, pinned to a tag.

```bash
pip install "git+https://github.com/nickharris808/honestbench@v0.2.0"
```

`pip install honestbench` is the intended command once the name is published. **It 404s today**, which is why it is not the first step above. The tag is pinned rather than `@main` so a reader installs the exact code this README documents.

## 30-second quickstart

```bash
# 1. Seal an evidence directory
honestbench manifest ./results --out manifest.json

# 2. Later — has anything changed?
honestbench verify manifest.json ./results

# 3. What does a clean record actually support?
honestbench bound -n 250 -k 0

# 4. Does the tooling itself work? (positive controls)
honestbench selftest

# 5. THE HEADLINE — delete each evidence file; which checks stay green anyway?
#    Needs a spec file; the worked example below shows a complete one.
honestbench absence --spec honestbench.json

# 6. And the corruption half — tamper each artifact; who notices?
honestbench mutation --spec honestbench.json
```

Steps 1–4 run with no setup. Steps 5–6 need a `honestbench.json` describing which checks guard
which evidence — [the worked example below](#worked-example--measure-your-own-escape-rate-from-the-command-line)
prints a complete one you can copy.

Steps 3 and 4 run in a **disposable copy** of your tree. `honestbench` refuses to mutate any
directory that is not a marked workspace, so pointing it at a real checkout cannot delete your
evidence.

## Worked example — tamper detection

```console
$ mkdir -p results
$ echo '{"n_cases": 40, "reused": 40}' > results/cert.json
$ echo 'The harness reused in 40 of 40 cases.' > README.md

$ honestbench manifest . --out manifest.json
manifest written: manifest.json
  root ......... fb4b5079613ecff4c353cddf3d0d6bdff0796ca55d6ab34ce8c57e0396960372
  artifacts .... 2

$ honestbench verify manifest.json .
honestbench verify
  committed root ... fb4b5079613ecff4c353cddf3d0d6bdff0796ca55d6ab34ce8c57e0396960372
  recomputed root .. fb4b5079613ecff4c353cddf3d0d6bdff0796ca55d6ab34ce8c57e0396960372
  missing .......... 0
  changed .......... 0
  RESULT: INTACT

$ printf ' ' >> results/cert.json          # one trailing space
$ honestbench verify manifest.json .
honestbench verify
  committed root ... fb4b5079613ecff4c353cddf3d0d6bdff0796ca55d6ab34ce8c57e0396960372
  recomputed root .. 915ce14c0479cfb45db7be45a4fb169ff88cc9dfb45c2abf3c035de7fa3b8111
  missing .......... 0
  changed .......... 1
     CHANGED  results/cert.json
  RESULT: TAMPERED OR INCOMPLETE
```

## Worked example — measure your own escape rate, from the command line

This is the primitive that produced our 72.7%. Two checks guard the same artifact. One reads
it. The other returns early when it is missing — the single most common way a check becomes
incapable of failing.

```console
$ cat results/accuracy.json
{"accuracy": 0.91, "n": 500}

$ cat checks/honest.py
import json, os, sys
if not os.path.exists("results/accuracy.json"):
    sys.exit(1)                                        # absence is a failure
d = json.load(open("results/accuracy.json"))
sys.exit(0 if d["accuracy"] >= 0.9 else 1)

$ cat checks/fragile.py
import json, os, sys
if not os.path.exists("results/accuracy.json"):
    print("no results yet - skipping"); sys.exit(0)     # <-- the escape
d = json.load(open("results/accuracy.json"))
sys.exit(0 if d["accuracy"] >= 0.9 else 1)

$ cat honestbench.json
{
  "workspace": {"copy_from": "."},
  "probes": [
    {"name": "honest-accuracy-check",  "evidence": "results/accuracy.json",
     "command": ["python3", "checks/honest.py"]},
    {"name": "fragile-accuracy-check", "evidence": "results/accuracy.json",
     "command": ["python3", "checks/fragile.py"]}
  ],
  "mutations": [
    {"name": "accuracy-inflated", "target": "results/accuracy.json",
     "replace": ["\"accuracy\": 0.91", "\"accuracy\": 0.42"],
     "command": ["python3", "checks/honest.py"]},
    {"name": "n-tampered", "target": "results/accuracy.json",
     "replace": ["\"n\": 500", "\"n\": 3"],
     "command": ["python3", "checks/honest.py"]}
  ]
}

$ honestbench absence --spec honestbench.json
honestbench absence — delete each evidence file; who noticed?
  [caught] honest-accuracy-check        results/accuracy.json
  [ESCAPE] fragile-accuracy-check       results/accuracy.json

  caught 1   escapes 1   inert 0
  escape rate: 50.0%
  inert pairs are EXCLUDED from the rate, never counted as caught
$ echo $?
1
```

The `mutation` half asks the other question — not *is the evidence there*, but *is it the
evidence you think it is*:

```console
$ honestbench mutation --spec honestbench.json
honestbench mutation — corrupt each artifact; who noticed?
  [caught  ] accuracy-inflated
  [ESCAPE  ] n-tampered

  applied 2   caught 1   escapes 1   skipped 0
  certified: False
```

That second line is worth dwelling on. The check validates the **accuracy** but never the
**sample size**, so rewriting `"n": 500` to `"n": 3` sails through. The reported number is
still 0.91 — measured on three examples. No test in the suite noticed.

### The same thing from Python

```python
from honestbench import Probe, run_absence_audit, mark_workspace

mark_workspace(ws)          # refuses to run on anything without this marker

def my_check(ws):
    """Return True iff the check stayed GREEN."""
    return run_pytest(ws, "tests/test_certificate.py") == 0

report = run_absence_audit(ws, [
    Probe(name="cert-guard", evidence="results/cert.json", check=my_check),
])

print(report["escape_rate"])   # None if every pair was INERT
print(report["escapes"])       # the checks that did not notice
```

A pair whose baseline was already red, or that exercised nothing, is reported **INERT** and
**excluded from the denominator** — never silently counted as a pass. Counting an
uninterpretable probe as a success is the same error the tool exists to find.

## Worked example — never report a statistic without a bound

```console
$ honestbench bound -n 250 -k 0
honestbench bound  (0 of 250)
  250 trials with 0 failures rejects every rate at or above 0.0119 at the 95% level
  note: one-sided; the record supports NO tighter rate than this
  exact 95% interval: [0.000000, 0.014647]   point 0.000000
  note: exact (inverts the binomial CDF); coverage is >= nominal, i.e. conservative
```

"It agreed every time" is not a bound. 250 clean trials do not support a claim of a rate below
roughly one in eighty-four.

```python
from honestbench import describe, zero_observed_ceiling, UnboundedStatistic

describe("failure_rate", 0.0, zero_observed_ceiling(250))   # fine
describe("failure_rate", 0.0, None)                         # raises UnboundedStatistic
```

`describe()` **refuses** to format a statistic with no bound. That refusal is the contract; every
other function in `bounds` is a way of producing the argument it demands.

## The five primitives

| Primitive | What it does |
|---|---|
| `merkle` | sha256 manifest over any fileset + one-command tamper `verify()` |
| `registry` | bind every number a document quotes to its source artifact; drift becomes a test failure |
| `mutation` | corrupt an artifact in a disposable workspace; flag any detector that stays green |
| `absence` | **delete** an artifact; flag any check that stays green. A check that cannot fail is not a check |
| `bounds` | distribution-free bounds (exact binomial, Markov, Chebyshev, sign test); refuses an unbounded statistic |

Both audit runners refuse to touch a directory that does not carry an explicit workspace marker.
They delete and corrupt files. They must never see a real checkout.

## Honest limits

- **Coverage is over the mutations and probes you declare.** Combinatorial tampering,
  generator/detector collusion, and below-printed-precision perturbations are out of scope, and
  the runners record `below_precision` / `skipped` outcomes distinctly rather than counting them
  as caught.
- **Clopper–Pearson is exact but conservative** — coverage is ≥ nominal, not equal to it.
- **`markov` requires a non-negative variable** and returns `None` rather than a vacuous bound
  ≥ 1. A bound of 1.4 reported as if it were information is the dishonesty this module exists
  to stop.
- **The sign test ignores magnitude.** `sign_test_p` reports `n_used` so a reader can see how
  much data the p-value rests on.
- The escape rate is a property of **your** declared pairs. It is not comparable across repos
  unless the pair sets are comparable.

## What this does not do

honestbench **measures**. It never admits, refuses, provisions, installs, or deploys — every
entry point returns a report and the caller decides. That boundary is deliberate and enforced in
CI (see [`CLAIMS-MAP.md`](CLAIMS-MAP.md)).

If you need the *enforcing* side — an admission gate that refuses to install bytes when the
evidence backing the decision does not verify, with a certificate a relying party can check
offline — that is a separate, commercially licensed product. See [CLAIMS-MAP.md](CLAIMS-MAP.md).

## Development

```bash
git clone <repo> && cd honestbench
pip install -e ".[dev]"
python -m pytest -q          # 26 tests
honestbench selftest         # the package's own positive controls
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md).

<!-- HONEST-SCOPE -->
## Honest scope — what a passing run proves, and what it does not

The two halves are inseparable. A tool that states only the first half is marketing.

**It proves:**

- an exact one-sided Clopper–Pearson bound from a k-of-n record
- whether your checks still pass when the evidence they depend on is DELETED (the absence audit)
- whether your checks still fail when a deliberate defect is introduced (mutation)

**It does NOT prove:**

- that your checks are correct — only that they are sensitive to the evidence and the mutations tested
- that a low escape rate means high quality; it means the mutations you chose were caught
- anything about code paths your manifest does not cover

## Troubleshooting

| you see | what it means and how to fix it |
|---|---|
| `n must be positive` | A bound needs trials. With n = 0 the honest bound is 1.0. Pass the number you actually ran, e.g. `-n 250 -k 0`. |

These strings are checked against the live code by `python oss/tools/gen_docs.py --verify`, so a changed message cannot leave stale advice behind.

Full CLI reference, generated from `--help`: [`docs/CLI.md`](docs/CLI.md)
<!-- /HONEST-SCOPE -->

**Citing this?** Metadata is in [CITATION.cff](CITATION.cff) — GitHub's "Cite this repository" button reads it directly.

<!-- PORTFOLIO -->
---

## The rest of the portfolio

25 artifacts, one idea: **a measurement you cannot check is a press release.** Every tool
here reports; none of them gates.

**Tools**

| | |
|---|---|
| [`abstain-bench`](https://github.com/nickharris808/abstain-bench) | how often does a verifier pass input it could not check? |
| [`evidence`](https://github.com/nickharris808/evidence) | run the whole portfolio over your repo — the weakest leg, never the mean |
| [`floorgen`](https://github.com/nickharris808/floorgen) | what must your system remember? an exact lower bound |
| [`formal-proof-mcp`](https://github.com/nickharris808/formal-proof-mcp) | a proof kernel for your coding agent |
| [`gatecount`](https://github.com/nickharris808/gatecount) | exactly how many states does removing this check admit? |
| [`gridlock`](https://github.com/nickharris808/gridlock) | certify a wait-for relation cannot wedge |
| [`honestbench`](https://github.com/nickharris808/honestbench) | measure your CI's escape rate ← you are here |
| [`kvleak`](https://github.com/nickharris808/kvleak) | cross-tenant leak scanner |
| [`kvprobe`](https://github.com/nickharris808/kvprobe) | model-substitution detector with a measured FPR |
| [`preregister`](https://github.com/nickharris808/preregister) | refuses to seal a plan whose conclusion is already fixed |
| [`proof-carrying-ci`](https://github.com/nickharris808/proof-carrying-ci) | the whole portfolio as one CI check, with SARIF |
| [`proof-to-code-drift`](https://github.com/nickharris808/proof-to-code-drift) | fail the build when the proof stops matching |
| [`sf-verify`](https://github.com/nickharris808/sf-verify) | re-derive admission decisions offline |
| [`signoff-cert`](https://github.com/nickharris808/signoff-cert) | certificates that carry their own false-pass bound |
| [`tokencount`](https://github.com/nickharris808/tokencount) | a token count both parties can recompute |

**Benchmarks** — each recomputes one of our own published numbers from its certificate

| | |
|---|---|
| [`illusion-bench`](https://github.com/nickharris808/illusion-bench) | how many broken kernels does your oracle admit? |
| [`kv-reuse-econ-bench`](https://github.com/nickharris808/kv-reuse-econ-bench) | recompute our economics headline |
| [`llm-tenant-isolation-bench`](https://github.com/nickharris808/llm-tenant-isolation-bench) | recompute our isolation figures |

**Datasets**

| | |
|---|---|
| [`abstain-corpus`](https://huggingface.co/datasets/nickh007/abstain-corpus) | 32 inputs a verifier must NOT pass |
| [`kv-reuse-econ-traces`](https://huggingface.co/datasets/nickh007/kv-reuse-econ-traces) | per-workload reuse accounting + the closed form |
| [`kv-tenant-isolation-bench`](https://huggingface.co/datasets/nickh007/kv-tenant-isolation-bench) | isolation observations, uninterpretable rows included |
| [`llm-precision-fingerprints`](https://huggingface.co/datasets/nickh007/llm-precision-fingerprints) | precision-labelled logprobs with a negative control |

**Try it in a browser** — no install, no GPU

| | |
|---|---|
| [`negative-results-atlas`](https://huggingface.co/spaces/nickh007/negative-results-atlas) | ten claims we took back |
| [`tenant-leak-demo`](https://huggingface.co/spaces/nickh007/tenant-leak-demo) | the residency calculator |
| [`wait-for-visualiser`](https://huggingface.co/spaces/nickh007/wait-for-visualiser) | paste a wait-for graph, see the cycle |

### Documentation

Everything above, explained in one place: **<https://nickharris808.github.io/evidence-docs/>** —
the [tutorial](https://nickharris808.github.io/evidence-docs/start/tutorial/),
[what this proves and what it does not](https://nickharris808.github.io/evidence-docs/concepts/what-this-proves/),
and a [CLI reference](https://nickharris808.github.io/evidence-docs/reference/cli/) generated by
running `--help` on every published command.

### The commercial edition

Everything above is **measure-only** and Apache-2.0: it tells you what is true and never acts on
it. The **enforcement** side — binding a partition key at the admission decision, the compiled gate
corpus, and the certificate-*issuing* faucet — is covered by filed patents and licensed separately.

**Reading is free. Enforcing is licensed.**
<!-- /PORTFOLIO -->
