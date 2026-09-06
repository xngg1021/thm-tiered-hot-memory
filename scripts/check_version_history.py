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


def show_text_optional(sha: str, path: str) -> str | None:
    proc = git("show", f"{sha}:{path}", check=False)
    return None if proc.returncode != 0 else proc.stdout


def parse_version_payload(raw: str, evidence: str, label: str) -> str | None:
    if evidence.endswith("pyproject.toml"):
        match = VERSION_RE.search(raw)
        if not match:
            raise HistoryError(f"{label}: no project version found in {evidence}")
        return match.group(1)
    if evidence.endswith(".json"):
        payload = json.loads(raw)
        observed = payload.get("engine_version") or payload.get("version") or payload.get("release")
        if observed is None:
            raise HistoryError(
                f"{label}: no engine_version/version/release in {evidence}"
            )
        return observed
    raise HistoryError(f"{label}: unsupported version evidence: {evidence}")


def verify_closeout_report(
    snapshot: dict[str, object], evidence: str, version: str, sha: str
) -> None:
    """Validate a post-merge closeout that intentionally cannot exist in the frozen code tree.

    Workflow run IDs are only known after the accepted code SHA is pushed. Such a
    report may therefore live in a forward-only descendant. The frozen commit must
    still self-identify its package version independently via pyproject.toml.
    """
    path = ROOT / evidence
    if not path.is_file():
        raise HistoryError(f"{snapshot['id']}: closeout evidence missing from current tree: {evidence}")
    raw = path.read_text(encoding="utf-8")
    observed = parse_version_payload(raw, evidence, str(snapshot["id"]))
    if observed != version:
        raise HistoryError(
            f"{snapshot['id']}: manifest says {version}, closeout evidence says {observed}"
        )
    payload = json.loads(raw)
    if payload.get("accepted_merge_commit") != sha:
        raise HistoryError(
            f"{snapshot['id']}: closeout accepted_merge_commit does not match frozen commit"
        )
    if payload.get("archive_branch") != snapshot.get("archive_branch"):
        raise HistoryError(
            f"{snapshot['id']}: closeout archive_branch does not match manifest"
        )

    package_raw = show_text_optional(sha, "pyproject.toml")
    if package_raw is None:
        raise HistoryError(
            f"{snapshot['id']}: post-merge closeout requires pyproject.toml in frozen commit"
        )
    package_version = parse_version_payload(
        package_raw, "pyproject.toml", f"{snapshot['id']} frozen package"
    )
    if package_version != version:
        raise HistoryError(
            f"{snapshot['id']}: frozen package says {package_version}, manifest says {version}"
        )


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
    raw = show_text_optional(sha, evidence)
    if raw is None:
        # A release closeout containing workflow IDs may only be written after the
        # accepted merge exists. We accept that shape only with stronger binding:
        # current-tree report -> exact accepted SHA/archive + frozen pyproject version.
        verify_closeout_report(snapshot, evidence, version, sha)
        return

    observed = parse_version_payload(raw, evidence, str(snapshot["id"]))
    if observed != version:
        raise HistoryError(
            f"{snapshot['id']}: manifest says {version}, evidence says {observed} at {sha}"
        )


def verify_acceptance(snapshot: dict[str, object]) -> None:
    acceptance = snapshot.get("acceptance")
    if acceptance is None:
        return
    if not isinstance(acceptance, dict):
        raise HistoryError(f"{snapshot['id']}: acceptance must be an object")
    required_ints = ("feature_pr", "correctness_run", "hermes_run", "harness_run", "retrieval_run")
    for field in required_ints:
        value = acceptance.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise HistoryError(f"{snapshot['id']}: acceptance.{field} must be a positive integer")
    if acceptance.get("retrieval_conclusion") != "skipped-no-retrieval-path-change":
        raise HistoryError(
            f"{snapshot['id']}: unsupported retrieval acceptance conclusion"
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
        feature_head = snapshot.get("feature_head")
        if feature_head is not None:
            require_commit(str(feature_head), f"{sid}.feature_head")
            if git("merge-base", "--is-ancestor", str(feature_head), sha, check=False).returncode != 0:
                raise HistoryError(f"{sid}: feature_head is not an ancestor of freeze commit")
        verify_version_evidence(snapshot)
        verify_acceptance(snapshot)
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
    except (HistoryError, json.JSONDecodeError, UnicodeError, OSError) as exc:
        print(f"VERSION_HISTORY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
