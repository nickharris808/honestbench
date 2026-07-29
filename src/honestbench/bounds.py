"""honestbench.bounds — never report a statistic without a bound.

WHY
---
"It agreed every time" is not a bound. "The mean was 0.03" is not a bound. A number reported
without a statement of what the record can support invites the reader to assume the record
supports more than it does.

This module supplies bounds that require **no distributional assumption**, so they survive a
workload that does not resemble the one a tool was characterised on. A distribution-free bound
is weaker than a parametric one, and that is the point: it cannot be invalidated by a change in
traffic.

Pure stdlib. No numpy, no scipy — a bound you cannot compute on a bare interpreter is a bound
nobody checks.

WHAT IS HERE
------------
``clopper_pearson``   exact binomial confidence interval (no normal approximation)
``zero_observed_ceiling``  the k=0 case: n trials, no failures, what rate is still consistent
``markov``            one-sided tail from the mean alone
``chebyshev``         two-sided tail from mean and variance
``sign_test_p``       distribution-free paired comparison
``describe``          format a statistic together with its bound, refusing to emit one alone

HONEST LIMITS, STATED IN THE CODE
---------------------------------
* Clopper-Pearson is exact but conservative; its coverage is >= the nominal level, not equal.
* Markov requires a non-negative variable; it returns None rather than a number otherwise.
* The sign test ignores magnitude. ``sign_test_p`` reports the count it actually used, so a
  reader can see how much data the p-value rests on.
"""
from __future__ import annotations

import math
from typing import Sequence

# ---------------------------------------------------------------------------------------
# Regularized incomplete beta, by continued fraction (Lentz). Needed for an EXACT binomial
# interval without scipy. Standard numerical recipe; the tests pin it against known values.
# ---------------------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float, itmax: int = 300, eps: float = 3e-16) -> float:
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def _beta_ppf(p: float, a: float, b: float, tol: float = 1e-12) -> float:
    """Inverse of ``betai`` in x, by bisection. Monotone, so bisection is safe and exact enough."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betai(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> dict:
    """Exact binomial interval for k successes in n trials.

    Exact in the sense that it inverts the binomial CDF rather than using a normal
    approximation, so it is valid at small n and at k = 0 or k = n where the normal
    approximation is worst — which is precisely the regime a conformance record lives in.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= k <= n:
        raise ValueError("k must be in [0, n]")
    alpha = 1.0 - confidence
    lo = 0.0 if k == 0 else _beta_ppf(alpha / 2.0, k, n - k + 1)
    hi = 1.0 if k == n else _beta_ppf(1.0 - alpha / 2.0, k + 1, n - k)
    return {
        "method": "clopper_pearson_exact",
        "k": k, "n": n, "confidence": confidence,
        "point": k / n,
        "lower": lo, "upper": hi,
        "note": "exact (inverts the binomial CDF); coverage is >= nominal, i.e. conservative",
    }


def zero_observed_ceiling(n: int, confidence: float = 0.95) -> dict:
    """n trials, zero failures observed: the largest failure rate still consistent.

    This is the bound that replaces "it agreed every time". At n=250 with 0 failures the
    one-sided 95% ceiling is about 1.2%, so a record of 250 clean trials does NOT support a
    claim of a rate below roughly one in eighty.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    # One-sided upper bound: 1 - alpha^(1/n).
    alpha = 1.0 - confidence
    upper = 1.0 - alpha ** (1.0 / n)
    return {
        "method": "rule_of_three_exact",
        "n": n, "observed_failures": 0, "confidence": confidence,
        "upper": upper,
        "statement": (f"{n} trials with 0 failures rejects every rate at or above "
                      f"{upper:.4f} at the {confidence:.0%} level"),
        "note": "one-sided; the record supports NO tighter rate than this",
    }


def markov(mean: float, threshold: float) -> dict | None:
    """P(X >= threshold) <= mean / threshold, for a NON-NEGATIVE variable.

    Returns None when the hypothesis fails or the bound is vacuous (>= 1), because reporting a
    bound of 1.4 as if it were information is exactly the dishonesty this module exists to stop.
    """
    if mean < 0 or threshold <= 0:
        return None
    b = mean / threshold
    if b >= 1.0:
        return None
    return {"method": "markov", "mean": mean, "threshold": threshold, "bound": b,
            "assumption": "X >= 0 only; no distribution assumed",
            "statement": f"P(X >= {threshold}) <= {b:.4f}"}


def chebyshev(mean: float, variance: float, k_sigma: float) -> dict | None:
    """P(|X - mean| >= k*sigma) <= 1/k^2. Two-sided, no distribution assumed."""
    if variance < 0 or k_sigma <= 0:
        return None
    b = 1.0 / (k_sigma ** 2)
    if b >= 1.0:
        return None
    sigma = math.sqrt(variance)
    return {"method": "chebyshev", "mean": mean, "sigma": sigma, "k": k_sigma, "bound": b,
            "assumption": "finite variance only; no distribution assumed",
            "statement": f"P(|X - {mean:.4g}| >= {k_sigma}*{sigma:.4g}) <= {b:.4f}"}


def sign_test_p(pairs: Sequence[tuple[float, float]]) -> dict:
    """Two-sided sign test over paired observations. Ties are dropped and counted.

    Distribution-free: it uses only the sign of each difference, so an A/B comparison between
    two configurations assumes nothing about the shape of either. It also IGNORES magnitude,
    which is a real limitation and is reported rather than buried — ``n_used`` tells the reader
    how much data the p-value actually rests on.
    """
    pos = sum(1 for a, b in pairs if b > a)
    neg = sum(1 for a, b in pairs if b < a)
    ties = len(pairs) - pos - neg
    n = pos + neg
    if n == 0:
        return {"method": "sign_test", "n_used": 0, "n_ties": ties, "p_value": None,
                "statement": "every pair tied; the test has no information"}
    wins = max(pos, neg)
    # Two-sided exact binomial p under p=1/2.
    tail = sum(math.comb(n, i) for i in range(wins, n + 1)) / (2 ** n)
    p = min(1.0, 2.0 * tail)
    return {"method": "sign_test", "n_used": n, "n_ties": ties,
            "n_positive": pos, "n_negative": neg, "p_value": p,
            "assumption": "no distribution assumed; magnitude IGNORED",
            "statement": f"sign test over {n} untied pairs: p = {p:.4g}"}


class UnboundedStatistic(Exception):
    """Raised when a statistic is reported with no bound. That is the whole point."""


def describe(name: str, value: float, bound: dict | None) -> str:
    """Format a statistic together with its bound; REFUSE to format one without.

    This is the module's actual contract. Every other function here is a way of producing the
    ``bound`` argument.
    """
    if bound is None:
        raise UnboundedStatistic(
            f"{name!r} was reported with no bound. Supply one of clopper_pearson / "
            f"zero_observed_ceiling / markov / chebyshev / sign_test_p, or state explicitly "
            f"why the statistic needs none."
        )
    return f"{name} = {value:.6g}   [{bound['method']}] {bound.get('statement', bound)}"


__all__ = [
    "betai", "clopper_pearson", "zero_observed_ceiling", "markov", "chebyshev",
    "sign_test_p", "describe", "UnboundedStatistic",
]
