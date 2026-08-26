#!/usr/bin/env python3
"""Fine-tune TrOCR on RxHandBD without using the official test for selection."""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from PIL import Image

from benchmark_common import DEFAULT_ARTIFACTS_DIR, compact_text, file_sha256, levenshtein, read_csv, write_json
from run_ocr_benchmark import preprocess_image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train-manifest",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR / "experiments" / "selection" / "train_finetune_manifest_3457.csv",
    )
    parser.add_argument(
        "--validation-manifest",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR / "experiments" / "selection" / "train_validation_manifest_1000.csv",
    )
    parser.add_argument("--base-model", default="microsoft/trocr-base-handwritten")
    parser.add_argument("--preprocessing", default="autocontrast")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR.parent / "models" / "training" / "trocr_base_rxhandbd",
    )
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.10)
    parser.add_argument("--max-label-length", type=int, default=48)
    parser.add_argument("--max-new-tokens", type=int, default=48)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--max-train-steps", type=int, default=0)
    parser.add_argument("--validation-limit", type=int, default=0)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--gradient-checkpointing", action="store_true")
    return parser.parse_args()


def select_device(requested: str, torch) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class RxHandBDDataset:
    def __init__(self, rows, processor, preprocessing: str, max_label_length: int):
        self.rows = rows
        self.processor = processor
        self.preprocessing = preprocessing
        self.max_label_length = max_label_length

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        image = preprocess_image(Path(row["image_path"]), self.preprocessing).convert("RGB")
        pixel_values = self.processor(images=image, return_tensors="pt").pixel_values.squeeze(0)
        tokenized = self.processor.tokenizer(
            row["ground_truth_raw"],
            padding="max_length",
            max_length=self.max_label_length,
            truncation=True,
            return_tensors="pt",
        ).input_ids.squeeze(0)
        tokenized[tokenized == self.processor.tokenizer.pad_token_id] = -100
        return {"pixel_values": pixel_values, "labels": tokenized}


def evaluate(model, processor, rows, preprocessing: str, device: str, batch_size: int, max_new_tokens: int):
    import torch

    outputs = []
    model.eval()
    previous_cache = model.config.use_cache
    model.config.use_cache = True
    started = time.perf_counter()
    try:
        with torch.inference_mode():
            for start in range(0, len(rows), batch_size):
                batch = rows[start:start + batch_size]
                images = [
                    preprocess_image(Path(row["image_path"]), preprocessing).convert("RGB")
                    for row in batch
                ]
                pixel_values = processor(images=images, return_tensors="pt").pixel_values.to(device)
                generated = model.generate(pixel_values, max_new_tokens=max_new_tokens)
                texts = processor.batch_decode(generated, skip_special_tokens=True)
                outputs.extend(texts)
    finally:
        model.config.use_cache = previous_cache
    exact = 0
    total_distance = 0.0
    examples = []
    for row, output in zip(rows, outputs):
        expected_key = compact_text(row["ground_truth_raw"])
        output_key = compact_text(output)
        distance = levenshtein(output_key, expected_key)
        exact += int(output_key == expected_key and bool(expected_key))
        total_distance += distance / max(len(expected_key), 1)
        if len(examples) < 30 and output_key != expected_key:
            examples.append({
                "sample_id": row["sample_id"],
                "image_id": row["image_id"],
                "expected": row["ground_truth_raw"],
                "output": output,
                "normalized_edit_distance": distance / max(len(expected_key), 1),
            })
    return {
        "rows": len(rows),
        "exact_matches": exact,
        "exact_accuracy": exact / max(len(rows), 1),
        "mean_character_error_rate": total_distance / max(len(rows), 1),
        "elapsed_seconds": time.perf_counter() - started,
        "failure_examples": examples,
    }


