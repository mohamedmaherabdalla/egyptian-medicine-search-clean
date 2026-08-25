"""Capture and validate source provenance for Algorithm 6 evaluations.

The legacy ``source_commit_expected`` field identifies an intended historical
revision, but it does not describe the files that Python actually imports from
a dirty worktree.  This module records both Git state and SHA-256 digests of
every source that can materially affect a rule-evaluation run.

The returned mapping is JSON-serializable.  It deliberately stores repository-
relative paths only; manifests therefore remain portable and do not disclose a
developer's absolute checkout path.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROVENANCE_SCHEMA_VERSION = 1

# These are the seven executable/data inputs whose exact bytes define an
# Algorithm 6 rule-evaluation run.  Callers may override paths for testing, but
# all seven logical keys remain mandatory.
DEFAULT_FILE_PATHS: dict[str, Path] = {
    "algorithm_5": Path(
        "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py"
    ),
    "algorithm_6": Path(
        "benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py"
    ),
    "product_reranker": Path("app/product_context_reranker.py"),
    "api": Path("app/api.py"),
    "catalog": Path("app/data/catalog.json"),
    "evaluator": Path(
        "algorithm_6_rule_evaluation/evaluators/evaluate_rule_test_sets.py"
    ),
    "generator": Path(
        "algorithm_6_rule_evaluation/generators/generate_rule_test_sets.py"
    ),
}
REQUIRED_FILE_KEYS = tuple(DEFAULT_FILE_PATHS)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ProvenanceError(RuntimeError):
    """Base exception for provenance collection and checking failures."""


class ProvenanceValidationError(ProvenanceError):
    """Raised when a provenance record is incomplete or malformed."""


class ProvenanceMismatchError(ProvenanceError):
    """Raised when a recorded snapshot differs from the current worktree."""


def sha256_path(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_bytes(repo: Path, arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        command = "git " + " ".join(arguments)
        raise ProvenanceError(f"{command} failed: {detail or 'unknown Git error'}")
    return completed.stdout


def _git_text(repo: Path, *arguments: str) -> str:
    return _git_bytes(repo, arguments).decode("utf-8", errors="strict").strip()


def _repository_root(path: Path) -> Path:
    requested = path.expanduser().resolve()
    root_text = _git_text(requested, "rev-parse", "--show-toplevel")
    return Path(root_text).resolve()


def _resolve_file(repo: Path, supplied_path: str | Path) -> tuple[Path, str]:
    candidate = Path(supplied_path)
    absolute = candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()
    try:
        relative = absolute.relative_to(repo)
    except ValueError as exc:
        raise ProvenanceError(
            f"provenance input is outside the repository: {supplied_path}"
        ) from exc
    if not absolute.is_file():
        raise ProvenanceError(f"provenance input is not a file: {relative.as_posix()}")
    return absolute, relative.as_posix()


def collect_provenance(
    repo: str | Path,
    *,
    file_paths: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Capture Git state and exact hashes of all required evaluation inputs.

    ``repo`` may be the repository root or any directory inside the worktree.
    ``file_paths`` exists primarily for isolated tests and future path moves;
    it must retain every key in :data:`REQUIRED_FILE_KEYS`.
    """

    root = _repository_root(Path(repo))
    selected_paths: Mapping[str, str | Path] = (
        DEFAULT_FILE_PATHS if file_paths is None else file_paths
    )
    missing = [key for key in REQUIRED_FILE_KEYS if key not in selected_paths]
    if missing:
        raise ProvenanceError(
            "missing required provenance file path(s): " + ", ".join(missing)
        )

    head = _git_text(root, "rev-parse", "--verify", "HEAD")
    # NUL-delimited porcelain is stable and unambiguous even for unusual file
    # names.  We hash it instead of embedding local file names in artifacts.
    status = _git_bytes(
        root,
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
    )

    files: dict[str, dict[str, Any]] = {}
    for key in REQUIRED_FILE_KEYS:
        absolute, relative = _resolve_file(root, selected_paths[key])
        files[key] = {
            "path": relative,
            "sha256": sha256_path(absolute),
            "bytes": absolute.stat().st_size,
        }

    record: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": {
            # A Git object ID is intentionally recorded as an object ID.  It is
            # normally 40 hex characters (SHA-1) and may be 64 in SHA-256 repos.
            "head": head,
            "dirty": bool(status),
            "status_porcelain_v1_sha256": hashlib.sha256(status).hexdigest(),
            "status_bytes": len(status),
        },
        "files": files,
    }
    validate_provenance(record)
    return record


