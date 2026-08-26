#!/usr/bin/env python3
"""Benchmark the public DrugEye website on testing dataset v2.

Problem: evaluate DrugEye's live ASP.NET search page against the same V2
commercial-name benchmark used for the local algorithms.
Inputs:
    - benchmark_02_synthetic/data/test_cases.csv
    - the public DrugEye Web Forms page
Outputs:
    - row-level DrugEye results under benchmark_02_synthetic/results
    - scope/category/error-type aggregate metrics
    - a compact Markdown benchmark report
Edge cases:
    - The site has no explicit confidence/clarification signal.
    - The site returns product rows, while the benchmark expects commercial
      families. Prefix matching is therefore used for relevance.
    - Network failures are recorded per row instead of aborting the full run.
Failure modes:
    - The site may throttle, change HTML, or become unreachable. The evaluator
      uses a JSONL cache so repeated runs reuse successful prior responses.
Algorithm choice:
    - The evaluator uses the site's own search endpoint, not local catalog data.
      It only normalizes returned product names for relevance scoring.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import evaluate_current_app_search as current_eval


LOGGER = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).resolve().parent
DATASET_PATH = DATASET_DIR / "data" / "test_cases.csv"
CATEGORY_SUMMARY_PATH = DATASET_DIR / "data" / "category_summary.csv"
RESULTS_DIR = DATASET_DIR / "artifacts" / "04_drugeye"

BASE_URL = "http://www.drugeye.pharorg.com/drugeyeapp/android-search/drugeye-android-live-go.aspx"
TOP_K_RESULTS = 20
NO_MATCH_EXPECTED = "__NO_MATCH__"
AMBIGUOUS_EXPECTED = "__AMBIGUOUS__"

SEARCH_MODES = {
    "trade": ("b1", "search"),
    "fuzzy": ("BtnSearchEx", "Ex"),
    "ingredient": ("BG", "G"),
    "price": ("BP", "P"),
    "pharmacology": ("Button1", "PH"),
}


@dataclass
class ResultAction:
    label: str
    drug_id: str


@dataclass
class DrugEyeResult:
    name: str
    price: str
    ingredients: str
    drug_class: str
    company: str
    actions: dict[str, ResultAction]


class InputParser(HTMLParser):
    """Extract ASP.NET hidden inputs from the initial page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        name = values.get("name")
        if name:
            self.inputs[name] = values.get("value", "")


