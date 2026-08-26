#!/usr/bin/env python3
"""Generate publication figures directly from OCR benchmark CSV files."""

from __future__ import annotations

import argparse
import math
import os
import re
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "data/04_model_predictions/predictions.csv"
DEFAULT_RESULTS = ROOT / "artifacts/04_model_predictions/algorithm_4_results.csv"
DEFAULT_OUTPUT = ROOT / "results/04_model_predictions/figures"

BLUE = "#2F5D8C"
GREEN = "#2A7F62"
ORANGE = "#C27A2C"
RED = "#B44C43"
PURPLE = "#735A93"
GRAY = "#66717D"
LIGHT_GRAY = "#D9DEE5"

COHORT_ORDER = [
    "real_drug_name_collision",
    "normalized_exact_match",
    "extreme_distance_prediction",
    "visible_name_fragment",
    "high_distance_prediction",
    "standard_ocr_error",
]
DISTANCE_ORDER = [
    "0_exact_after_normalization",
    "1_single_edit",
    "2_3_edits",
    "4_5_edits",
    "6_plus_edits",
]
OPERATION_ORDER = [
    "formatting_only",
    "extra_characters_only",
    "missing_characters_only",
    "substitutions_only",
    "mixed_operations",
]
QUERY_LENGTH_ORDER = [
    "1_3_characters",
    "4_5_characters",
    "6_7_characters",
    "8_9_characters",
    "10_plus_characters",
]
LENGTH_DIRECTION_ORDER = [
    "ocr_output_shorter",
    "equal_length",
    "ocr_output_longer",
]

LABELS = {
    "normalized_exact_match": "Normalized exact match",
    "standard_ocr_error": "Standard OCR error",
    "visible_name_fragment": "Visible name fragment",
    "high_distance_prediction": "High-distance prediction",
    "extreme_distance_prediction": "Extreme-distance prediction",
    "real_drug_name_collision": "Real-drug-name collision",
    "0_exact_after_normalization": "0: exact after normalization",
    "1_single_edit": "1 edit",
    "2_3_edits": "2-3 edits",
    "4_5_edits": "4-5 edits",
    "6_plus_edits": "6+ edits",
    "formatting_only": "Formatting only",
    "extra_characters_only": "Extra characters only",
    "missing_characters_only": "Missing characters only",
    "substitutions_only": "Substitutions only",
    "mixed_operations": "Mixed operations",
    "1_3_characters": "1-3 characters",
    "4_5_characters": "4-5 characters",
    "6_7_characters": "6-7 characters",
    "8_9_characters": "8-9 characters",
    "10_plus_characters": "10+ characters",
    "ocr_output_shorter": "OCR output shorter",
    "equal_length": "Equal length",
    "ocr_output_longer": "OCR output longer",
    "development": "Development",
    "holdout": "Holdout",
}