def main() -> int:
    args = parse_args()
    try:
        import torch
        from torch.nn.utils import clip_grad_norm_
        from torch.utils.data import DataLoader
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as exc:
        raise RuntimeError("Training requires torch and transformers from requirements-ocr.txt") from exc

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    train_rows = [
        row for row in read_csv(args.train_manifest)
        if row.get("image_valid") == "1" and row.get("ground_truth_usable") == "1"
    ]
    validation_rows = [
        row for row in read_csv(args.validation_manifest)
        if row.get("image_valid") == "1" and row.get("ground_truth_usable") == "1"
    ]
    if args.validation_limit:
        validation_rows = validation_rows[:args.validation_limit]
    train_ids = {row["sample_id"] for row in train_rows}
    validation_ids = {row["sample_id"] for row in validation_rows}
    if train_ids & validation_ids:
        raise ValueError("fine-tuning and validation manifests overlap")
    if any(row.get("split") == "test" for row in train_rows + validation_rows):
        raise ValueError("official test rows are forbidden during fine-tuning and selection")

    processor = TrOCRProcessor.from_pretrained(args.base_model)
    model = VisionEncoderDecoderModel.from_pretrained(args.base_model)
    device = select_device(args.device, torch)
    model.to(device)
    model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
    model.config.pad_token_id = processor.tokenizer.pad_token_id
    model.config.eos_token_id = processor.tokenizer.sep_token_id
    model.config.vocab_size = model.config.decoder.vocab_size
    model.config.use_cache = False
    if args.gradient_checkpointing and hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()

    trainable_parameters = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total_parameters = sum(parameter.numel() for parameter in model.parameters())
    dataset = RxHandBDDataset(
        train_rows, processor, args.preprocessing, args.max_label_length
    )
    generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,
        generator=generator,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    steps_per_epoch = math.ceil(len(loader) / args.gradient_accumulation)
    planned_steps = steps_per_epoch * args.epochs
    if args.max_train_steps:
        planned_steps = min(planned_steps, args.max_train_steps)
    warmup_steps = round(planned_steps * args.warmup_ratio)

    def learning_rate_scale(step: int) -> float:
        if warmup_steps and step < warmup_steps:
            return (step + 1) / warmup_steps
        decay_steps = max(planned_steps - warmup_steps, 1)
        return max(0.0, (planned_steps - step) / decay_steps)

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, learning_rate_scale)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "base_model": args.base_model,
        "preprocessing": args.preprocessing,
        "device": device,
        "seed": args.seed,
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "train_validation_overlap": 0,
        "official_test_rows_used": 0,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "effective_batch_size": args.batch_size * args.gradient_accumulation,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "warmup_ratio": args.warmup_ratio,
        "warmup_steps": warmup_steps,
        "planned_optimizer_steps": planned_steps,
        "gradient_checkpointing": args.gradient_checkpointing,
        "max_train_steps": args.max_train_steps,
        "trainable_parameters": trainable_parameters,
        "total_parameters": total_parameters,
        "train_manifest_sha256": file_sha256(args.train_manifest),
        "validation_manifest_sha256": file_sha256(args.validation_manifest),
        "history": [],
    }
    run["baseline_validation"] = evaluate(
        model,
        processor,
        validation_rows,
        args.preprocessing,
        device,
        max(1, args.batch_size * 2),
        args.max_new_tokens,
    )
    write_json(args.output_dir / "training_run.json", run)

    best_key = (-1.0, float("-inf"))
    optimizer_steps = 0
    micro_steps = 0
    stop = False
    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        epoch_loss = 0.0
        epoch_batches = 0
        started = time.perf_counter()
        for batch in loader:
            pixel_values = batch["pixel_values"].to(device)
            labels = batch["labels"].to(device)
            result = model(pixel_values=pixel_values, labels=labels)
            loss = result.loss / args.gradient_accumulation
            loss.backward()
            epoch_loss += float(result.loss.detach().cpu())
            epoch_batches += 1
            micro_steps += 1
            if micro_steps % args.gradient_accumulation == 0:
                clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
                optimizer_steps += 1
                if args.log_every and optimizer_steps % args.log_every == 0:
                    print(
                        f"epoch={epoch} optimizer_step={optimizer_steps} "
                        f"mean_loss={epoch_loss / epoch_batches:.6f} "
                        f"lr={scheduler.get_last_lr()[0]:.8g}",
                        flush=True,
                    )
                if args.max_train_steps and optimizer_steps >= args.max_train_steps:
                    stop = True
                    break
        if micro_steps % args.gradient_accumulation:
            clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            optimizer_steps += 1

        training_elapsed_seconds = time.perf_counter() - started
        validation = evaluate(
            model,
            processor,
            validation_rows,
            args.preprocessing,
            device,
            max(1, args.batch_size * 2),
            args.max_new_tokens,
        )
        epoch_record = {
            "epoch": epoch,
            "optimizer_steps": optimizer_steps,
            "mean_train_loss": epoch_loss / max(epoch_batches, 1),
            "training_elapsed_seconds": training_elapsed_seconds,
            "validation": validation,
        }
        run["history"].append(epoch_record)
        checkpoint_dir = args.output_dir / f"epoch_{epoch}"
        model.save_pretrained(checkpoint_dir)
        processor.save_pretrained(checkpoint_dir)
        key = (validation["exact_accuracy"], -validation["mean_character_error_rate"])
        if key > best_key:
            best_key = key
            best_dir = args.output_dir / "best"
            model.save_pretrained(best_dir)
            processor.save_pretrained(best_dir)
            run["best_epoch"] = epoch
            run["best_validation"] = validation
        write_json(args.output_dir / "training_run.json", run)
        print(json.dumps(epoch_record, ensure_ascii=False, indent=2), flush=True)
        if stop:
            break

    best_model_file = args.output_dir / "best" / "model.safetensors"
    if best_model_file.exists():
        run["best_model_sha256"] = file_sha256(best_model_file)
    run["completed_optimizer_steps"] = optimizer_steps
    write_json(args.output_dir / "training_run.json", run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