class DrugEyeResultParser(HTMLParser):
    """Parse DrugEye's nested result table into product rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[DrugEyeResult] = []
        self.helper_text = ""

        self._table_depth = 0
        self._my_table_depth: int | None = None
        self._in_direct_result_row = False
        self._in_direct_result_cell = False
        self._current_cell: list[str] = []
        self._current_row: list[str] = []
        self._outer_rows: list[list[str]] = []
        self._current_result_index = -1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}

        if tag == "table":
            self._table_depth += 1
            if values.get("id") == "MyTable":
                self._my_table_depth = self._table_depth
            return

        if tag == "input":
            if values.get("id") == "TttHelper":
                self.helper_text = clean_text(values.get("value", ""))
            return

        if self._my_table_depth is None:
            return

        if tag == "tr" and self._table_depth == self._my_table_depth:
            self._in_direct_result_row = True
            self._current_row = []
            return

        if tag == "td" and self._in_direct_result_row and self._table_depth == self._my_table_depth:
            self._in_direct_result_cell = True
            self._current_cell = []
            return

        if tag == "td":
            classes = set(values.get("class", "").split())
            if classes.intersection({"geno", "alto", "moro", "imigo"}):
                self._add_action(classes, values.get("title", ""))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "td" and self._in_direct_result_cell:
            self._current_row.append(clean_text(" ".join(self._current_cell)))
            self._current_cell = []
            self._in_direct_result_cell = False
            return

        if tag == "tr" and self._in_direct_result_row:
            self._outer_rows.append(self._current_row)
            self._consume_complete_result()
            self._current_row = []
            self._in_direct_result_row = False
            return

        if tag == "table":
            if self._my_table_depth == self._table_depth:
                self._my_table_depth = None
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_direct_result_cell:
            self._current_cell.append(data)

    def _consume_complete_result(self) -> None:
        while len(self._outer_rows) >= 4:
            first, second, third, fourth = self._outer_rows[:4]
            if len(first) < 2:
                self._outer_rows.pop(0)
                continue
            result = DrugEyeResult(
                name=first[0],
                price=first[1],
                ingredients=second[0] if second else "",
                drug_class=third[0] if third else "",
                company=fourth[0] if fourth else "",
                actions={},
            )
            self.results.append(result)
            self._current_result_index = len(self.results) - 1
            del self._outer_rows[:4]
            if self._outer_rows and is_action_row(self._outer_rows[0]):
                self._outer_rows.pop(0)

    def _add_action(self, classes: set[str], title: str) -> None:
        if self._current_result_index < 0:
            return
        action_name = ""
        if "geno" in classes:
            action_name = "similars"
        elif "alto" in classes:
            action_name = "alternatives"
        elif "moro" in classes:
            action_name = "more"
        elif "imigo" in classes:
            action_name = "images"
        if action_name:
            self.results[self._current_result_index].actions[action_name] = ResultAction(
                label=action_name,
                drug_id=clean_text(title),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark DrugEye against testing dataset v2.")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit. Zero means all rows.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many dataset rows before evaluating.")
    parser.add_argument("--mode", choices=sorted(SEARCH_MODES), default="trade", help="DrugEye mode to benchmark.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--sleep", type=float, default=0.25, help="Sleep after each live website request.")
    parser.add_argument("--cache", type=Path, default=None, help="JSONL cache path. Defaults under results/.")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH, help="Dataset CSV to evaluate.")
    parser.add_argument("--output-prefix", default="", help="Optional output filename prefix.")
    parser.add_argument("--no-network", action="store_true", help="Use only cached responses; do not query DrugEye.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    args = parse_args()
    if args.limit < 0:
        raise ValueError("--limit must be >= 0")
    if args.offset < 0:
        raise ValueError("--offset must be >= 0")
    if args.sleep < 0:
        raise ValueError("--sleep must be >= 0")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = args.cache or RESULTS_DIR / f"v2_drugeye_{args.mode}_cache.jsonl"
    cache = load_cache(cache_path)
    cases = read_cases(args.dataset, args.limit, args.offset)
    LOGGER.info("loaded cases=%d mode=%s cache_entries=%d", len(cases), args.mode, len(cache))

    started = time.time()
    rows: list[dict[str, Any]] = []
    live_requests = 0
    for index, case in enumerate(cases, 1):
        row, requested = evaluate_case(case, args, cache, cache_path)
        rows.append(row)
        live_requests += int(requested)
        if index % 100 == 0 or index == len(cases):
            LOGGER.info("processed=%d live_requests=%d elapsed_s=%.1f", index, live_requests, time.time() - started)

    output_prefix = args.output_prefix or f"v2_drugeye_{args.mode}"
    all_results_path = RESULTS_DIR / f"{output_prefix}_all_test_results.csv"
    metrics_category_path = RESULTS_DIR / f"{output_prefix}_metrics_by_scope_category.csv"
    metrics_error_path = RESULTS_DIR / f"{output_prefix}_metrics_by_scope_category_error_type.csv"
    failure_path = RESULTS_DIR / f"{output_prefix}_failure_samples.csv"
    report_path = RESULTS_DIR / f"{output_prefix}_benchmark_report.md"
    summary_path = RESULTS_DIR / f"{output_prefix}_benchmark_summary.json"

    category_metrics = metric_rows_by_scope_category(rows)
    error_metrics = metric_rows_by_error_type(rows)
    failures = failure_samples(rows)
    elapsed_seconds = time.time() - started

    write_csv(all_results_path, rows)
    write_csv(metrics_category_path, category_metrics)
    write_csv(metrics_error_path, error_metrics)
    write_csv(failure_path, failures)
    write_report(report_path, category_metrics, error_metrics, elapsed_seconds, len(cases), args, live_requests)
    write_summary(summary_path, elapsed_seconds, len(cases), args, live_requests, cache_path)

    LOGGER.info("wrote report: %s", report_path)
    return 0


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_action_row(row: list[str]) -> bool:
    text = " ".join(row).lower()
    return all(word in text for word in ("similars", "alternatives", "more", "images"))


def parse_inputs(page_html: str) -> dict[str, str]:
    parser = InputParser()
    parser.feed(page_html)
    return parser.inputs


def parse_results(page_html: str) -> tuple[list[DrugEyeResult], str]:
    parser = DrugEyeResultParser()
    parser.feed(page_html)
    return parser.results, parser.helper_text


def request_text(
    opener: urllib.request.OpenerDirector,
    url: str,
    data: bytes | None = None,
    timeout: float = 20,
) -> str:
    request = urllib.request.Request(url, data=data)
    with opener.open(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def build_opener() -> urllib.request.OpenerDirector:
    cookie_jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (compatible; V2DrugEyeBenchmark/1.0)"),
        ("Accept", "text/html,application/xhtml+xml"),
    ]
    return opener


def search_drugeye(query: str, mode: str, limit: int, timeout: float) -> tuple[list[DrugEyeResult], str]:
    opener = build_opener()
    initial_html = request_text(opener, BASE_URL, timeout=timeout)
    inputs = parse_inputs(initial_html)
    button_name, button_value = SEARCH_MODES[mode]
    payload = {
        "__VIEWSTATE": inputs.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": inputs.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": inputs.get("__EVENTVALIDATION", ""),
        "ttt": query,
        button_name: button_value,
        "Passgenericname": "",
    }
    body = urllib.parse.urlencode(payload).encode("utf-8")
    html_text = request_text(opener, BASE_URL, data=body, timeout=timeout)
    results, helper_text = parse_results(html_text)
    return results[:limit], helper_text


def cache_key(mode: str, query: str) -> str:
    return f"{mode}\t{query}"


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            key = str(item.get("key") or "")
            if key:
                out[key] = item
    return out


def append_cache(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def result_to_payload(result: DrugEyeResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "price": result.price,
        "ingredients": result.ingredients,
        "drug_class": result.drug_class,
        "company": result.company,
        "actions": {name: asdict(action) for name, action in result.actions.items()},
    }


def payload_to_result(payload: dict[str, Any]) -> DrugEyeResult:
    return DrugEyeResult(
        name=str(payload.get("name") or ""),
        price=str(payload.get("price") or ""),
        ingredients=str(payload.get("ingredients") or ""),
        drug_class=str(payload.get("drug_class") or ""),
        company=str(payload.get("company") or ""),
        actions={
            name: ResultAction(label=str(action.get("label") or name), drug_id=str(action.get("drug_id") or ""))
            for name, action in dict(payload.get("actions") or {}).items()
        },
    )


def cached_or_live_response(
    query: str,
    args: argparse.Namespace,
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
) -> tuple[list[DrugEyeResult], str, str, bool]:
    key = cache_key(args.mode, query)
    cached = cache.get(key)
    if cached is not None:
        results = [payload_to_result(item) for item in cached.get("results", [])]
        return results, str(cached.get("helper_text") or ""), str(cached.get("error") or ""), False
    if args.no_network:
        return [], "", "cache_miss_no_network", False

    try:
        results, helper_text = search_drugeye(query, args.mode, TOP_K_RESULTS, args.timeout)
        item = {
            "key": key,
            "mode": args.mode,
            "query": query,
            "helper_text": helper_text,
            "error": "",
            "results": [result_to_payload(result) for result in results],
        }
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        results = []
        helper_text = ""
        item = {
            "key": key,
            "mode": args.mode,
            "query": query,
            "helper_text": "",
            "error": type(exc).__name__ + ": " + str(exc),
            "results": [],
        }
    cache[key] = item
    append_cache(cache_path, item)
    if args.sleep:
        time.sleep(args.sleep)
    return results, helper_text, str(item.get("error") or ""), True


def read_cases(dataset_path: Path, limit: int, offset: int) -> list[dict[str, Any]]:
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "input", "expected", "category", "error_type", "difficulty", "danger",
            "scope", "expected_behavior", "collision_with", "source_base_group",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{dataset_path} missing required columns: {', '.join(sorted(missing))}")
        cases: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, 1):
            if row_number <= offset:
                continue
            source_row = int(row.get("source_row") or row_number)
            cases.append({
                "source_row": source_row,
                "input": row["input"],
                "expected": row["expected"],
                "category": row["category"],
                "error_type": row["error_type"],
                "difficulty": row["difficulty"],
                "danger": row["danger"],
                "scope": row["scope"],
                "expected_behavior": row["expected_behavior"],
                "collision_with": row["collision_with"],
                "source_base_group": row["source_base_group"],
            })
            if limit and len(cases) >= limit:
                break
    return cases


def evaluate_case(
    case: dict[str, Any],
    args: argparse.Namespace,
    cache: dict[str, dict[str, Any]],
    cache_path: Path,
) -> tuple[dict[str, Any], bool]:
    results, helper_text, error, requested = cached_or_live_response(case["input"], args, cache, cache_path)
    targets = targets_for_case(case)
    rel_total = relevant_total_for_targets(targets)
    relevances = [drugeye_relevance(item, targets) for item in results]
    first_rank, ap20, ndcg20 = ranking_metrics(relevances, case, bool(results), rel_total)
    behavior_success = behavior_success_for_case(case, first_rank, bool(results))
    top1 = results[0] if results else None
    top1_rel = relevances[0] if relevances else 0
    top5_names = "|".join(result.name for result in results[:5])
    return {
        "algorithm": f"drugeye_{args.mode}",
        "scope": case["scope"],
        "source_row": case["source_row"],
        "category": case["category"],
        "error_type": case["error_type"],
        "difficulty": case["difficulty"],
        "danger": case["danger"],
        "expected_behavior": case["expected_behavior"],
        "input": case["input"],
        "expected": case["expected"],
        "first_rank": first_rank,
        "hit_at_1": int(first_rank <= 1),
        "hit_at_5": int(first_rank <= 5),
        "hit_at_10": int(first_rank <= 10),
        "hit_at_20": int(first_rank <= 20),
        "ap20": ap20,
        "ndcg20": ndcg20,
        "result_count": len(results),
        "candidate_pool": len(results),
        "top1_base": top1.name if top1 else "",
        "top1_product": top1.name if top1 else "",
        "top1_score": "",
        "top1_relevance": top1_rel,
        "top1_status": "ranked_list" if top1 else "no_result",
        "top1_signals": helper_text,
        "top5_bases": top5_names,
        "unsafe_confident_top1": 0,
        "missing_clarification": 0,
        "behavior_success": int(behavior_success),
        "network_error": error,
    }, requested


def targets_for_case(case: dict[str, Any]) -> list[tuple[str, str]]:
    if case["expected_behavior"] == "match":
        return current_eval.parse_expected_targets(case["expected"])
    if case["expected_behavior"] == "ambiguous":
        names = [case.get("source_base_group", "")]
        names.extend(part.strip() for part in str(case.get("collision_with", "")).split(";") if part.strip())
        targets = [(current_eval.normalize_search(name), current_eval.compact_key(name)) for name in names if name]
        return list(dict.fromkeys(targets)) or [(AMBIGUOUS_EXPECTED, AMBIGUOUS_EXPECTED)]
    return [(NO_MATCH_EXPECTED, NO_MATCH_EXPECTED)]


def relevant_total_for_targets(targets: list[tuple[str, str]]) -> int:
    real_targets = {
        compact
        for _, compact in targets
        if compact and compact not in {NO_MATCH_EXPECTED, AMBIGUOUS_EXPECTED}
    }
    return max(1, len(real_targets))


def normalized_result_values(result: DrugEyeResult) -> set[tuple[str, str]]:
    values = [
        result.name,
        result.actions.get("images", ResultAction("", "")).drug_id,
        result.actions.get("more", ResultAction("", "")).drug_id,
    ]
    out = set()
    for value in values:
        norm = current_eval.normalize_search(value)
        compact = current_eval.compact_key(value)
        if norm or compact:
            out.add((norm, compact))
    return out


def drugeye_relevance(result: DrugEyeResult, targets: list[tuple[str, str]]) -> int:
    values = normalized_result_values(result)
    for target_norm, target_compact in targets:
        if target_compact in {NO_MATCH_EXPECTED, AMBIGUOUS_EXPECTED}:
            continue
        for result_norm, result_compact in values:
            if result_norm == target_norm or result_compact == target_compact:
                return 3
            if target_norm and result_norm.startswith(f"{target_norm} "):
                return 2
            if target_compact and result_compact.startswith(target_compact):
                return 2
    return 0


def ranking_metrics(
    relevances: list[int],
    case: dict[str, Any],
    has_results: bool,
    rel_total: int,
) -> tuple[int, float, float]:
    if case["expected_behavior"] == "no_match":
        success = not has_results
        return (1 if success else 999, 1.0 if success else 0.0, 1.0 if success else 0.0)

    first_rank = 999
    relevant_seen = 0
    ap = 0.0
    for rank, rel in enumerate(relevances, 1):
        if rel > 0:
            if first_rank == 999:
                first_rank = rank
            relevant_seen += 1
            ap += relevant_seen / rank
    ap20 = ap / min(rel_total, TOP_K_RESULTS)
    ndcg20 = current_eval.ndcg(relevances, rel_total)
    return first_rank, ap20, ndcg20


def behavior_success_for_case(case: dict[str, Any], first_rank: int, has_results: bool) -> bool:
    if case["expected_behavior"] == "match":
        return first_rank <= TOP_K_RESULTS
    if case["expected_behavior"] == "ambiguous":
        return first_rank <= TOP_K_RESULTS
    return not has_results


def metric_rows_by_scope_category(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_scope_category: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_scope_category[(row["scope"], row["category"])].append(row)
        by_scope[row["scope"]].append(row)
    metrics: list[dict[str, Any]] = []
    for scope, group in sorted(by_scope.items()):
        metrics.append(metric_row(scope, "__ALL__", group))
    metrics.append(metric_row("__ALL__", "__ALL__", rows))
    for (scope, category), group in sorted(by_scope_category.items()):
        metrics.append(metric_row(scope, category, group))
    return metrics


def metric_rows_by_error_type(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scope"], row["category"], row["error_type"])].append(row)
    return [
        {**metric_row(scope, category, group), "error_type": error_type}
        for (scope, category, error_type), group in sorted(grouped.items())
    ]


def metric_row(scope: str, category: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        raise ValueError("cannot aggregate empty rows")
    return {
        "scope": scope,
        "category": category,
        "cases": n,
        "hit_at_1": sum(row["first_rank"] <= 1 for row in rows) / n,
        "hit_at_5": sum(row["first_rank"] <= 5 for row in rows) / n,
        "hit_at_10": sum(row["first_rank"] <= 10 for row in rows) / n,
        "hit_at_20": sum(row["first_rank"] <= 20 for row in rows) / n,
        "mrr_at_20": sum((1 / row["first_rank"]) if row["first_rank"] <= TOP_K_RESULTS else 0 for row in rows) / n,
        "map_at_20": sum(float(row["ap20"]) for row in rows) / n,
        "ndcg_at_20": sum(float(row["ndcg20"]) for row in rows) / n,
        "no_result_rate": sum(row["result_count"] == 0 for row in rows) / n,
        "behavior_success_rate": sum(row["behavior_success"] for row in rows) / n,
        "network_error_rate": sum(bool(row["network_error"]) for row in rows) / n,
        "avg_candidate_pool": sum(row["candidate_pool"] for row in rows) / n,
    }


def failure_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures = []
    for row in rows:
        if row["behavior_success"] and row["first_rank"] <= TOP_K_RESULTS and not row["network_error"]:
            continue
        failures.append({
            "scope": row["scope"],
            "category": row["category"],
            "error_type": row["error_type"],
            "expected_behavior": row["expected_behavior"],
            "danger": row["danger"],
            "input": row["input"],
            "expected": row["expected"],
            "top1_base": row["top1_base"],
            "top5_bases": row["top5_bases"],
            "network_error": row["network_error"],
        })
        if len(failures) >= 1500:
            break
    return failures or [{
        "scope": "",
        "category": "",
        "error_type": "",
        "expected_behavior": "",
        "danger": "",
        "input": "",
        "expected": "",
        "top1_base": "",
        "top5_bases": "",
        "network_error": "",
    }]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def write_report(
    path: Path,
    category_metrics: list[dict[str, Any]],
    error_metrics: list[dict[str, Any]],
    elapsed_seconds: float,
    evaluated_cases: int,
    args: argparse.Namespace,
    live_requests: int,
) -> None:
    by_key = {(row["scope"], row["category"]): row for row in category_metrics}
    scope_order = ["inside", "safety", "semi_outside", "smoke", "__ALL__"]
    scope_rows = [by_key[(scope, "__ALL__")] for scope in scope_order if (scope, "__ALL__") in by_key]
    category_rows = [row for row in category_metrics if row["category"] != "__ALL__"]
    context = load_category_context()

    lines = [
        f"# DrugEye V2 Benchmark ({args.mode})",
        "",
        f"This report benchmarks the public DrugEye ASP.NET search page against `{display_path(args.dataset)}`.",
        "",
        "Important limitation: DrugEye returns a ranked product list but does not expose a confidence or clarification flag. Therefore this report scores retrieval and simple expected behavior, not unsafe confident top-1 behavior.",
        "",
        "## Headline",
        "",
        f"- Evaluated cases: `{evaluated_cases:,}`.",
        f"- Live website requests: `{live_requests:,}`. Cached duplicate queries do not count here.",
        f"- Runtime: `{elapsed_seconds:.2f}` seconds.",
        f"- DrugEye mode: `{args.mode}`.",
        "",
        "| scope | cases | Hit@1 | Hit@5 | Hit@20 | behavior success | no-result | network error | avg results |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in scope_rows:
        lines.append(
            f"| `{row['scope']}` | {row['cases']:,} | {pct(row['hit_at_1'])} | {pct(row['hit_at_5'])} | "
            f"{pct(row['hit_at_20'])} | {pct(row['behavior_success_rate'])} | {pct(row['no_result_rate'])} | "
            f"{pct(row['network_error_rate'])} | {float(row['avg_candidate_pool']):.2f} |"
        )

    lines += [
        "",
        "## Category Scores",
        "",
        "| scope | category | cases | Hit@1 | Hit@20 | behavior success | no-result | network error |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(category_rows, key=lambda item: (item["scope"], int(context.get(item["category"], {}).get("category_number", 999)))):
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {row['cases']:,} | {pct(row['hit_at_1'])} | "
            f"{pct(row['hit_at_20'])} | {pct(row['behavior_success_rate'])} | {pct(row['no_result_rate'])} | "
            f"{pct(row['network_error_rate'])} |"
        )

    lines += [
        "",
        "## Error-Type Scores",
        "",
        "| scope | category | error_type | cases | Hit@1 | Hit@20 | behavior success | no-result | network error |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(error_metrics, key=lambda item: (item["scope"], item["category"], item["error_type"])):
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | `{row['error_type']}` | {row['cases']:,} | "
            f"{pct(row['hit_at_1'])} | {pct(row['hit_at_20'])} | {pct(row['behavior_success_rate'])} | "
            f"{pct(row['no_result_rate'])} | {pct(row['network_error_rate'])} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(
    path: Path,
    elapsed_seconds: float,
    evaluated_cases: int,
    args: argparse.Namespace,
    live_requests: int,
    cache_path: Path,
) -> None:
    payload = {
        "evaluated_cases": evaluated_cases,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "mode": args.mode,
        "dataset": display_path(args.dataset),
        "output_prefix": args.output_prefix or f"v2_drugeye_{args.mode}",
        "limit": args.limit,
        "offset": args.offset,
        "sleep": args.sleep,
        "live_requests": live_requests,
        "cache_path": str(cache_path.relative_to(ROOT) if cache_path.is_relative_to(ROOT) else cache_path),
        "base_url": BASE_URL,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_category_context() -> dict[str, dict[str, str]]:
    with CATEGORY_SUMMARY_PATH.open(newline="", encoding="utf-8") as handle:
        return {row["category"]: row for row in csv.DictReader(handle)}


if __name__ == "__main__":
    raise SystemExit(main())