MODEL_LABELS = {
    "easyocr": "EasyOCR",
    "got_ocr2": "GOT-OCR2",
    "minicpm_v_46": "MiniCPM-V 4.6",
    "qwen25_vl_3b": "Qwen2.5-VL 3B",
    "paddleocr_vl_space": "PaddleOCR-VL",
    "llava_onevision_qwen2_7b_ov_hf": "LLaVA-OneVision 7B",
    "llava_onevision_qwen2_05b_ov": "LLaVA-OneVision 0.5B",
    "qwen3_vl_4b": "Qwen3-VL 4B",
    "internvl3_1b_hf": "InternVL3 1B",
    "qwen25_vl_7b": "Qwen2.5-VL 7B",
    "qwen3_vl_8b": "Qwen3-VL 8B",
    "trocr": "TrOCR",
    "internvl3_14b_hf": "InternVL3 14B",
    "internvl3_8b_hf": "InternVL3 8B",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.0,
            "axes.titlesize": 12.0,
            "axes.titleweight": "bold",
            "axes.labelsize": 10.0,
            "axes.labelweight": "semibold",
            "axes.edgecolor": GRAY,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def load_data(source_path: Path, results_path: Path) -> pd.DataFrame:
    source = pd.read_csv(source_path, encoding="utf-8-sig")
    results = pd.read_csv(results_path, encoding="utf-8-sig")
    source.insert(
        0,
        "sample_id",
        [f"{model}:{index}" for index, model in enumerate(source["source_model"], 1)],
    )
    data = source.merge(results, on="sample_id", how="inner", validate="one_to_one")
    if len(data) != len(source) or len(data) != len(results):
        raise ValueError(
            f"source/results reconciliation failed: {len(source)} source, "
            f"{len(results)} results, {len(data)} joined"
        )

    numeric_columns = [
        "edited_length",
        "canonical_length",
        "length_difference",
        "edit_distance_count",
        "additions_count",
        "deletions_count",
        "flip_count",
        "matches_count",
        "edit_distance_over_edited_length",
        "edit_distance_over_canonical_length",
        "similarity_over_canonical_length",
        "hit_at_1",
        "hit_at_5",
        "hit_at_10",
        "hit_at_20",
    ]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="raise")

    data["operation_profile"] = data.apply(operation_profile, axis=1)
    data["query_length_band"] = data["edited_length"].map(query_length_band)
    data["length_direction"] = data["length_difference"].map(length_direction)
    data["operation_signature"] = data["operation_sequence"].map(operation_signature)
    data["h20_failure"] = 1 - data["hit_at_20"]
    data["rank_only_failure"] = (
        (data["hit_at_20"] == 1) & (data["hit_at_1"] == 0)
    ).astype(int)
    data["compact_query"] = (
        data["edited_name"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    )
    return data


def operation_profile(row: pd.Series) -> str:
    additions = int(row["additions_count"])
    deletions = int(row["deletions_count"])
    flips = int(row["flip_count"])
    active = sum(value > 0 for value in (additions, deletions, flips))
    if active > 1:
        return "mixed_operations"
    if additions:
        return "missing_characters_only"
    if deletions:
        return "extra_characters_only"
    if flips:
        return "substitutions_only"
    return "formatting_only"


def query_length_band(length: float) -> str:
    if length <= 3:
        return "1_3_characters"
    if length <= 5:
        return "4_5_characters"
    if length <= 7:
        return "6_7_characters"
    if length <= 9:
        return "8_9_characters"
    return "10_plus_characters"


def length_direction(difference: float) -> str:
    if difference < 0:
        return "ocr_output_longer"
    if difference > 0:
        return "ocr_output_shorter"
    return "equal_length"


def operation_signature(sequence: str) -> str:
    operations = re.findall(r"([A-Za-z]+)\(", str(sequence))
    return " ".join(operation[0].upper() for operation in operations) or "Unknown"


def label(value: object) -> str:
    text = str(value)
    return MODEL_LABELS.get(text, LABELS.get(text, text.replace("_", " ").title()))


def grouped_metrics(data: pd.DataFrame, field: str, order: list[str] | None = None) -> pd.DataFrame:
    result = (
        data.groupby(field, observed=True)
        .agg(n=("sample_id", "size"), h1=("hit_at_1", "mean"), h20=("hit_at_20", "mean"))
        .reset_index(names="key")
    )
    if order:
        result["sort"] = result["key"].map({value: index for index, value in enumerate(order)})
        result = result.sort_values("sort").drop(columns="sort")
    else:
        result = result.sort_values(["n", "key"], ascending=[False, True])
    result["label"] = result["key"].map(label)
    return result.reset_index(drop=True)


def impact_metrics(
    data: pd.DataFrame,
    field: str,
    failure_field: str,
    order: list[str] | None = None,
) -> pd.DataFrame:
    result = (
        data.groupby(field, observed=True)
        .agg(n=("sample_id", "size"), failures=(failure_field, "sum"))
        .reset_index(names="key")
    )
    total_failures = result["failures"].sum()
    result["failure_rate"] = result["failures"] / result["n"]
    result["impact_share"] = result["failures"] / total_failures if total_failures else 0.0
    if order:
        result["sort"] = result["key"].map({value: index for index, value in enumerate(order)})
        result = result.sort_values("sort").drop(columns="sort")
    else:
        result = result.sort_values(
            ["failures", "failure_rate", "key"], ascending=[False, False, True]
        )
    result["label"] = result["key"].map(label)
    return result.reset_index(drop=True)


def begin_figure(
    title: str,
    subtitle: str,
    *,
    width: float = 8.6,
    height: float = 4.6,
    columns: int = 1,
) -> tuple[plt.Figure, np.ndarray]:
    fig, axes = plt.subplots(1, columns, figsize=(width, height), squeeze=False)
    fig.suptitle(title, x=0.02, y=0.985, ha="left", va="top", fontsize=12, fontweight="bold")
    fig.text(0.02, 0.935, subtitle, ha="left", va="top", fontsize=8.5, color=GRAY)
    return fig, axes[0]


def save_figure(fig: plt.Figure, output: Path, stem: str) -> None:
    fig.tight_layout(rect=(0.015, 0.015, 0.985, 0.905))
    fig.savefig(output / f"{stem}.pdf", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def style_bar_axis(ax: plt.Axes, *, x_percent: bool = False) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=LIGHT_GRAY, linewidth=0.65, alpha=0.8)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if x_percent:
        ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))


def annotate_horizontal(ax: plt.Axes, bars, *, percent: bool = False, fontsize: float = 8.0) -> None:
    for bar in bars:
        value = bar.get_width()
        text = f"{value:.1f}%" if percent else f"{value:,.0f}"
        ax.text(
            value + ax.get_xlim()[1] * 0.012,
            bar.get_y() + bar.get_height() / 2,
            text,
            va="center",
            ha="left",
            fontsize=fontsize,
            color="#1F2937",
        )


def count_bars(
    output: Path,
    stem: str,
    title: str,
    subtitle: str,
    items: list[tuple[str, float]],
    *,
    xlabel: str,
    ylabel: str,
    color: str = BLUE,
    two_panels: bool = False,
) -> None:
    panel_count = 2 if two_panels and len(items) > 14 else 1
    panel_size = math.ceil(len(items) / panel_count)
    height = max(3.7, 1.7 + 0.34 * panel_size)
    fig, axes = begin_figure(title, subtitle, width=10.0 if panel_count == 2 else 8.6, height=height, columns=panel_count)
    shared_max = max(value for _, value in items) * 1.20 if items else 1.0
    for panel_index, ax in enumerate(axes):
        panel = items[panel_index * panel_size : (panel_index + 1) * panel_size]
        if not panel:
            ax.set_visible(False)
            continue
        names = [name for name, _ in panel]
        values = [value for _, value in panel]
        y = np.arange(len(panel))
        bars = ax.barh(y, values, color=color, height=0.62)
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.set_xlim(0, shared_max)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        style_bar_axis(ax)
        annotate_horizontal(ax, bars)
    save_figure(fig, output, stem)


