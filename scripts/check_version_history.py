#!/usr/bin/env python3
"""Validate THM's machine-readable historical recovery map against Git itself."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "versions" / "history.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


class HistoryError(RuntimeError):
    pass


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise HistoryError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


def require_commit(sha: str, label: str) -> None:
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise HistoryError(f"{label}: invalid full commit SHA: {sha!r}")
    git("cat-file", "-e", f"{sha}^{{commit}}")
    ancestor = git("merge-base", "--is-ancestor", sha, "HEAD", check=False)
    if ancestor.returncode != 0:
        raise HistoryError(f"{label}: {sha} is not an ancestor of the checked-out history")


def require_archive_ref(branch: str, expected_sha: str, label: str) -> None:
    """Require a locally fetched archive ref to point at the manifest commit."""
    candidates = (
        f"refs/remotes/origin/{branch}",
        f"refs/heads/{branch}",
    )
    observed = None
    for ref in candidates:
        result = git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
        if result.returncode == 0:
            observed = result.stdout.strip()
            break
    if observed is None:
        raise HistoryError(
            f"{label}: archive ref {branch!r} is not present in the fetched Git refs; "
            "CI must checkout with full branch history"
        )
    if observed != expected_sha:
        raise HistoryError(
            f"{label}: archive ref {branch!r} moved: expected {expected_sha}, observed {observed}"
        )


def show_text(sha: str, path: str) -> str:
    return git("show", f"{sha}:{path}").stdout


def verify_version_evidence(snapshot: dict[str, object]) -> None:
    version = snapshot.get("version")
    evidence = snapshot.get("version_evidence")
    if version is None:
        if evidence is not None:
            raise HistoryError(f"{snapshot['id']}: unversioned snapshot has version_evidence")
        return
    if not isinstance(version, str) or not version:
        raise HistoryError(f"{snapshot['id']}: invalid version")
    if not isinstance(evidence, str) or not evidence:
        raise HistoryError(f"{snapshot['id']}: versioned snapshot lacks version_evidence")

    sha = str(snapshot["commit"])
    raw = show_text(sha, evidence)
    if evidence.endswith("pyproject.toml"):
        match = VERSION_RE.search(raw)
        if not match:
            raise HistoryError(f"{snapshot['id']}: no project version found in {evidence}@{sha}")
        observed = match.group(1)
    elif evidence.endswith(".json"):
        payload = json.loads(raw)
        observed = payload.get("engine_version") or payload.get("version")
        if observed is None:
            raise HistoryError(f"{snapshot['id']}: no engine_version/version in {evidence}@{sha}")
    else:
        raise HistoryError(f"{snapshot['id']}: unsupported version evidence: {evidence}")

    if observed != version:
        raise HistoryError(
            f"{snapshot['id']}: manifest says {version}, evidence says {observed} at {sha}"
        )


def main() -> int:
    payload = json.loads(HISTORY.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise HistoryError("versions/history.json: unsupported schema_version")
    if payload.get("repository") != "xngg1021/thm-tiered-hot-memory":
        raise HistoryError("versions/history.json: unexpected repository identity")

    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        raise HistoryError("versions/history.json: snapshots must be a non-empty list")

    ids: set[str] = set()
    commits: set[str] = set()
    ordered_commits: list[tuple[str, str]] = []

    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise HistoryError("snapshot must be an object")
        sid = snapshot.get("id")
        sha = snapshot.get("commit")
        branch = snapshot.get("archive_branch")
        if not isinstance(sid, str) or not sid:
            raise HistoryError("snapshot has missing id")
        if sid in ids:
            raise HistoryError(f"duplicate snapshot id: {sid}")
        ids.add(sid)
        if not isinstance(sha, str):
            raise HistoryError(f"{sid}: missing commit")
        if sha in commits:
            raise HistoryError(f"{sid}: duplicate milestone commit: {sha}")
        commits.add(sha)
        if not isinstance(branch, str) or not branch.startswith("archive/"):
            raise HistoryError(f"{sid}: archive branch must use archive/ namespace")
        if snapshot.get("recoverability") != "exact-git-snapshot":
            raise HistoryError(f"{sid}: milestone must be classified exact-git-snapshot")

        require_commit(sha, sid)
        require_archive_ref(branch, sha, sid)
        introduced = snapshot.get("introduced_commit")
        if introduced is not None:
            require_commit(str(introduced), f"{sid}.introduced_commit")
            if git("merge-base", "--is-ancestor", str(introduced), sha, check=False).returncode != 0:
                raise HistoryError(f"{sid}: introduced_commit is not an ancestor of freeze commit")
        verify_version_evidence(snapshot)
        ordered_commits.append((sid, sha))

    for (prev_id, prev), (next_id, nxt) in zip(ordered_commits, ordered_commits[1:]):
        if git("merge-base", "--is-ancestor", prev, nxt, check=False).returncode != 0:
            raise HistoryError(
                f"history order broken: {prev_id}@{prev} is not an ancestor of {next_id}@{nxt}"
            )

    boundaries = payload.get("development_boundaries", [])
    if not isinstance(boundaries, list):
        raise HistoryError("development_boundaries must be a list")
    for idx, boundary in enumerate(boundaries):
        if not isinstance(boundary, dict):
            raise HistoryError(f"development_boundaries[{idx}] must be an object")
        require_commit(str(boundary.get("commit", "")), f"development_boundaries[{idx}]")

    generated_from = payload.get("generated_from_commit")
    require_commit(str(generated_from), "generated_from_commit")

    print(
        f"version history OK: {len(snapshots)} milestone snapshots, "
        f"{len(boundaries)} development boundaries, archive refs pinned"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HistoryError, json.JSONDecodeError) as exc:
        print(f"VERSION_HISTORY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