def validate_provenance(record: Mapping[str, Any]) -> None:
    """Validate the structure and digest syntax of a provenance record."""

    errors: list[str] = []
    if record.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {PROVENANCE_SCHEMA_VERSION}"
        )

    captured_at = record.get("captured_at_utc")
    if not isinstance(captured_at, str):
        errors.append("captured_at_utc must be an ISO-8601 string")
    else:
        try:
            parsed = datetime.fromisoformat(captured_at)
            if parsed.tzinfo is None:
                errors.append("captured_at_utc must include a timezone")
        except ValueError:
            errors.append("captured_at_utc must be a valid ISO-8601 timestamp")

    git = record.get("git")
    if not isinstance(git, Mapping):
        errors.append("git must be an object")
    else:
        head = git.get("head")
        if not isinstance(head, str) or not _GIT_OBJECT_ID_RE.fullmatch(head):
            errors.append("git.head must be a 40- or 64-character lowercase hex object ID")
        if type(git.get("dirty")) is not bool:
            errors.append("git.dirty must be a boolean")
        status_hash = git.get("status_porcelain_v1_sha256")
        if not isinstance(status_hash, str) or not _SHA256_RE.fullmatch(status_hash):
            errors.append("git.status_porcelain_v1_sha256 must be a SHA-256 digest")
        status_bytes = git.get("status_bytes")
        if type(status_bytes) is not int or status_bytes < 0:
            errors.append("git.status_bytes must be a non-negative integer")

    files = record.get("files")
    if not isinstance(files, Mapping):
        errors.append("files must be an object")
    else:
        for key in REQUIRED_FILE_KEYS:
            file_record = files.get(key)
            if not isinstance(file_record, Mapping):
                errors.append(f"files.{key} must be an object")
                continue
            path = file_record.get("path")
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                errors.append(f"files.{key}.path must be repository-relative")
            digest = file_record.get("sha256")
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                errors.append(f"files.{key}.sha256 must be a SHA-256 digest")
            byte_count = file_record.get("bytes")
            if type(byte_count) is not int or byte_count < 0:
                errors.append(f"files.{key}.bytes must be a non-negative integer")

    if errors:
        raise ProvenanceValidationError("; ".join(errors))


def verify_provenance_against_worktree(
    record: Mapping[str, Any],
    repo: str | Path,
    *,
    file_paths: Mapping[str, str | Path] | None = None,
) -> None:
    """Raise if a valid record does not describe the current worktree exactly."""

    validate_provenance(record)
    current = collect_provenance(repo, file_paths=file_paths)
    mismatches: list[str] = []

    recorded_git = record["git"]
    current_git = current["git"]
    for key in ("head", "dirty", "status_porcelain_v1_sha256", "status_bytes"):
        if recorded_git[key] != current_git[key]:
            mismatches.append(f"git.{key}")

    recorded_files = record["files"]
    current_files = current["files"]
    for key in REQUIRED_FILE_KEYS:
        for field in ("path", "sha256", "bytes"):
            if recorded_files[key][field] != current_files[key][field]:
                mismatches.append(f"files.{key}.{field}")

    if mismatches:
        raise ProvenanceMismatchError(
            "provenance differs from the current worktree: " + ", ".join(mismatches)
        )