def distribution_bars(
    output: Path,
    stem: str,
    title: str,
    subtitle: str,
    items: list[tuple[str, float]],
    *,
    xlabel: str,
    ylabel: str = "OCR observations (count)",
    color: str = BLUE,
) -> None:
    width = max(8.6, min(12.0, 5.7 + 0.24 * len(items)))
    fig, axes = begin_figure(title, subtitle, width=width, height=4.6)
    ax = axes[0]
    names = [name for name, _ in items]
    values = [value for _, value in items]
    x = np.arange(len(items))
    bars = ax.bar(x, values, color=color, width=0.72)
    ax.set_xticks(x, names, rotation=45 if any(len(name) > 5 for name in names) else 0, ha="right" if any(len(name) > 5 for name in names) else "center")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, max(values, default=1) * 1.18)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=LIGHT_GRAY, linewidth=0.65, alpha=0.8)
    ax.bar_label(bars, labels=[f"{value:,.0f}" for value in values], padding=2, fontsize=7.5)
    save_figure(fig, output, stem)


def recovery_bars(
    output: Path,
    stem: str,
    title: str,
    subtitle: str,
    metrics: pd.DataFrame,
    *,
    ylabel: str,
    two_panels: bool = False,
) -> None:
    panel_count = 2 if two_panels and len(metrics) > 14 else 1
    panel_size = math.ceil(len(metrics) / panel_count)
    height = max(4.0, 1.8 + 0.48 * panel_size)
    fig, axes = begin_figure(title, subtitle, width=10.3 if panel_count == 2 else 8.8, height=height, columns=panel_count)
    for panel_index, ax in enumerate(axes):
        panel = metrics.iloc[panel_index * panel_size : (panel_index + 1) * panel_size]
        if panel.empty:
            ax.set_visible(False)
            continue
        names = [f"{row.label}  (n={int(row.n)})" for row in panel.itertuples()]
        y = np.arange(len(panel))
        h1 = panel["h1"].to_numpy() * 100
        h20 = panel["h20"].to_numpy() * 100
        bars_h1 = ax.barh(y - 0.18, h1, height=0.32, color=BLUE, label="Hit@1")
        bars_h20 = ax.barh(y + 0.18, h20, height=0.32, color=GREEN, label="Hit@20")
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.set_xlim(0, 112)
        ax.set_xlabel("Recovery rate within group (%)")
        ax.set_ylabel(ylabel)
        style_bar_axis(ax, x_percent=True)
        annotate_horizontal(ax, bars_h1, percent=True, fontsize=7.2)
        annotate_horizontal(ax, bars_h20, percent=True, fontsize=7.2)
        if panel_index == 0:
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    save_figure(fig, output, stem)


