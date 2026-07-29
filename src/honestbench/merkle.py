"""honestbench.merkle — a signed (sha256) Merkle manifest over a set of files.

Generalised from a proof-index builder used in production on a large evidence set.
Hash every file, record (path, bytes, sha256), fold the sorted ``path:sha256\\n`` lines
into ONE root hash. `verify()` re-hashes and reports any missing file or hash mismatch —
so a single call attests that nothing in a committed evidence set was altered.

Standalone: no third-party deps, no repo-specific paths. Point it at any directory.
"""
from __future__ import annotations

import hashlib
import os
from typing import Callable, Iterable


def sha256_file(path: str, _bufsize: int = 65536) -> tuple[str, int]:
    """Return (hex sha256, byte count) streamed in chunks (constant memory)."""
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_bufsize), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def merkle_root(entries: Iterable[dict]) -> str:
    """Fold sorted ``path:sha256\\n`` lines into one root hash.

    Order-independent by construction (entries are sorted by path first), so the root
    depends only on the SET of (path, content), never on discovery order.
    """
    h = hashlib.sha256()
    for e in sorted(entries, key=lambda x: x["path"]):
        h.update(f"{e['path']}:{e['sha256']}\n".encode())
    return h.hexdigest()


def collect(root_dir: str,
            include: Callable[[str], bool] | None = None) -> list[str]:
    """Every file under ``root_dir`` (root-relative, sorted) for which ``include(rel)`` is true.

    ``include`` defaults to "everything". Pass a predicate to scope by extension/prefix —
    the same role the repo's `_collect()` globs play, but caller-supplied so the package
    stays portable.
    """
    include = include or (lambda _rel: True)
    rels: list[str] = []
    for dirpath, dirs, names in os.walk(root_dir):
        dirs.sort()
        for nm in sorted(names):
            rel = os.path.relpath(os.path.join(dirpath, nm), root_dir).replace(os.sep, "/")
            if include(rel):
                rels.append(rel)
    return sorted(set(rels))


def build_manifest(root_dir: str,
                   include: Callable[[str], bool] | None = None,
                   restrict: Iterable[str] | None = None) -> dict:
    """Build a manifest dict over ``root_dir``.

    ``restrict`` (optional) is a set of root-relative paths the result is intersected with —
    the portable analogue of "committed artifacts only" (pass ``git ls-files`` output to
    attest only tracked files).
    """
    restrict_set = None if restrict is None else {p.replace(os.sep, "/") for p in restrict}
    entries = []
    for rel in collect(root_dir, include):
        if restrict_set is not None and rel not in restrict_set:
            continue
        digest, nbytes = sha256_file(os.path.join(root_dir, rel))
        entries.append({"path": rel, "bytes": nbytes, "sha256": digest})
    return {
        "artifact": "honestbench_manifest",
        "version": 1,
        "hash_algo": "sha256",
        "root_hash": merkle_root(entries),
        "n_artifacts": len(entries),
        "artifacts": entries,
    }


def verify(manifest: dict, root_dir: str) -> dict:
    """Re-hash every file in ``manifest`` against ``root_dir``.

    Returns {"ok", "root_matches", "missing", "changed", "recomputed_root"}. ``ok`` is
    True iff no file is missing, no hash drifted, AND the recomputed root equals the
    committed one — the whole set attested in one call.
    """
    missing, changed, live_entries = [], [], []
    for e in manifest.get("artifacts", []):
        ap = os.path.join(root_dir, e["path"])
        if not os.path.exists(ap):
            missing.append(e["path"])
            continue
        digest, _ = sha256_file(ap)
        live_entries.append({"path": e["path"], "sha256": digest})
        if digest != e["sha256"]:
            changed.append(e["path"])
    recomputed = merkle_root(live_entries) if not missing else None
    root_matches = recomputed == manifest.get("root_hash") and not missing
    return {
        "ok": (not missing) and (not changed) and root_matches,
        "root_matches": root_matches,
        "missing": missing,
        "changed": changed,
        "recomputed_root": recomputed,
        "committed_root": manifest.get("root_hash"),
    }
