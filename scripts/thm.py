#!/usr/bin/env python3
"""THM 1.1: profile-bound index maintenance and residency proposals.

The six original commands remain available. This program never writes Hermes
MEMORY.md/USER.md, never moves their entries and never calls a model. See
 docs/06-engine-guide.md for CLI, migration and persistence boundaries.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

VERSION = "1.1.0"
BASE = Path(__file__).resolve().parents[1]
STORES = ("MEMORY.md", "USER.md")
W = {"hit": 2.0, "confirm": 1.5, "create": 1.0,
     "display": 0.0, "retrieve": 0.0, "promote": 0.0, "demote": 0.0}
REVIEW_LADDER = (3, 7, 30, 90)
DEMOTE_A, DEMOTE_AGE, COLD_A, COLD_IDLE = 0.6, 21, 0.3, 90
MAX_BYTES = 8 * 1024 * 1024


class ThmError(Exception):
    """An explicit operation failure, not an empty successful result."""


def today():
    return dt.date.today()


def day(value, *, future=False, now=None):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ThmError("INVALID_DATE: expected YYYY-MM-DD")
    try:
        result = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ThmError("INVALID_DATE: impossible calendar date") from exc
    if not future and result > (now or today()):
        raise ThmError("FUTURE_EVENT_DATE")
    return result


def days_since(value, now=None):
    now = now or today()
    return (now - day(value, now=now)).days


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    try:
        raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ThmError("INVALID_JSON_VALUE") from exc
    if len(raw) > MAX_BYTES:
        raise ThmError("INDEX_SIZE_LIMIT")
    return raw


def read_bytes(path):
    path = Path(path)
    if path.is_symlink():
        raise ThmError("SYMLINK_FILE_NOT_SUPPORTED")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ThmError("FILE_SIZE_LIMIT")
    return raw


def decode(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ThmError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def bad_constant(_):
        raise ThmError("NONFINITE_JSON_NUMBER")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, UnicodeError) as exc:
        raise ThmError("INVALID_INDEX_JSON") from exc


def normal_path(value, relative_to=None):
    value = os.path.expandvars(os.path.expanduser(str(value)))
    if not value.strip() or "\x00" in value or value.startswith("~"):
        raise ThmError("INVALID_PATH")
    path = Path(value)
    if not path.is_absolute():
        path = (relative_to or Path.cwd()) / path
    return path.resolve()


def config_paths(mem_dir=None, state_dir=None, conf=None):
    """Resolve configuration only after a command has passed argument parsing."""
    conf = Path(conf) if conf else BASE / "thm.conf"
    options = {}
    if conf.exists():
        for line in read_bytes(conf).decode("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not sep or key not in ("mem_dir", "state_dir") or not value or key in options:
                raise ThmError("INVALID_CONFIG_LINE")
            options[key] = normal_path(value, conf.resolve().parent)
    home = normal_path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    mem = normal_path(mem_dir or os.environ.get("THM_MEM_DIR") or options.get("mem_dir") or home / "memories")
    state = normal_path(state_dir or os.environ.get("THM_STATE_DIR") or options.get("state_dir") or mem / ".thm")
    return mem, state


def parse_store(path):
    """Read section-sign-delimited entries; preserve internal newlines and line numbers."""
    try:
        text = read_bytes(path).decode("utf-8")
    except FileNotFoundError as exc:
        raise ThmError("SOURCE_UNAVAILABLE: " + Path(path).name) from exc
    except UnicodeError as exc:
        raise ThmError("SOURCE_ENCODING_INVALID") from exc
    entries, lines, start = [], [], None
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip() == "§":
            if lines:
                entries.append(("\n".join(lines).strip(), start))
            lines, start = [], None
        else:
            if start is None and line.strip():
                start = number
            if start is not None:
                lines.append(line)
    if lines:
        entries.append(("\n".join(lines).strip(), start))
    return [(text, number) for text, number in entries if text]


def source_hash(store, text):
    return digest((store + "\0" + text).encode("utf-8"))


def activation(entry, now=None):
    """Activity heuristic only. Unknown/invalid events fail; movement has zero weight."""
    now = now or today()
    score = 0.0
    seen = set()
    for event in entry.get("events", []):
        kind = event.get("type")
        if kind not in W:
            raise ThmError("UNKNOWN_EVENT_TYPE")
        age = days_since(event.get("t"), now)
        event_id = event.get("event_id")
        if event_id:
            if event_id in seen:
                raise ThmError("DUPLICATE_EVENT_ID")
            seen.add(event_id)
        if kind == "confirm" and not event.get("evidence"):
            if event.get("legacy_unverified") is True:
                continue
            raise ThmError("CONFIRMATION_EVIDENCE_REQUIRED")
        score += W[kind] * (age + 1) ** -0.5
    return score


@contextmanager
def index_lock(path, timeout=5.0):
    """OS advisory lock on a stable lock file. Process exit releases the lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ThmError("SYMLINK_LOCK_NOT_SUPPORTED")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ThmError("INDEX_BUSY") from None
                time.sleep(0.025)
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        # Do not unlink: another process may already hold this inode open.