def comparison_bars(
    output: Path,
    stem: str,
    title: str,
    subtitle: str,
    metrics: pd.DataFrame,
    *,
    first_field: str,
    second_field: str,
    first_label: str,
    second_label: str,
    ylabel: str,
) -> None:
    height = max(4.0, 1.8 + 0.48 * len(metrics))
    fig, axes = begin_figure(title, subtitle, height=height)
    ax = axes[0]
    names = [f"{row.label}  (n={int(row.n)})" for row in metrics.itertuples()]
    y = np.arange(len(metrics))
    first = metrics[first_field].to_numpy() * 100
    second = metrics[second_field].to_numpy() * 100
    first_bars = ax.barh(y - 0.18, first, height=0.32, color=BLUE, label=first_label)
    second_bars = ax.barh(y + 0.18, second, height=0.32, color=GREEN, label=second_label)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xlabel("Recovery rate within group (%)")
    ax.set_ylabel(ylabel)
    style_bar_axis(ax, x_percent=True)
    annotate_horizontal(ax, first_bars, percent=True, fontsize=7.2)
    annotate_horizontal(ax, second_bars, percent=True, fontsize=7.2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    save_figure(fig, output, stem)


def impact_bars(
    output: Path,
    stem: str,
    title: str,
    subtitle: str,
    metrics: pd.DataFrame,
    *,
    ylabel: str,
) -> None:
    height = max(4.0, 1.8 + 0.52 * len(metrics))
    fig, axes = begin_figure(title, subtitle, height=height)
    ax = axes[0]
    names = [
        f"{row.label}  ({int(row.failures)} misses / {int(row.n)} rows)"
        for row in metrics.itertuples()
    ]
    y = np.arange(len(metrics))
    rates = metrics["failure_rate"].to_numpy() * 100
    shares = metrics["impact_share"].to_numpy() * 100
    rate_bars = ax.barh(y - 0.18, rates, height=0.32, color=ORANGE, label="Failure rate inside group")
    share_bars = ax.barh(y + 0.18, shares, height=0.32, color=RED, label="Share of all failures")
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(0, 112)
    ax.set_xlabel("Percentage (%)")
    ax.set_ylabel(ylabel)
    style_bar_axis(ax, x_percent=True)
    annotate_horizontal(ax, rate_bars, percent=True, fontsize=7.2)
    annotate_horizontal(ax, share_bars, percent=True, fontsize=7.2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    save_figure(fig, output, stem)


def cumulative_recovery(output: Path, data: pd.DataFrame) -> None:
    cutoffs = [1, 5, 10, 20]
    values = [data[f"hit_at_{cutoff}"].mean() * 100 for cutoff in cutoffs]
    fig, axes = begin_figure(
        "Cumulative Algorithm 4 recovery",
        f"Hit@k = percentage with the verified family at or before rank k; denominator is all n={len(data)} rows.",
        height=4.5,
    )
    ax = axes[0]
    ax.plot(cutoffs, values, color=GREEN, marker="o", linewidth=2.0, markersize=6)
    for x, value in zip(cutoffs, values):
        ax.annotate(f"{value:.1f}%", (x, value), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8.5)
    ax.set_xticks(cutoffs)
    ax.set_xlim(0, 21)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Maximum candidate rank k")
    ax.set_ylabel("Hit@k (% of all OCR observations)")
    ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.set_axisbelow(True)
    ax.grid(color=LIGHT_GRAY, linewidth=0.65, alpha=0.8)
    save_figure(fig, output, "16_algorithm_4_overall_recovery")


def operation_composition(output: Path, data: pd.DataFrame) -> None:
    fields = ["additions_count", "deletions_count", "flip_count", "matches_count"]
    grouped = data.groupby("source_model", observed=True)[fields].sum()
    grouped["total"] = grouped.sum(axis=1)
    grouped = grouped.sort_values("total", ascending=False)
    shares = grouped[fields].div(grouped["total"], axis=0) * 100
    fig, axes = begin_figure(
        "Character-alignment composition by OCR model",
        "Each horizontal bar sums to 100% of source alignment operations for that model.",
        height=7.2,
    )
    ax = axes[0]
    y = np.arange(len(shares))
    left = np.zeros(len(shares))
    colors = [ORANGE, RED, PURPLE, GREEN]
    names = ["Additions", "Deletions", "Replacements", "Matches"]
    for field, name, color in zip(fields, names, colors):
        values = shares[field].to_numpy()
        bars = ax.barh(y, values, left=left, height=0.62, color=color, label=name)
        for bar, value in zip(bars, values):
            if value >= 8:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{value:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=7.0,
                    color="white" if color != ORANGE else "#1F2937",
                )
        left += values
    ax.set_yticks(y, [MODEL_LABELS.get(value, value) for value in shares.index])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of character-alignment operations (%)")
    ax.set_ylabel("OCR source model")
    ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), ncol=4)
    style_bar_axis(ax)
    save_figure(fig, output, "14_operation_by_model")


def distance_similarity_scatter(output: Path, data: pd.DataFrame) -> None:
    fig, axes = begin_figure(
        "Compact normalized edit distance versus compact similarity",
        f"One point per row (n={len(data)}); compacting removes spaces/punctuation before Levenshtein distance.",
        width=8.6,
        height=5.3,
    )
    ax = axes[0]
    rng = np.random.default_rng(20260714)
    x = data["normalized_edit_distance"].to_numpy(float)
    y = 1.0 - x
    success = data["hit_at_1"].to_numpy(int) == 1
    jitter_x = rng.normal(0, 0.007, len(data))
    jitter_y = rng.normal(0, 0.007, len(data))
    ax.scatter(x[~success] + jitter_x[~success], y[~success] + jitter_y[~success], s=23, color=RED, alpha=0.48, edgecolors="none", label="Hit@1 miss")
    ax.scatter(x[success] + jitter_x[success], y[success] + jitter_y[success], s=23, color=GREEN, alpha=0.58, edgecolors="none", label="Hit@1 success")
    limit = max(2.05, math.ceil(float(x.max()) * 10) / 10)
    line_x = np.linspace(0, limit, 100)
    ax.plot(line_x, 1 - line_x, color=GRAY, linewidth=1.0, linestyle="--", label="Similarity = 1 - distance")
    ax.axvline(0.60, color=ORANGE, linewidth=1.2, linestyle=":", label="Extreme threshold = 0.60")
    ax.set_xlim(-0.05, limit)
    ax.set_ylim(min(-1.05, float(y.min()) - 0.05), 1.05)
    ax.set_xlabel("Compact edit distance / compact target length (ratio)")
    ax.set_ylabel("Compact similarity (1 - normalized distance)")
    ax.set_axisbelow(True)
    ax.grid(color=LIGHT_GRAY, linewidth=0.65, alpha=0.8)
    ax.legend(loc="lower left", ncol=2)
    save_figure(fig, output, "25_distance_similarity_scatter")


def exact_distance_recovery(output: Path, data: pd.DataFrame) -> None:
    metrics = grouped_metrics(data, "edit_distance_count").sort_values("key")
    fig, axes = begin_figure(
        "Recovery at each source edit distance",
        "Rates use all rows at each exact source-provided edit distance; labels show group size.",
        width=9.2,
        height=4.8,
    )
    ax = axes[0]
    x = metrics["key"].to_numpy(int)
    ax.plot(x, metrics["h1"] * 100, color=BLUE, marker="o", linewidth=1.8, label="Hit@1")
    ax.plot(x, metrics["h20"] * 100, color=GREEN, marker="s", linewidth=1.8, label="Hit@20")
    for row in metrics.itertuples():
        ax.annotate(f"n={int(row.n)}", (int(row.key), row.h20 * 100), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=6.8, color=GRAY)
    ax.set_xticks(x)
    ax.set_xlim(x.min() - 0.5, x.max() + 0.5)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Source edit distance (character operations)")
    ax.set_ylabel("Recovery rate (% within exact-distance group)")
    ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.set_axisbelow(True)
    ax.grid(color=LIGHT_GRAY, linewidth=0.65, alpha=0.8)
    ax.legend(loc="upper right")
    save_figure(fig, output, "26_recovery_by_source_distance")


