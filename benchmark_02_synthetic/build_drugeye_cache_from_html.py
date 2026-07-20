#!/usr/bin/env python3
"""Build a DrugEye evaluator JSONL cache from fetched HTML files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


DATASET_DIR = Path(__file__).resolve().parent
EVALUATOR_PATH = DATASET_DIR / "evaluate_drugeye.py"


def load_evaluator() -> Any:
    spec = importlib.util.spec_from_file_location("evaluate_drugeye", EVALUATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {EVALUATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert DrugEye HTML files to evaluator JSONL cache.")
    parser.add_argument("--mode", default="trade")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--html-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--include-missing", action="store_true")
    return parser.parse_args()


def result_payload(module: Any, result: Any) -> dict[str, Any]:
    return {
        "name": result.name,
        "price": result.price,
        "ingredients": result.ingredients,
        "drug_class": result.drug_class,
        "company": result.company,
        "actions": {name: asdict(action) for name, action in result.actions.items()},
    }


def main() -> int:
    args = parse_args()
    module = load_evaluator()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    missing = 0
    with args.queries.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as out:
        for line in source:
            if args.limit and written >= args.limit:
                break
            line = line.rstrip("\n")
            if not line:
                continue
            query_id, query = line.split("\t", 1)
            html_path = args.html_dir / f"{args.mode}_{query_id}.html"
            key = module.cache_key(args.mode, query)
            if not html_path.exists():
                missing += 1
                if not args.include_missing:
                    continue
                item = {
                    "key": key,
                    "mode": args.mode,
                    "query": query,
                    "helper_text": "",
                    "error": "missing_html_cache",
                    "results": [],
                }
            else:
                html_text = html_path.read_text(encoding="utf-8", errors="replace")
                results, helper_text = module.parse_results(html_text)
                item = {
                    "key": key,
                    "mode": args.mode,
                    "query": query,
                    "helper_text": helper_text,
                    "error": "",
                    "results": [result_payload(module, result) for result in results[: module.TOP_K_RESULTS]],
                }
            out.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            written += 1
    print(f"wrote {written} cache entries to {args.output}; missing_html={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
