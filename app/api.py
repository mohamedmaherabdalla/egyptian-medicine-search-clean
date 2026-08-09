#!/usr/bin/env python3
"""Serve the existing UI with the real Python Algorithm 6 runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
ALGORITHM_PATH = (
    ROOT
    / "benchmark_01_legacy"
    / "master_algorithms"
    / "algorithm_6_consensus_search.py"
)
CATALOG_PATH = APP_DIR / "data" / "catalog.json"
SEARCH_LOCK = threading.Lock()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=20, ge=1, le=20)


def load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("algorithm_6_api_runtime", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Algorithm 6 from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_display_records() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    by_family: dict[str, dict[str, Any]] = {}
    by_product: dict[str, dict[str, Any]] = {}
    for record in payload["records"]:
        product_key = algorithm_6.current_app.compact_key(record.get("n", ""))
        family_key = algorithm_6.current_app.compact_key(
            record.get("b") or record.get("n") or ""
        )
        if product_key:
            by_product.setdefault(product_key, record)
        if family_key:
            by_family.setdefault(family_key, record)
    return by_family, by_product


def add_display_fields(result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    family_name = algorithm_6.result_name(result)
    family_key = algorithm_6.current_app.compact_key(family_name)
    product_key = algorithm_6.current_app.compact_key(
        result.get("commercial_name") or ""
    )
    record = display_by_product.get(product_key) or display_by_family.get(family_key) or {}
    output.update(
        {
            "commercial_name_en": record.get("n") or result.get("commercial_name") or family_name,
            "commercial_name_ar": record.get("ar") or "-",
            "base_group_key": family_name,
            "family_group_key": result.get("variant_group") or family_name,
            "ingredient_key": record.get("ing") or record.get("s") or "-",
            "strength": record.get("st") or "-",
            "dosage_form": record.get("f") or "-",
            "route_family": record.get("r") or "-",
            "price_egp": record.get("p") or "-",
            "manufacturer": record.get("m") or "-",
            "drug_class": record.get("dc") or "-",
            "warnings": record.get("w") or "",
            "matched_context": "",
            "needs_clarification": True,
            "confirmation_required": True,
        }
    )
    return output


started = time.perf_counter()
algorithm_6 = load_module(ALGORITHM_PATH)
catalog = algorithm_6.prepare_catalog()
display_by_family, display_by_product = load_display_records()
initialization_seconds = time.perf_counter() - started

app = FastAPI(title="Egyptian Medicine Search Algorithm 6", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://mohamedmaherabdalla.github.io",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/runtime")
def runtime() -> dict[str, Any]:
    return {
        "ready": True,
        "algorithm": "algorithm_6",
        "evaluation_version": catalog.policy.get(
            "evaluation_version", "algorithm_6_consensus_v1"
        ),
        "medicine_count": 25_066,
        "family_count": len(catalog.families),
        "initialization_seconds": round(initialization_seconds, 3),
        "process_memory_mb": round(
            psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024,
            1,
        ),
    }


@app.post("/api/search")
def search(request: SearchRequest) -> dict[str, Any]:
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must contain visible text")
    started_at = time.perf_counter()
    with SEARCH_LOCK:
        response = algorithm_6.search_catalog(catalog, query, request.limit)
    if response.get("algorithm") != "algorithm_6":
        raise RuntimeError("Algorithm 6 returned an invalid runtime identifier")
    response["results"] = [add_display_fields(item) for item in response["results"]]
    response["server_elapsed_ms"] = round(
        (time.perf_counter() - started_at) * 1000,
        3,
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "algorithm": "algorithm_6"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.get("/app.js")
def javascript() -> FileResponse:
    return FileResponse(APP_DIR / "app.js", media_type="application/javascript")


@app.get("/styles.css")
def stylesheet() -> FileResponse:
    return FileResponse(APP_DIR / "styles.css", media_type="text/css")


app.mount("/data", StaticFiles(directory=APP_DIR / "data"), name="data")
