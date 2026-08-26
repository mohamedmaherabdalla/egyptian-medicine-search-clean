#!/usr/bin/env python3
"""Record executed, duplicate, incompatible, and credential-blocked OCR systems."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmark_common import DEFAULT_RESULTS_DIR, read_csv, write_csv


FIELDS = [
    "system", "system_type", "intended_input", "independent_model", "status",
    "completed_rows", "result_file", "reason_or_scope",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser.parse_args()


def observation_status(results_dir: Path, system: str, pattern: str, intended_input: str) -> dict[str, object]:
    paths = sorted(results_dir.glob(pattern))
    paths = [path for path in paths if not path.name.startswith("pilot_")]
    if not paths:
        return {
            "system": system,
            "system_type": "open_source",
            "intended_input": intended_input,
            "independent_model": 1,
            "status": "not_run",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "No canonical observation file exists.",
        }
    path = paths[0]
    rows = read_csv(path)
    complete = len(rows) >= 5577
    return {
        "system": system,
        "system_type": "open_source",
        "intended_input": intended_input,
        "independent_model": 1,
        "status": "complete" if complete else "partial_checkpoint",
        "completed_rows": len(rows),
        "result_file": str(path),
        "reason_or_scope": "RxHandBD word-level benchmark.",
    }


def exact_file_status(
    results_dir: Path,
    system: str,
    relative_path: str,
    intended_input: str,
    system_type: str = "open_source",
    complete_rows: int = 5577,
    complete_status: str = "complete",
    reason: str = "RxHandBD word-level benchmark.",
) -> dict[str, object]:
    path = results_dir / relative_path
    rows = read_csv(path) if path.exists() else []
    return {
        "system": system,
        "system_type": system_type,
        "intended_input": intended_input,
        "independent_model": 1,
        "status": complete_status if len(rows) >= complete_rows else "not_run",
        "completed_rows": len(rows),
        "result_file": str(path) if rows else "",
        "reason_or_scope": reason,
    }


def donut_pilot_status(results_dir: Path) -> dict[str, object]:
    paths = sorted((results_dir / "calibration").glob("pilot_donut_*.csv"))
    candidates = [(path, read_csv(path)) for path in paths]
    path, rows = max(candidates, key=lambda item: len(item[1])) if candidates else (None, [])
    return {
        "system": "chinmays18 medical-prescription Donut",
        "system_type": "open_source_medical",
        "intended_input": "full prescription",
        "independent_model": 1,
        "status": "input_mismatch_pilot_complete" if rows else "not_primary_input_mismatch",
        "completed_rows": len(rows),
        "result_file": str(path) if path else "",
        "reason_or_scope": (
            "Pilot only: RxHandBD contains isolated word crops, while the model is intended "
            "for full prescription documents. It is excluded from the primary comparison."
        ),
    }


def secondary_paddle_status(results_dir: Path) -> dict[str, object]:
    paths = sorted((results_dir / "secondary").glob("full_paddleocr_v3_*.csv"))
    path = paths[0] if paths else None
    rows = read_csv(path) if path else []
    return {
        "system": "PaddleOCR English v3 mobile (secondary)",
        "system_type": "open_source_secondary_configuration",
        "intended_input": "word crop",
        "independent_model": 0,
        "status": "complete_excluded_from_primary_aggregate" if rows else "not_run",
        "completed_rows": len(rows),
        "result_file": str(path) if path else "",
        "reason_or_scope": "Same PaddleOCR family; v6 medium won the training-only model-selection pilot.",
    }


def main() -> int:
    args = parse_args()
    rows = [
        exact_file_status(
            args.results_dir, "Tesseract 5 LSTM", "ocr_tesseract_lstm_raw_all.csv", "word/line"
        ),
        exact_file_status(
            args.results_dir,
            "Microsoft TrOCR Base Handwritten (zero-shot)",
            "ocr_trocr_raw_all.csv",
            "single text line",
        ),
        exact_file_status(
            args.results_dir,
            "Microsoft TrOCR Base fine-tuned on RxHandBD",
            "ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv",
            "single text line",
            system_type="open_source_domain_finetuned",
            reason="Promoted after a 600-row screen and disjoint 1,000-row train validation; full RxHandBD run.",
        ),
        exact_file_status(
            args.results_dir, "EasyOCR 1.7", "ocr_easyocr_raw_all.csv", "word/page"
        ),
        exact_file_status(
            args.results_dir,
            "PaddleOCR PP-OCRv6 English recognition",
            "ocr_paddleocr_raw_all.csv",
            "word crop",
        ),
        exact_file_status(
            args.results_dir,
            "Microsoft TrOCR Large Handwritten",
            "ocr_validation/trocr_large_raw_train1000.csv",
            "single text line",
            complete_rows=1000,
            complete_status="validation_complete_not_promoted",
            reason="Validated on 1,000 disjoint training rows; 27.60% exact, below the final promotion band.",
        ),
        exact_file_status(
            args.results_dir,
            "GOT-OCR2 580M",
            "screening/got_ocr2_raw_train600.csv",
            "general OCR/image-to-text",
            complete_rows=600,
            complete_status="screen_complete_not_promoted",
            reason="600-row screen: 23.33% exact and about 744 ms/image; failed accuracy and latency promotion criteria.",
        ),
        secondary_paddle_status(args.results_dir),
        donut_pilot_status(args.results_dir),
        {
            "system": "JonSnow Medical-Prescription-OCR",
            "system_type": "open_source_wrapper",
            "intended_input": "full prescription",
            "independent_model": 0,
            "status": "not_counted_duplicate_model",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "Wrapper uses the same chinmays18 Donut checkpoint.",
        },
        {
            "system": "David-Magdy OCR pipeline",
            "system_type": "open_source_medical_pipeline",
            "intended_input": "full prescription",
            "independent_model": 1,
            "status": "blocked_missing_full_page_input",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "Requires separate raw-OCR and post-SymSpell evaluation on full pages.",
        },
        {
            "system": "DeepSeek-OCR",
            "system_type": "open_source_document_vlm",
            "intended_input": "document/page",
            "independent_model": 1,
            "status": "blocked_incompatible_local_backend",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "Official execution path is CUDA-oriented; the benchmark host is Apple MPS and the task is an isolated word crop.",
        },
        {
            "system": "PaddleOCR-VL",
            "system_type": "open_source_document_vlm",
            "intended_input": "document/page parsing",
            "independent_model": 1,
            "status": "not_run_input_and_backend_mismatch",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "Page-structure parsing is not comparable to recognition-only word crops; the supported local backend is not Apple MPS.",
        },
        {
            "system": "Qwen2.5-VL",
            "system_type": "open_source_general_vlm",
            "intended_input": "general vision-language",
            "independent_model": 1,
            "status": "researched_not_promoted_to_execution",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "Not a handwriting-specialist checkpoint; GOT-OCR2 represented the general OCR/VLM screen and failed promotion.",
        },
    ]
    for provider in ("Google Vision", "Azure Document Intelligence Read", "Amazon Textract", "Koncile Prescription OCR"):
        rows.append({
            "system": provider,
            "system_type": "commercial_api",
            "intended_input": "full prescription/document",
            "independent_model": 1,
            "status": "blocked_credentials_and_privacy_approval",
            "completed_rows": 0,
            "result_file": "",
            "reason_or_scope": "Requires API credentials and an approved deidentified common sample.",
        })
    write_csv(args.results_dir / "model_execution_status.csv", rows, FIELDS)
    print(args.results_dir / "model_execution_status.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
