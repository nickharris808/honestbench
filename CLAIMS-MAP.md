# CLAIMS-MAP — honestbench

**Tag: CLEAN. Licence: Apache-2.0.**

This file exists so the CLEAN tag is *auditable* rather than asserted. It names the filed claims
this package approaches, and states the specific step it does **not** perform.

## The line

Every independent claim in the corresponding filed specification terminates in a **physical
actuation** step — writing bytes into a memory region, loading a kernel into a serving path,
provisioning a resource, admitting a subject into an executing path, refusing an operation upon
a physical resource.

A tool that **measures and reports** performs no such step. A tool that **gates an admission
decision** does.

honestbench measures. Every entry point returns a report.

## Claims approached, and the step not performed

| Filed claim family | What it recites | What honestbench does instead |
|---|---|---|
| Self-referential evidence index (sealing an evidence set backing an admission gate) | *(a)* digest tree over the evidence set → root; *(b)* regenerate the summary without incorporating the root; *(c)* recompute; **(d) refuse to admit a gate decision** in reliance on the set when a member carries a divergent root | `merkle` performs (a) and a verify. It does **not** perform (d): it backs no admission gate and refuses no decision. There is no gate. |
| Certificate-derived render validation | validating that each numeric assertion rendered into a member of the evidence set matches the certificate it derives from | `registry` performs the comparison and returns failures. The claim is a dependent of the sealing claim above and inherits its (d). |
| Positive-control qualification of a validation procedure | introducing a defect of a class the procedure is intended to detect, recording that it refuses, and **withholding reliance** on it otherwise | `mutation` and `absence` perform the introduction and the recording. They report an escape list; they withhold nothing and gate nothing. |
| Distribution-free instance bounds on a gate's statistics | computing a bound requiring no distributional assumption and **emitting it in a certificate**, refusing to emit the statistic without it | `bounds` computes the bounds and `describe()` refuses to *format* an unbounded statistic. It emits no certificate and admits nothing. |
| Finite-sample evidence ceiling | computing an exact upper bound on a rate consistent with a k-of-n record, and **admitting a state-reuse operation** only where a required rate is at or above it | `clopper_pearson` / `zero_observed_ceiling` compute the bound. No state-reuse operation exists here to admit. |

## Enforcement

This is not an honour system. `oss/tools/check_measure_only.py` scans every CLEAN-tagged
artifact and fails the build on an actuation construct:

- invocation of a deployment / serving / orchestration verb
- a write into a serving, deployment, or model path
- a function named `admit*` / `refuse*` / `gate*` / `provision*` / `install*` / `deploy*`
- loading a model or adapter into a serving engine

Exit codes are deliberately **not** flagged — `raise SystemExit(main())` is the ordinary CLI
idiom and exiting non-zero to *report* a verdict is not the claimed actuation. The rail's first
version flagged them and produced four false positives; a rail that cries wolf gets switched
off, which is worse than no rail.

## Why the licence is Apache-2.0 and not BSL

Apache-2.0 §3 grants an express patent licence to the claims a published implementation
practices. That is precisely why the measure/gate line matters: because honestbench practices
none of the filed claims, Apache-2.0 grants nothing away, and the package can carry the most
permissive licence available — which is what maximises adoption.

A package that **did** gate would have to ship under BSL 1.1 or a dual licence. If a
contribution ever crosses that line, the correct response is to re-tag and re-licence the
artifact, not to keep the tag and hope.

## The commercial boundary, stated plainly

honestbench tells you **that** your evidence is intact, **that** your checks are blind, and
**what** your record actually supports.

It does not decide anything on the strength of that. An admission gate that refuses to install
bytes when the backing evidence does not verify — with a certificate a relying party verifies
offline, without contacting the issuer — is a separate, commercially licensed product covered by
the filed claims above.