def dataset_overview(output: Path, data: pd.DataFrame) -> None:
    """Show the four distributions needed to interpret the benchmark denominator."""

    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.2))
    fig.suptitle(
        "OCR benchmark at a glance",
        x=0.03,
        y=0.985,
        ha="left",
        va="top",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.03,
        0.945,
        f"All panels describe the same {len(data)} joined OCR observations before collision rows are removed from primary scoring.",
        ha="left",
        va="top",
        fontsize=8.5,
        color=GRAY,
    )

    split_counts = data["split"].value_counts().reindex(["development", "holdout"])
    ax = axes[0, 0]
    bars = ax.bar(["Development", "Holdout"], split_counts, color=[BLUE, GREEN], width=0.62)
    ax.set_title("A. Evaluation split", loc="left")
    ax.set_xlabel("Target-family-disjoint split")
    ax.set_ylabel("OCR observations (count)")
    ax.bar_label(
        bars,
        labels=[f"{value} ({value / len(data) * 100:.1f}%)" for value in split_counts],
        padding=3,
        fontsize=8,
    )
    ax.set_ylim(0, split_counts.max() * 1.18)
    ax.grid(axis="y", color=LIGHT_GRAY, linewidth=0.65)
    ax.set_axisbelow(True)

    cohort_counts = data["analysis_cohort"].value_counts().reindex(COHORT_ORDER)
    ax = axes[0, 1]
    cohort_names = [label(value) for value in cohort_counts.index]
    y = np.arange(len(cohort_counts))
    bars = ax.barh(y, cohort_counts, color=ORANGE, height=0.62)
    ax.set_title("B. Analysis cohort", loc="left")
    ax.set_yticks(y, cohort_names)
    ax.invert_yaxis()
    ax.set_xlabel("OCR observations (count)")
    ax.set_ylabel("Rule-assigned cohort")
    ax.set_xlim(0, cohort_counts.max() * 1.25)
    style_bar_axis(ax)
    for bar, value in zip(bars, cohort_counts):
        ax.text(
            value + cohort_counts.max() * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{value} ({value / len(data) * 100:.1f}%)",
            va="center",
            fontsize=7.2,
        )

    ax = axes[1, 0]
    distance_counts = data["edit_distance_count"].value_counts().sort_index()
    bars = ax.bar(distance_counts.index, distance_counts.values, color=PURPLE, width=0.72)
    mean_distance = data["edit_distance_count"].mean()
    median_distance = data["edit_distance_count"].median()
    ax.axvline(mean_distance, color=RED, linestyle="--", linewidth=1.4, label=f"Mean = {mean_distance:.2f}")
    ax.axvline(median_distance, color=GREEN, linestyle=":", linewidth=1.7, label=f"Median = {median_distance:.0f}")
    ax.set_title("C. Source character errors", loc="left")
    ax.set_xlabel("Source edit distance (character operations)")
    ax.set_ylabel("OCR observations (count)")
    ax.set_xticks(distance_counts.index)
    ax.grid(axis="y", color=LIGHT_GRAY, linewidth=0.65)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right")
    ax.bar_label(bars, padding=2, fontsize=6.8)

    outcomes = pd.Series(
        {
            "Correct at rank 1": int(data["hit_at_1"].sum()),
            "Found at ranks 2-20": int(data["rank_only_failure"].sum()),
            "Outside top 20": int(data["h20_failure"].sum()),
        }
    )
    ax = axes[1, 1]
    y = np.arange(len(outcomes))
    bars = ax.barh(y, outcomes.values, color=[GREEN, BLUE, RED], height=0.62)
    ax.set_title("D. Algorithm 4 outcome", loc="left")
    ax.set_yticks(y, outcomes.index)
    ax.invert_yaxis()
    ax.set_xlabel("OCR observations (count)")
    ax.set_ylabel("Mutually exclusive search outcome")
    ax.set_xlim(0, outcomes.max() * 1.30)
    style_bar_axis(ax)
    for bar, value in zip(bars, outcomes.values):
        ax.text(
            value + outcomes.max() * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{value} ({value / len(data) * 100:.1f}%)",
            va="center",
            fontsize=7.4,
        )

    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.91), h_pad=2.2, w_pad=2.0)
    fig.savefig(output / "00_dataset_overview.pdf", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def build_figures(data: pd.DataFrame, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for old_file in output.glob("*.pdf"):
        old_file.unlink()

    model_metrics = grouped_metrics(data, "source_model")
    target_metrics = grouped_metrics(data, "matched_canonical_name_norm")
    cohort_metrics = grouped_metrics(data, "analysis_cohort", COHORT_ORDER)
    distance_metrics = grouped_metrics(data, "distance_band", DISTANCE_ORDER)
    operation_metrics = grouped_metrics(data, "operation_profile", OPERATION_ORDER)
    query_length_metrics = grouped_metrics(data, "query_length_band", QUERY_LENGTH_ORDER)
    length_direction_metrics = grouped_metrics(data, "length_direction", LENGTH_DIRECTION_ORDER)
    extreme = data[data["analysis_cohort"] == "extreme_distance_prediction"]

    dataset_overview(output, data)

    count_bars(
        output,
        "01_dataset_inclusion",
        "Dataset inclusion and evaluation flow",
        f"Rows: {len(data)} input, {len(data)} mapped, {len(data)} evaluated. Extreme means compact normalized distance > 0.60.",
        [
            ("Source OCR observations", len(data)),
            ("Mapped to verified target", len(data)),
            ("Evaluated by Algorithm 4", len(data)),
            ("Extreme-distance observations", len(extreme)),
        ],
        xlabel="Rows (count)",
        ylabel="Pipeline stage",
    )

    repeated = data["edited_name"].value_counts().head(15)
    count_bars(
        output,
        "02_repeated_ocr_outputs",
        "Most frequently repeated OCR outputs",
        f"There are {data['edited_name'].nunique()} unique raw strings; mean repetition is {len(data) / data['edited_name'].nunique():.2f} rows per string.",
        list(repeated.items()),
        xlabel="OCR observations (count)",
        ylabel="Raw OCR output string",
        color=PURPLE,
    )
    count_bars(
        output,
        "03_ocr_model_coverage",
        "Observation coverage by OCR source model",
        f"All {data['source_model'].nunique()} models are retained; mean coverage is {len(data) / data['source_model'].nunique():.1f} rows per model.",
        [(row.label, row.n) for row in model_metrics.itertuples()],
        xlabel="OCR observations (count)",
        ylabel="OCR source model",
    )
    count_bars(
        output,
        "04_target_coverage",
        "Observation coverage by verified medicine target",
        f"All {data['matched_canonical_name_norm'].nunique()} targets are shown; mean coverage is {len(data) / data['matched_canonical_name_norm'].nunique():.1f} rows per target.",
        [(row.label, row.n) for row in target_metrics.itertuples()],
        xlabel="OCR observations (count)",
        ylabel="Verified medicine target",
        color=GREEN,
        two_panels=True,
    )
    count_bars(
        output,
        "05_analysis_cohorts",
        "Observation count by analysis cohort",
        "Priority: collision, exact, >0.60 extreme, limited evidence (n=0), fragment, >0.40 high, otherwise standard.",
        [(row.label, row.n) for row in cohort_metrics.itertuples()],
        xlabel="OCR observations (count)",
        ylabel="Analysis cohort",
        color=ORANGE,
    )

    source_distance = data["edit_distance_count"].value_counts().sort_index()
    distribution_bars(
        output,
        "06_source_edit_distance",
        "Source edit-distance distribution",
        f"Insertions + deletions + replacements; mean={data['edit_distance_count'].mean():.2f}, median={data['edit_distance_count'].median():.0f} edits.",
        [(str(int(key)), value) for key, value in source_distance.items()],
        xlabel="Source edit distance (character operations)",
    )
    ratio_bins = [-np.inf, 0.20, 0.40, 0.60, 0.80, 1.00, 1.50, np.inf]
    ratio_labels = ["<0.20", "0.20-0.39", "0.40-0.59", "0.60-0.79", "0.80-0.99", "1.00-1.49", "1.50+"]
    canonical_buckets = pd.cut(data["edit_distance_over_canonical_length"], bins=ratio_bins, labels=ratio_labels, right=False).value_counts(sort=False)
    output_buckets = pd.cut(data["edit_distance_over_edited_length"], bins=ratio_bins, labels=ratio_labels, right=False).value_counts(sort=False)
    distribution_bars(
        output,
        "07_distance_over_canonical",
        "Edit distance normalized by verified target length",
        f"Source edits / target length; mean={data['edit_distance_over_canonical_length'].mean():.3f}, median={data['edit_distance_over_canonical_length'].median():.3f}.",
        list(canonical_buckets.items()),
        xlabel="Edit distance / verified target length (ratio band)",
        color=PURPLE,
    )
    distribution_bars(
        output,
        "08_distance_over_ocr_output",
        "Edit distance normalized by OCR-output length",
        f"Source edits / OCR length; mean={data['edit_distance_over_edited_length'].mean():.3f}, median={data['edit_distance_over_edited_length'].median():.3f}.",
        list(output_buckets.items()),
        xlabel="Edit distance / OCR-output length (ratio band)",
        color=ORANGE,
    )
    similarity_bins = [-np.inf, 0, 0.20, 0.40, 0.60, 0.80, np.inf]
    similarity_labels = ["Below 0", "0.00-0.19", "0.20-0.39", "0.40-0.59", "0.60-0.79", "0.80-1.00"]
    similarity_buckets = pd.cut(data["similarity_over_canonical_length"], bins=similarity_bins, labels=similarity_labels, right=False).value_counts(sort=False)
    distribution_bars(
        output,
        "09_similarity_distribution",
        "Similarity to the verified target",
        f"Similarity = 1 - source edits / target length; mean={data['similarity_over_canonical_length'].mean():.3f}, median={data['similarity_over_canonical_length'].median():.3f}.",
        list(similarity_buckets.items()),
        xlabel="Similarity to verified target (ratio band)",
        color=GREEN,
    )

    for stem, title, field, xlabel, color in [
        ("10_ocr_output_length", "OCR-output length distribution", "edited_length", "OCR-output length (characters, including source spacing)", BLUE),
        ("11_canonical_length", "Verified target length distribution", "canonical_length", "Verified target length (characters, including source spacing)", GREEN),
        ("12_length_difference", "Target-minus-output length difference", "length_difference", "Verified target length - OCR-output length (characters)", PURPLE),
    ]:
        counts = data[field].value_counts().sort_index()
        distribution_bars(
            output,
            stem,
            title,
            (
                f"n={len(data)}; mean={data[field].mean():.2f}, median={data[field].median():.1f}, "
                f"range={int(data[field].min())} to {int(data[field].max())}."
            ),
            [(str(int(key)), value) for key, value in counts.items()],
            xlabel=xlabel,
            color=color,
        )

    operations = [
        ("Additions", data["additions_count"].sum()),
        ("Deletions", data["deletions_count"].sum()),
        ("Replacements / flips", data["flip_count"].sum()),
        ("Matches", data["matches_count"].sum()),
    ]
    count_bars(
        output,
        "13_operation_totals",
        "Character-alignment operation totals",
        (
            f"Totals across {len(data)} alignments; mean per row: "
            f"additions {data['additions_count'].mean():.2f}, "
            f"deletions {data['deletions_count'].mean():.2f}, "
            f"replacements {data['flip_count'].mean():.2f}, "
            f"matches {data['matches_count'].mean():.2f}."
        ),
        operations,
        xlabel="Alignment operations (count)",
        ylabel="Operation type",
    )
    operation_composition(output, data)
    signatures = data["operation_signature"].value_counts().head(15)
    count_bars(
        output,
        "15_operation_signatures",
        "Most common alignment-operation signatures",
        "M = match, I = insertion into OCR output, D = deletion, R = replacement.",
        list(signatures.items()),
        xlabel="OCR observations (count)",
        ylabel="Ordered operation signature",
        color=GREEN,
    )

    cumulative_recovery(output, data)
    outcomes = [
        ("Correct at rank 1", int(data["hit_at_1"].sum())),
        ("Found at ranks 2-20", int(data["rank_only_failure"].sum())),
        ("Expected target outside top 20", int(data["h20_failure"].sum())),
    ]
    count_bars(
        output,
        "17_algorithm_4_outcomes",
        "Mutually exclusive Algorithm 4 outcomes",
        f"The three bars partition all n={len(data)} observations.",
        outcomes,
        xlabel="OCR observations (count)",
        ylabel="Search outcome",
    )
    recovery_bars(output, "18_recovery_by_cohort", "Recovery by analysis cohort", f"All {len(data)} rows; priority: collision, exact, >0.60 extreme, fragment, >0.40 high, otherwise standard.", cohort_metrics, ylabel="Analysis cohort")
    recovery_bars(
        output,
        "19_recovery_by_model",
        "Recovery by OCR source model",
        (
            f"Inclusive model rates; overall Hit@1={100 * data['hit_at_1'].mean():.1f}% "
            f"and Hit@20={100 * data['hit_at_20'].mean():.1f}% across all {len(data)} rows."
        ),
        model_metrics,
        ylabel="OCR source model",
    )
    recovery_bars(output, "20_recovery_by_target", "Recovery by verified medicine target", "Inclusive target rates; unequal n means this is not a target-balanced comparison.", target_metrics, ylabel="Verified medicine target", two_panels=True)
    recovery_bars(output, "21_recovery_by_distance_band", "Recovery by compact edit-distance band", "Compact Levenshtein removes spaces/punctuation; bands contain 0, 1, 2-3, 4-5, or 6+ edits.", distance_metrics, ylabel="Compact edit-distance band")

    extreme_models = extreme["source_model"].value_counts()
    count_bars(output, "22_extreme_rows_by_model", "Extreme-distance observations by OCR model", f"Extreme = compact edit distance / target length >0.60; all n={len(extreme)} rows remain visible.", [(MODEL_LABELS.get(key, key), value) for key, value in extreme_models.items()], xlabel="Extreme-distance observations (count)", ylabel="OCR source model", color=ORANGE)
    extreme_targets = extreme["matched_canonical_name_norm"].value_counts()
    count_bars(output, "23_extreme_rows_by_target", "Extreme-distance observations by verified target", f"Extreme = compact edit distance / target length >0.60; n={len(extreme)} across displayed targets.", list(extreme_targets.items()), xlabel="Extreme-distance observations (count)", ylabel="Verified medicine target", color=RED, two_panels=True)
    extreme_outcomes = [
        ("Correct at rank 1", int(extreme["hit_at_1"].sum())),
        ("Found at ranks 2-20", int(extreme["rank_only_failure"].sum())),
        ("Expected target outside top 20", int(extreme["h20_failure"].sum())),
    ]
    count_bars(output, "24_extreme_recovery_outcomes", "Algorithm 4 outcomes on extreme predictions", f"The outcomes partition n={len(extreme)} rows whose compact normalized distance is >0.60.", extreme_outcomes, xlabel="Extreme-distance observations (count)", ylabel="Search outcome", color=RED)
    distance_similarity_scatter(output, data)
    exact_distance_recovery(output, data)
    recovery_bars(output, "27_recovery_by_operation_profile", "Recovery by character-operation profile", "Mixed = at least two of insertion, deletion, and replacement counts are nonzero in one row.", operation_metrics, ylabel="Character-operation profile")
    recovery_bars(output, "28_recovery_by_query_length", "Recovery by OCR-output length", "Length is source edited_length, including source spaces; fixed bands are shown on the y-axis.", query_length_metrics, ylabel="OCR-output length band")
    recovery_bars(output, "29_recovery_by_length_direction", "Recovery by output-versus-target length direction", "Difference = target length - OCR length: positive means OCR shorter, zero means equal.", length_direction_metrics, ylabel="Relative string length")

    raw_by_model = grouped_metrics(data, "source_model")
    standard_by_model = grouped_metrics(data[data["analysis_cohort"] == "standard_ocr_error"], "source_model")[["key", "h1"]].rename(columns={"h1": "standard_h1"})
    case_mix = raw_by_model.merge(standard_by_model, on="key", how="left")
    case_mix = case_mix.rename(columns={"h1": "raw_h1"}).sort_values("raw_h1", ascending=False)
    comparison_bars(output, "30_model_case_mix_comparison", "Raw versus standard-error-only model recovery", "Standard errors have normalized distance <=0.40 and are not exact, fragments, or collisions.", case_mix, first_field="raw_h1", second_field="standard_h1", first_label="Raw Hit@1", second_label="Standard-error-only Hit@1", ylabel="OCR source model")

    unique = data.drop_duplicates(["compact_query", "expected_family_key"], keep="first")
    scored = data[data["scored_case"] == 1]
    unique_scored = unique[unique["scored_case"] == 1]
    denominator_metrics = pd.DataFrame(
        [
            {"label": "All observations", "n": len(data), "h1": data["hit_at_1"].mean(), "h20": data["hit_at_20"].mean()},
            {"label": "Scored observations", "n": len(scored), "h1": scored["hit_at_1"].mean(), "h20": scored["hit_at_20"].mean()},
            {"label": "All unique query-target pairs", "n": len(unique), "h1": unique["hit_at_1"].mean(), "h20": unique["hit_at_20"].mean()},
            {"label": "Scored unique pairs (primary)", "n": len(unique_scored), "h1": unique_scored["hit_at_1"].mean(), "h20": unique_scored["hit_at_20"].mean()},
        ]
    )
    recovery_bars(output, "31_duplicate_sensitivity", "Metric changes under four denominators", "Scored excludes 17 real-drug collisions; unique counts each compact query-target pair once.", denominator_metrics, ylabel="Evaluation denominator")
    primary_split_metrics = grouped_metrics(unique_scored, "split", ["development", "holdout"])
    recovery_bars(output, "32_split_recovery", "Primary recovery by development and holdout split", "Primary denominator: 464 scored unique pairs; target hashing keeps one family in one split.", primary_split_metrics, ylabel="Target-family-disjoint split")

    impact_bars(output, "33_failure_impact_by_cohort", "Top-20 failure rate and total impact by cohort", "Orange divides misses by cohort rows; red divides cohort misses by all top-20 misses.", impact_metrics(data, "analysis_cohort", "h20_failure", COHORT_ORDER), ylabel="Analysis cohort")
    impact_bars(output, "34_failure_impact_by_distance", "Top-20 failure rate and total impact by compact distance", "Rate measures subgroup difficulty; share measures contribution to the benchmark's total failures.", impact_metrics(data, "distance_band", "h20_failure", DISTANCE_ORDER), ylabel="Compact edit-distance band")
    impact_bars(output, "35_failure_impact_by_operation", "Top-20 failure rate and total impact by operation profile", f"Rate and impact use the same {int(data['h20_failure'].sum())} top-20 failures but answer different questions.", impact_metrics(data, "operation_profile", "h20_failure", OPERATION_ORDER), ylabel="Character-operation profile")
    impact_bars(output, "36_failure_impact_by_length", "Top-20 failure rate and total impact by OCR-output length", "Short strings can have high failure rates without producing the largest absolute miss count.", impact_metrics(data, "query_length_band", "h20_failure", QUERY_LENGTH_ORDER), ylabel="OCR-output length band")
    impact_bars(output, "37_failure_impact_by_model", "Top-20 failure rate and total impact by OCR model", "Model-level impact combines model quality, observation count, target mix, and error severity.", impact_metrics(data, "source_model", "h20_failure"), ylabel="OCR source model")
    target_impact = impact_metrics(data, "matched_canonical_name_norm", "h20_failure").head(12)
    impact_bars(output, "38_failure_impact_by_target", "Targets with the largest top-20 failure impact", f"The figure shows the 12 targets contributing the most misses; red bars sum against all {int(data['h20_failure'].sum())} misses.", target_impact, ylabel="Verified medicine target")
    impact_bars(output, "39_ranking_failure_impact", "Rank-only failure rate and impact by cohort", "A rank-only failure means the target exists at ranks 2-20 but not rank 1; impact uses all rank-only failures.", impact_metrics(data, "analysis_cohort", "rank_only_failure", COHORT_ORDER), ylabel="Analysis cohort")

    generated = sorted(output.glob("*.pdf"))
    if len(generated) != 40:
        raise RuntimeError(f"expected 40 figures, generated {len(generated)}")


def main() -> None:
    args = parse_args()
    configure_style()
    data = load_data(args.source, args.results)
    build_figures(data, args.output)
    print(f"Generated 40 paper figures from {len(data)} joined observations in {args.output}")


if __name__ == "__main__":
    main()
