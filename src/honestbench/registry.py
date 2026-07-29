"""honestbench.registry — the number-registry drift guard.

Generalised from a number-registry guard used to keep a large report set honest.
Every headline number a document quotes is
registered as (source JSON, dotted pointer into it, display format). `check_document`
formats each registered value from its live source and asserts the formatted token
appears in the document — so the "361,576 in the prose vs 361,587 in the cert" class of
hand-drift FAILS loudly instead of shipping.

The point: a number in a doc is a CLAIM about an artifact. Registering it makes the doc
re-derivable from the evidence, and makes silent divergence a test failure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


def resolve(obj, pointer: str):
    """Walk a dotted pointer into nested dict/list. Ints index lists, else dict keys."""
    for part in pointer.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def fmt(value, code: str) -> str:
    """Format a value the way a human writes it in prose (so tokens compare byte-for-byte)."""
    if code == "int_commas":
        return f"{int(round(float(value))):,}"
    if code == "float1":
        return f"{float(value):.1f}"
    if code == "float2":
        return f"{float(value):.2f}"
    if code == "frac3":
        return f"{float(value):.3f}"
    if code == "raw":
        return str(value)
    raise ValueError(f"unknown format code: {code!r}")


@dataclass
class Row:
    source: str        # path to the JSON artifact (source of truth)
    pointer: str       # dotted pointer into it
    fmt: str           # a code understood by fmt()
    anchor: str | None = None   # optional nearby substring the token must appear beside


class Registry:
    """A list of Row bindings + the drift check over a document string."""

    def __init__(self, rows: list[Row] | None = None, load=json.load):
        self.rows = list(rows or [])
        self._load = load
        self._cache: dict[str, dict] = {}

    def add(self, source: str, pointer: str, fmt: str, anchor: str | None = None) -> "Registry":
        self.rows.append(Row(source, pointer, fmt, anchor))
        return self

    def _artifact(self, path: str) -> dict:
        if path not in self._cache:
            with open(path) as fh:
                self._cache[path] = self._load(fh)
        return self._cache[path]

    def expected(self) -> list[dict]:
        """Resolve+format every row from its live source. Raises on a broken pointer."""
        out = []
        for r in self.rows:
            val = resolve(self._artifact(r.source), r.pointer)
            out.append({"row": f"{r.source}:{r.pointer}", "token": fmt(val, r.fmt),
                        "anchor": r.anchor})
        return out

    def check_document(self, text: str) -> list[dict]:
        """Return the list of DRIFT failures (empty == the document matches all evidence).

        A row fails if its formatted token is absent from ``text`` (or, when an anchor is
        given, if the token never appears within the same line as the anchor).
        """
        failures = []
        lines = text.splitlines()
        for exp in self.expected():
            tok, anchor = exp["token"], exp["anchor"]
            if anchor is None:
                present = tok in text
            else:
                present = any((tok in ln and anchor in ln) for ln in lines)
            if not present:
                failures.append({"row": exp["row"], "missing_token": tok, "anchor": anchor})
        return failures
