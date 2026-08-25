#!/usr/bin/env python3
"""Unit tests for the standalone Algorithm 6 provenance helper."""

from __future__ import annotations

import copy
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from provenance import (  # noqa: E402
    DEFAULT_FILE_PATHS,
    REQUIRED_FILE_KEYS,
    ProvenanceMismatchError,
    ProvenanceValidationError,
    collect_provenance,
    validate_provenance,
    verify_provenance_against_worktree,
)


class ProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self._git("init", "--quiet")
        self._git("config", "user.email", "provenance-test@example.invalid")
        self._git("config", "user.name", "Provenance Test")

        for index, relative_path in enumerate(DEFAULT_FILE_PATHS.values(), start=1):
            path = self.repo / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture-{index}\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "--quiet", "-m", "fixture")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return completed.stdout.strip()

    def test_collects_all_required_hashes_head_and_clean_status(self) -> None:
        record = collect_provenance(self.repo)

        self.assertEqual(set(record["files"]), set(REQUIRED_FILE_KEYS))
        self.assertEqual(record["git"]["head"], self._git("rev-parse", "HEAD"))
        self.assertIs(record["git"]["dirty"], False)
        self.assertEqual(record["git"]["status_bytes"], 0)
        self.assertEqual(
            record["git"]["status_porcelain_v1_sha256"],
            hashlib.sha256(b"").hexdigest(),
        )

        for key, relative_path in DEFAULT_FILE_PATHS.items():
            payload = (self.repo / relative_path).read_bytes()
            self.assertEqual(record["files"][key]["path"], relative_path.as_posix())
            self.assertEqual(
                record["files"][key]["sha256"],
                hashlib.sha256(payload).hexdigest(),
            )
            self.assertEqual(record["files"][key]["bytes"], len(payload))

        validate_provenance(record)
        verify_provenance_against_worktree(record, self.repo)

    def test_dirty_state_and_modified_source_are_captured(self) -> None:
        algorithm_6 = self.repo / DEFAULT_FILE_PATHS["algorithm_6"]
        algorithm_6.write_text("changed-runtime-bytes\n", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new\n", encoding="utf-8")

        record = collect_provenance(self.repo)

        self.assertIs(record["git"]["dirty"], True)
        self.assertGreater(record["git"]["status_bytes"], 0)
        self.assertEqual(
            record["files"]["algorithm_6"]["sha256"],
            hashlib.sha256(algorithm_6.read_bytes()).hexdigest(),
        )

    def test_validation_rejects_missing_or_malformed_hashes(self) -> None:
        record = collect_provenance(self.repo)
        malformed = copy.deepcopy(record)
        malformed["files"]["api"]["sha256"] = "not-a-sha256"

        with self.assertRaisesRegex(
            ProvenanceValidationError, r"files\.api\.sha256"
        ):
            validate_provenance(malformed)

        missing = copy.deepcopy(record)
        del missing["files"]["generator"]
        with self.assertRaisesRegex(
            ProvenanceValidationError, r"files\.generator"
        ):
            validate_provenance(missing)

    def test_verification_detects_a_post_capture_change(self) -> None:
        record = collect_provenance(self.repo)
        api_path = self.repo / DEFAULT_FILE_PATHS["api"]
        api_path.write_text("changed-after-snapshot\n", encoding="utf-8")

        with self.assertRaisesRegex(
            ProvenanceMismatchError, r"files\.api\.sha256"
        ):
            verify_provenance_against_worktree(record, self.repo)


if __name__ == "__main__":
    unittest.main()