def atomic_write(path, raw):
    """Same-directory atomic replacement; not a multi-file or hardware durability promise."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ThmError("SYMLINK_TARGET_NOT_SUPPORTED")
    fd, name = tempfile.mkstemp(prefix=".thm-tmp-", dir=path.parent)
    replaced = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        replaced = True
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except OSError as exc:
        if replaced:
            raise ThmError("COMMIT_VISIBLE_SYNC_UNCERTAIN: read back before retry; reuse event ID") from exc
        raise
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Snapshot:
    def __init__(self, data, etag):
        self.data, self.etag = data, etag


class Engine:
    def __init__(self, mem_dir, state_dir=None, clock=today):
        self.mem_dir = normal_path(mem_dir)
        self.state_dir = normal_path(state_dir or self.mem_dir / ".thm")
        self.index = self.state_dir / "index.json"
        self.clock = clock

    def empty(self):
        return {"version": 2, "revision": 0, "mem_dir": str(self.mem_dir), "entries": []}

    def validate(self, data):
        if not isinstance(data, dict) or data.get("version") != 2:
            raise ThmError("LEGACY_INDEX_REQUIRES_EXPLICIT_MIGRATION")
        if data.get("mem_dir") != str(self.mem_dir):
            raise ThmError("MEMORY_DIRECTORY_MISMATCH")
        if type(data.get("revision")) is not int or data["revision"] < 0:
            raise ThmError("INVALID_INDEX_REVISION")
        entries = data.get("entries")
        if not isinstance(entries, list):
            raise ThmError("INVALID_ENTRIES")
        ids = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", entry["id"]) or entry["id"] in ids:
                raise ThmError("INVALID_OR_DUPLICATE_ENTRY_ID")
            ids.add(entry["id"])
            if entry.get("tier") not in ("T0", "T1", "T2", "T3") or entry.get("cost_class") not in ("low", "med", "high"):
                raise ThmError("INVALID_TIER_OR_COST")
            if not isinstance(entry.get("store"), str) or not isinstance(entry.get("key"), str) or not entry["key"] or not isinstance(entry.get("summary"), str):
                raise ThmError("INVALID_ENTRY_TEXT")
            if type(entry.get("pinned")) is not bool or entry.get("status") not in ("active", "invalid", "deleted", "unresolved_legacy"):
                raise ThmError("INVALID_ENTRY_STATE")
            sh = entry.get("source_hash")
            if sh is not None and (not isinstance(sh, str) or not re.fullmatch(r"[0-9a-f]{64}", sh)):
                raise ThmError("INVALID_SOURCE_HASH")
            if entry["status"] == "active" and not sh:
                raise ThmError("ACTIVE_ENTRY_REQUIRES_SOURCE_HASH")
            day(entry.get("created"), now=self.clock())
            for field in ("next_review", "valid_from", "valid_until"):
                if entry.get(field) is not None:
                    day(entry[field], future=True)
            if entry.get("valid_from") and entry.get("valid_until") and entry["valid_from"] >= entry["valid_until"]:
                raise ThmError("INVALID_VALIDITY_INTERVAL")
            stage = entry.get("review_stage")
            if type(stage) is not int or not 0 <= stage < len(REVIEW_LADDER):
                raise ThmError("INVALID_REVIEW_STAGE")
            events = entry.get("events")
            if not isinstance(events, list) or any(not isinstance(e, dict) or not isinstance(e.get("event_id"), str) or not e["event_id"] for e in events):
                raise ThmError("INVALID_EVENTS")
            activation(entry, self.clock())
        encoded(data)

    def load(self):
        try:
            raw = read_bytes(self.index)
        except FileNotFoundError:
            return Snapshot(self.empty(), None)
        data = decode(raw)
        self.validate(data)
        return Snapshot(data, digest(raw))

    def _save_locked(self, snapshot):
        current = self.load()
        if current.etag != snapshot.etag or current.data["revision"] != snapshot.data["revision"]:
            raise ThmError("INDEX_CONFLICT")
        candidate = copy.deepcopy(snapshot.data)
        candidate["revision"] += 1
        self.validate(candidate)
        raw = encoded(candidate)  # Serialize before opening any target.
        if current.etag is not None:
            old = read_bytes(self.index)
            if digest(old) != current.etag:
                raise ThmError("INDEX_CONFLICT")
            atomic_write(self.state_dir / "index.previous.json", old)
        atomic_write(self.index, raw)
        if read_bytes(self.index) != raw:
            raise ThmError("INDEX_READBACK_MISMATCH")
        snapshot.data, snapshot.etag = candidate, digest(raw)

    def save(self, snapshot):
        with index_lock(self.state_dir / "index.lock"):
            self._save_locked(snapshot)

    def update(self, operation):
        with index_lock(self.state_dir / "index.lock"):
            snapshot = self.load()
            before = encoded(snapshot.data)
            result = operation(snapshot.data)
            if encoded(snapshot.data) != before:
                self._save_locked(snapshot)
            return result

    def stores(self):
        return {name: parse_store(self.mem_dir / name) for name in STORES}

    def add(self, data, store, text, cost="med", pinned=False):
        fingerprint = source_hash(store, text)
        prior = [e for e in data["entries"] if e.get("source_hash") == fingerprint and e["store"] == store]
        if prior:
            return prior[0], False  # A tombstone is not silently resurrected.
        now = self.clock().isoformat()
        identifier = "e" + uuid.uuid4().hex
        entry = {"id": identifier, "tier": "T0", "store": store,
                 "key": text[:24], "summary": text[:60], "source_hash": fingerprint,
                 "created": now, "created_basis": "registration_date_not_source_age",
                 "events": [{"event_id": "create:" + identifier, "type": "create", "t": now}],
                 "cost_class": cost, "pinned": bool(pinned), "status": "active",
                 "review_stage": 0, "next_review": (self.clock() + dt.timedelta(days=3)).isoformat()}
        data["entries"].append(entry)
        return entry, True

    def seed(self):
        stores = self.stores()  # Missing source is never reported as empty.
        def mutate(data):
            added = sum(self.add(data, name, text)[1] for name, items in stores.items() for text, _ in items)
            return {"status": "OK", "added": added, "total": len(data["entries"])}
        return self.update(mutate)

    def register(self, store, needle, cost, pinned=False):
        if store not in STORES or cost not in ("high", "med", "low") or not needle:
            raise ThmError("INVALID_REGISTER_ARGUMENT")
        matches = sorted(set(text for text, _ in parse_store(self.mem_dir / store) if needle in text))
        if len(matches) != 1:
            raise ThmError("ENTRY_NOT_FOUND" if not matches else "AMBIGUOUS_SOURCE_MATCH")
        def mutate(data):
            entry, added = self.add(data, store, matches[0], cost, pinned)
            return {"status": "OK", "id": entry["id"], "added": added}
        return self.update(mutate)

    def find(self, data, needle):
        if not needle or not needle.strip():
            raise ThmError("EMPTY_SELECTOR")
        exact = [e for e in data["entries"] if e["id"] == needle]
        if exact:
            return exact[0]
        hits = [e for e in data["entries"] if needle in e["key"] or needle in e["summary"]]
        if not hits:
            for store, items in self.stores().items():
                fingerprints = {source_hash(store, text) for text, _ in items if needle in text}
                hits.extend(e for e in data["entries"] if e["store"] == store and e.get("source_hash") in fingerprints)
        if len(hits) != 1:
            raise ThmError("ENTRY_NOT_FOUND" if not hits else "AMBIGUOUS_ENTRY: " + ",".join(e["id"] for e in hits))
        return hits[0]

    def eligible(self, entry):
        now = self.clock().isoformat()
        return (entry["status"] == "active"
                and (not entry.get("valid_from") or entry["valid_from"] <= now)
                and (not entry.get("valid_until") or now < entry["valid_until"]))

    def feedback(self, kind, needle, note="", event_id=None, evidence=None):
        if kind not in ("hit", "confirm"):
            raise ThmError("INVALID_FEEDBACK_TYPE")
        if kind == "confirm" and (not isinstance(evidence, str) or not evidence.strip()):
            raise ThmError("CONFIRMATION_EVIDENCE_REQUIRED")
        if event_id is not None and (not event_id.strip() or len(event_id) > 200):
            raise ThmError("INVALID_EVENT_ID")
        if len(note) > 4000 or (evidence and len(evidence) > 2000):
            raise ThmError("FEEDBACK_TOO_LONG")
        def mutate(data):
            entry = self.find(data, needle)
            if not self.eligible(entry):
                raise ThmError("ENTRY_NOT_CURRENTLY_ELIGIBLE")
            if entry["tier"] != "T0" or entry["store"] not in STORES:
                raise ThmError("NON_T0_FEEDBACK_REQUIRES_A_SOURCE_ADAPTER")
            actual = {source_hash(entry["store"], text) for text, _ in parse_store(self.mem_dir / entry["store"])}
            if entry["source_hash"] not in actual:
                raise ThmError("SOURCE_CHANGED_OR_REMOVED: reconcile before feedback")
            event = {"type": kind, "t": self.clock().isoformat(), "note": note}
            if kind == "confirm":
                event["evidence"] = evidence.strip()
            event["event_id"] = event_id or "auto:" + digest(encoded({"entry": entry["id"], **event}))
            old = next((e for e in entry["events"] if e["event_id"] == event["event_id"]), None)
            if old is not None:
                if old != event:
                    raise ThmError("EVENT_ID_REUSED_WITH_DIFFERENT_CONTENT")
                return {"status": "DUPLICATE", "id": entry["id"]}
            if kind == "confirm" and any(e["type"] == "confirm" and e["t"] == event["t"] and not e.get("legacy_unverified") for e in entry["events"]):
                return {"status": "ALREADY_CONFIRMED_TODAY", "id": entry["id"]}
            entry["events"].append(event)
            if kind == "confirm":
                entry["review_stage"] = min(entry["review_stage"] + 1, len(REVIEW_LADDER) - 1)
                entry["next_review"] = (self.clock() + dt.timedelta(days=REVIEW_LADDER[entry["review_stage"]])).isoformat()
            return {"status": "OK", "id": entry["id"], "activity_score": activation(entry, self.clock()), "next_review": entry["next_review"]}
        return self.update(mutate)

    def pin(self, needle, value):
        def mutate(data):
            entry = self.find(data, needle)
            entry["pinned"] = value
            entry["pin_reason"] = "explicit_cli_selection" if value else None
            return {"status": "OK", "id": entry["id"], "pinned": value}
        return self.update(mutate)

    def audit(self):
        data = self.load().data
        stores = self.stores()
        active_hashes = {s: {source_hash(s, t) for t, _ in rows} for s, rows in stores.items()}
        result = {"status": "OK", "proposals_only": True, "date": self.clock().isoformat(),
                  "demote": [], "archive": [], "pinned_low_activity": [], "excluded": [],
                  "review_due": [], "ranking": [], "duplicates": [],
                  "source_characters": {s: len(read_bytes(self.mem_dir / s).decode("utf-8")) for s in STORES}}
        candidates = []
        for entry in data["entries"]:
            score, age = activation(entry, self.clock()), days_since(entry["created"], self.clock())
            row = {"id": entry["id"], "activity_score": score, "cost_class": entry["cost_class"]}
            if not self.eligible(entry):
                result["excluded"].append({**row, "reason": "status_or_validity"})
                continue
            if entry["tier"] == "T0":
                if entry["store"] not in active_hashes or entry.get("source_hash") not in active_hashes[entry["store"]]:
                    result["excluded"].append({**row, "reason": "source_changed_or_removed"})
                    continue
                result["ranking"].append(row)
                if score < DEMOTE_A and age > DEMOTE_AGE:
                    result["pinned_low_activity" if entry["pinned"] else "demote"].append(row)
            elif entry["tier"] == "T1":
                hits = [e["t"] for e in entry["events"] if e["type"] == "hit"]
                idle = days_since(max(hits) if hits else entry["created"], self.clock())
                if score < COLD_A and idle > COLD_IDLE and not entry["pinned"]:
                    result["archive"].append(row)
            if entry.get("next_review") and entry["next_review"] <= self.clock().isoformat():
                result["review_due"].append(entry["id"])
            candidates.append(entry)
        # Similarity is a review hint, never an automatic merge or a truth test.
        bounded = sorted(candidates, key=lambda e: e["id"])[:500]
        result["duplicate_scan_complete"] = len(candidates) <= len(bounded)
        for i, left in enumerate(bounded):
            for right in bounded[i + 1:]:
                if left["store"] != right["store"]:
                    continue
                ratio = difflib.SequenceMatcher(None, left["summary"], right["summary"]).ratio()
                if ratio > 0.55:
                    result["duplicates"].append({"score": ratio, "left": left["id"], "right": right["id"]})
        result["duplicates"].sort(key=lambda r: (-r["score"], r["left"], r["right"]))
        result["ranking"].sort(key=lambda r: (-r["activity_score"], r["id"]))
        result["demote"].sort(key=lambda r: (("low", "med", "high").index(r["cost_class"]), r["activity_score"], r["id"]))
        return result

    def manifest(self):
        self.load()  # Also enforce the memory-directory binding for read-only calls.
        warm = self.state_dir / "warm"
        if not warm.exists():
            return {"status": "MISSING_DIRECTORY", "files": []}
        files = []
        for path in sorted(warm.glob("*.md")):
            text = read_bytes(path).decode("utf-8")
            files.append({"name": path.name, "bytes": path.stat().st_size,
                          "title": next((line.strip() for line in text.splitlines() if line.strip()), "")[:100]})
        return {"status": "OK", "files": files}

    def migrate(self, legacy_path, apply=False):
        """Explicit v1 adoption. Original file and unknown metadata remain intact."""
        legacy_path = normal_path(legacy_path)
        raw = read_bytes(legacy_path)
        legacy = decode(raw)
        if not isinstance(legacy, dict) or legacy.get("version") != 1 or not isinstance(legacy.get("entries"), list):
            raise ThmError("EXPECTED_V1_INDEX")
        stores = self.stores()
        candidate = copy.deepcopy(legacy)
        candidate.update(version=2, revision=0, mem_dir=str(self.mem_dir),
                         migration={"source_sha256": digest(raw), "date": self.clock().isoformat()})
        unresolved = []
        for entry in candidate["entries"]:
            if not isinstance(entry, dict):
                raise ThmError("INVALID_LEGACY_ENTRY")
            store, key = entry.get("store"), entry.get("key")
            if not isinstance(key, str) or not key:
                raise ThmError("INVALID_LEGACY_KEY")
            matches = []
            for text, _ in stores.get(store, []):
                old_text = " ".join(line.strip() for line in text.splitlines() if line.strip())
                if key == old_text[:24] and entry.get("summary") == old_text[:60]:
                    matches.append(text)
            entry["source_hash"] = source_hash(store, matches[0]) if len(matches) == 1 else None
            entry["status"] = "active" if len(matches) == 1 else "unresolved_legacy"
            if entry["status"] != "active":
                unresolved.append(entry.get("id"))
            # Preserve old high-cost immunity until the user explicitly unpins it.
            entry["pinned"] = entry.get("pinned", entry.get("cost_class") == "high")
            if entry["pinned"]:
                entry.setdefault("pin_reason", "legacy_protection_requires_review")
            for ordinal, event in enumerate(entry.get("events", [])):
                event.setdefault("event_id", f"legacy:{entry.get('id')}:{ordinal}")
                if event.get("type") == "confirm" and not event.get("evidence"):
                    event["legacy_unverified"] = True
        self.validate(candidate)
        report = {"status": "PREVIEW", "source_sha256": digest(raw), "entries": len(candidate["entries"]),
                  "unresolved_ids": unresolved, "policy_changes": ["movement_weight_zero", "unverified_confirmation_weight_zero", "legacy_high_protection_preserved"]}
        if apply:
            with index_lock(self.state_dir / "index.lock"):
                if self.index.exists():
                    raise ThmError("MIGRATION_TARGET_EXISTS")
                if read_bytes(legacy_path) != raw:
                    raise ThmError("LEGACY_SOURCE_CHANGED")
                backup = self.state_dir / "legacy-index.backup.json"
                if backup.exists() and read_bytes(backup) != raw:
                    raise ThmError("MIGRATION_BACKUP_CONFLICT")
                atomic_write(backup, raw)
                if read_bytes(backup) != raw:
                    raise ThmError("MIGRATION_BACKUP_READBACK_FAILED")
                self._save_locked(Snapshot(candidate, None))
            report["status"] = "APPLIED"
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--mem-dir")
    parser.add_argument("--state-dir")
    parser.add_argument("--config")
    commands = parser.add_subparsers(dest="command")
    for name in ("seed", "audit", "manifest"):
        commands.add_parser(name)
    hit = commands.add_parser("hit")
    hit.add_argument("selector")
    hit.add_argument("note", nargs="*", default=[])
    hit.add_argument("--event-id")
    confirm = commands.add_parser("confirm")
    confirm.add_argument("selector")
    confirm.add_argument("--event-id")
    confirm.add_argument("--evidence", required=True)
    register = commands.add_parser("register")
    register.add_argument("store", choices=STORES)
    register.add_argument("selector")
    register.add_argument("cost", choices=("high", "med", "low"))
    register.add_argument("--pin", action="store_true")
    for name in ("pin", "unpin"):
        commands.add_parser(name).add_argument("selector")
    migration = commands.add_parser("migrate")
    migration.add_argument("legacy_index")
    migration.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        mem, state = config_paths(args.mem_dir, args.state_dir, args.config)
        engine = Engine(mem, state)
        if args.command != "migrate" and not engine.index.exists() and (BASE / "index.json").exists():
            raise ThmError("REPOSITORY_LEGACY_INDEX_FOUND: use explicit migrate; no automatic adoption")
        if args.command in ("seed", "audit", "manifest"):
            result = getattr(engine, args.command)()
        elif args.command == "register":
            result = engine.register(args.store, args.selector, args.cost, args.pin)
        elif args.command == "hit":
            result = engine.feedback("hit", args.selector, " ".join(args.note), args.event_id)
        elif args.command == "confirm":
            result = engine.feedback("confirm", args.selector, event_id=args.event_id, evidence=args.evidence)
        elif args.command in ("pin", "unpin"):
            result = engine.pin(args.selector, args.command == "pin")
        else:
            result = engine.migrate(args.legacy_index, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ThmError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
