#!/usr/bin/env python3
"""Download the declared public Roboflow prescription datasets with a size guard."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "05_roboflow_sources"
MANIFEST_PATH = DATA_DIR / "datasets.csv"
RAW_DIR = DATA_DIR / "raw"
REPORT_PATH = DATA_DIR / "download_report.csv"
API_ROOT = "https://api.roboflow.com"
DEFAULT_LIMIT_BYTES = 10 * 1024**3
POLL_SECONDS = 5
POLL_ATTEMPTS = 60


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    workspace: str
    project_slug: str
    version: str
    export_format: str

    @property
    def api_path(self) -> str:
        values = (
            self.workspace,
            self.project_slug,
            self.version,
            self.export_format,
        )
        return "/".join(urllib.parse.quote(value, safe="") for value in values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--estimate", action="store_true")
    action.add_argument("--download", action="store_true")
    parser.add_argument(
        "--limit-gb",
        type=float,
        default=10.0,
        help="maximum combined ZIP size before download refusal (default: 10)",
    )
    parser.add_argument("--allow-over-limit", action="store_true")
    return parser.parse_args()


def load_manifest() -> list[Dataset]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        Dataset(
            dataset_id=row["dataset_id"],
            workspace=row["workspace"],
            project_slug=row["project_slug"],
            version=row["version"],
            export_format=row["export_format"],
        )
        for row in rows
        if row["status"] in {"ready", "optional", "review_only"}
    ]


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "medicine-search-clean/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Roboflow request failed ({error.code}): {body}") from error


def find_download_url(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload if payload.startswith(("http://", "https://")) else None
    if isinstance(payload, list):
        for item in payload:
            found = find_download_url(item)
            if found:
                return found
        return None
    if isinstance(payload, dict):
        for key in ("link", "download", "download_url", "url"):
            found = find_download_url(payload.get(key))
            if found:
                return found
        for value in payload.values():
            found = find_download_url(value)
            if found:
                return found
    return None


def get_export_url(dataset: Dataset, api_key: str) -> str:
    query = urllib.parse.urlencode({"api_key": api_key})
    endpoint = f"{API_ROOT}/{dataset.api_path}?{query}"
    last_payload: dict[str, Any] = {}
    for _ in range(POLL_ATTEMPTS):
        last_payload = request_json(endpoint)
        download_url = find_download_url(last_payload)
        if download_url:
            return download_url
        time.sleep(POLL_SECONDS)
    raise RuntimeError(
        f"{dataset.dataset_id}: export did not become ready: {last_payload}"
    )


def remote_size(url: str) -> int:
    head = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "medicine-search-clean/1"},
    )
    try:
        with urllib.request.urlopen(head, timeout=60) as response:
            length = response.headers.get("Content-Length")
            if length:
                return int(length)
    except urllib.error.HTTPError:
        pass

    probe = urllib.request.Request(
        url,
        headers={"Range": "bytes=0-0", "User-Agent": "medicine-search-clean/1"},
    )
    with urllib.request.urlopen(probe, timeout=60) as response:
        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            return int(content_range.rsplit("/", 1)[1])
        length = response.headers.get("Content-Length")
        if length:
            return int(length)
    raise RuntimeError("server did not report archive size")


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "medicine-search-clean/1"})
    temporary = destination.with_suffix(destination.suffix + ".partial")
    with urllib.request.urlopen(request, timeout=300) as response:
        with temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
    temporary.replace(destination)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_archive(archive: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)


def write_report(rows: list[dict[str, str]]) -> None:
    fields = [
        "dataset_id",
        "archive_bytes",
        "archive_gb",
        "sha256",
        "archive_path",
        "extracted_path",
        "status",
    ]
    with REPORT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print(
            "ROBOFLOW_API_KEY is not set. Create a free Roboflow key and export "
            "it in the shell before running this command.",
            file=sys.stderr,
        )
        return 2

    datasets = load_manifest()
    exports: list[tuple[Dataset, str, int]] = []
    for dataset in datasets:
        url = get_export_url(dataset, api_key)
        size = remote_size(url)
        exports.append((dataset, url, size))
        print(f"{dataset.dataset_id}: {size / 1024**2:.2f} MB")

    total = sum(size for _, _, size in exports)
    limit = int(args.limit_gb * 1024**3)
    print(f"Combined ZIP size: {total / 1024**3:.3f} GB")
    if args.estimate:
        return 0
    if total > limit and not args.allow_over_limit:
        print(
            f"Refusing download: {total / 1024**3:.3f} GB exceeds "
            f"{args.limit_gb:.3f} GB.",
            file=sys.stderr,
        )
        return 3

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, str]] = []
    for dataset, url, expected_size in exports:
        dataset_dir = RAW_DIR / dataset.dataset_id
        archive = dataset_dir / "dataset.zip"
        extracted = dataset_dir / "extracted"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        download_file(url, archive)
        actual_size = archive.stat().st_size
        if actual_size != expected_size:
            raise RuntimeError(
                f"{dataset.dataset_id}: expected {expected_size} bytes, "
                f"downloaded {actual_size}"
            )
        extract_archive(archive, extracted)
        report.append(
            {
                "dataset_id": dataset.dataset_id,
                "archive_bytes": str(actual_size),
                "archive_gb": f"{actual_size / 1024**3:.6f}",
                "sha256": sha256(archive),
                "archive_path": str(archive.relative_to(DATA_DIR)),
                "extracted_path": str(extracted.relative_to(DATA_DIR)),
                "status": "downloaded_and_extracted",
            }
        )
        write_report(report)
        print(f"{dataset.dataset_id}: downloaded and extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
