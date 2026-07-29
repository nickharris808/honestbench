"""honestbench — make a green pipeline attest CORRECTNESS, not just internal CONSISTENCY.

Five dependency-free primitives:

  merkle    — a sha256 manifest over any fileset + one-command tamper ``verify()``.
  registry  — bind every number a document quotes to its source artifact; drift becomes a
              test failure instead of a shipped claim.
  mutation  — prove your checks catch TAMPERING, not just drift: corrupt an artifact in a
              disposable workspace and flag any detector that stays green.
  absence   — prove your checks catch DELETION: remove an artifact and flag any check that
              still passes. A check that cannot fail is not a check.
  bounds    — never report a statistic without a bound; distribution-free, stdlib only.

The thesis: a manifest makes an evidence set tamper-evident, a registry makes the prose
re-derivable from the evidence, the mutation and absence audits prove the detectors actually
fire when the evidence lies, and the bounds stop a number being reported as if it said more
than the record supports.

MEASURE-ONLY BY DESIGN
----------------------
Nothing here admits, refuses, provisions, installs or deploys. Every entry point returns a
report; the caller decides what to do with it. That boundary is deliberate and is enforced in
CI — see CLAIMS-MAP.md.
"""
from __future__ import annotations

from . import absence, bounds, merkle, mutation, registry
from .absence import Probe, run_absence_audit
from .bounds import (
    UnboundedStatistic,
    chebyshev,
    clopper_pearson,
    describe,
    markov,
    sign_test_p,
    zero_observed_ceiling,
)
from .merkle import build_manifest, merkle_root, sha256_file, verify
from .mutation import Mutation, mark_workspace, run_audit, skip
from .registry import Registry, Row

__all__ = [
    "merkle", "registry", "mutation", "absence", "bounds",
    "sha256_file", "merkle_root", "build_manifest", "verify",
    "Registry", "Row",
    "Mutation", "run_audit", "mark_workspace", "skip",
    "Probe", "run_absence_audit",
    "clopper_pearson", "zero_observed_ceiling", "markov", "chebyshev", "sign_test_p",
    "describe", "UnboundedStatistic",
]

__version__ = "0.2.0"
