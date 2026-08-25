#!/usr/bin/env python3
"""Generate LaTeX tables from executable Algorithm 6 manifests/registries."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "algorithm_6_rule_evaluation"
GENERATED = PACKAGE / "latex" / "generated"
MANIFEST = PACKAGE / "test_sets" / "manifests" / "generation_manifest.json"
REGISTRY = PACKAGE / "test_sets" / "generated" / "rule_registry.csv"
REGISTRY_MANIFEST = (
    PACKAGE / "test_sets" / "generated" / "rule_registry.manifest.json"
)


def escape(value: object) -> str:
    text = str(value or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "≤": r"$\leq$",
        "≥": r"$\geq$",
        "→": r"$\rightarrow$",
        "↔": r"$\leftrightarrow$",
    }
    return "".join(replacements.get(character, character) for character in text)


def breakable(value: object) -> str:
    """Escape prose while exposing safe wrap points in code-shaped tokens."""
    return (
        escape(value)
        .replace(r"\_", r"\_\allowbreak{}")
        .replace("/", r"/\allowbreak{}")
    )


def write_manifest_table() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = list(manifest["generated_files"])
    registry_manifest = json.loads(REGISTRY_MANIFEST.read_text(encoding="utf-8"))
    rows.append(
        {
            "file": str(REGISTRY.relative_to(REPO)),
            "rows": registry_manifest["row_count"],
            "sha256": registry_manifest["csv_sha256"],
        }
    )
    lines = [
        r"\begin{longtable}{@{}p{2.75in}r p{2.9in}@{}}",
        r"\toprule",
        r"Generated file & Rows & SHA-256 \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in rows:
        name = Path(row["file"]).name
        lines.append(
            f"{escape(name)} & {row['rows']:,} & "
            f"\\texttt{{\\scriptsize \\seqsplit{{{escape(row['sha256'])}}}}} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{longtable}", ""])
    (GENERATED / "test_set_manifest_table.tex").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def first(row: dict[str, str], *names: str) -> str:
    return next((row.get(name, "") for name in names if row.get(name, "")), "")


def write_registry_table() -> None:
    if not REGISTRY.exists():
        raise SystemExit(f"missing rule registry: {REGISTRY}")
    with REGISTRY.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    lines = [
        r"\begingroup",
        r"\setlength{\parskip}{0pt}",
        r"\small",
    ]
    previous_subsystem = ""
    for row in rows:
        rule_id = first(row, "rule_id", "id")
        subsystem = first(row, "subsystem", "area")
        status = first(row, "status")
        exact_rule = first(row, "exact_rule", "rule", "description")
        threshold = first(row, "threshold_or_value", "threshold")
        if threshold:
            exact_rule = f"{exact_rule} Threshold/value: {threshold}"
        source = "; ".join(
            value
            for value in (
                first(row, "source_symbols", "source", "implementation"),
                first(row, "source_files"),
                (
                    f"Rulebook {first(row, 'rulebook_section')}"
                    if first(row, "rulebook_section")
                    else ""
                ),
            )
            if value
        )
        coverage_status = first(row, "coverage_status", "coverage")
        tests = "; ".join(
            f"{label}: {value}"
            for label, value in (
                ("P", first(row, "positive_test_coverage", "positive_tests")),
                ("N", first(row, "negative_test_coverage", "negative_tests")),
                ("B", first(row, "boundary_test_coverage", "boundary_tests")),
            )
            if value
        ) or first(row, "test_coverage", "tests")
        gap = first(row, "coverage_gap", "gap")
        coverage = "; ".join(value for value in (coverage_status, tests, gap) if value)
        if subsystem != previous_subsystem:
            if previous_subsystem:
                lines.append(r"\medskip")
            lines.append(
                rf"\subsection*{{{breakable(subsystem.replace('_', ' '))}}}"
            )
            previous_subsystem = subsystem
        lines.extend(
            [
                r"\begin{tcolorbox}[enhanced,breakable,colback=white,colframe=Muted!45,"
                r"boxrule=0.45pt,arc=1.5pt,left=6pt,right=6pt,top=5pt,bottom=5pt,"
                rf"title={{\texttt{{{breakable(rule_id)}}}}},"
                rf"title after break={{\texttt{{{breakable(rule_id)}}}\ (continued)}},"
                r"fonttitle=\headingfont\bfseries\color{Navy},coltitle=Navy]",
                rf"\textbf{{Area/status:}} {breakable(subsystem)} $\boldsymbol{{\cdot}}$ {breakable(status)}\par",
                r"\smallskip",
                rf"\textbf{{Exact rule / threshold:}} {breakable(exact_rule)}\par",
                r"\smallskip",
                rf"\textbf{{Implementation source:}} {breakable(source)}\par",
                r"\smallskip",
                rf"\textbf{{Coverage / gap:}} {breakable(coverage)}",
                r"\end{tcolorbox}",
            ]
        )
    lines.extend([r"\endgroup", ""])
    (GENERATED / "rule_registry_table.tex").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def normalize_pandoc_rulebook_tables() -> None:
    """Replace Pandoc's natural-width columns with bounded wrapping columns."""
    path = GENERATED / "complete_rulebook.tex"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    ragged = r">{\RaggedRight\arraybackslash}"
    widths = {
        "ll": (".27", ".66"),
        "lr": (".70", ".20"),
        "lll": (".22", ".34", ".36"),
        "llr": (".45", ".25", ".18"),
        "lrr": (".45", ".20", ".20"),
        "rrr": (".28", ".28", ".28"),
        "llrl": (".24", ".24", ".14", ".23"),
        "lrlr": (".26", ".15", ".28", ".15"),
        "lrrrl": (".27", ".12", ".15", ".16", ".22"),
        "lrlrlr": (".16", ".10", ".16", ".10", ".16", ".10"),
    }
    for source_spec, column_widths in widths.items():
        bounded = "".join(
            f"{ragged}p{{{width}\\linewidth}}" for width in column_widths
        )
        text = text.replace(
            rf"\begin{{longtable}}[]{{@{{}}{source_spec}@{{}}}}",
            rf"\begin{{longtable}}[]{{@{{}}{bounded}@{{}}}}",
        )
    protected_break = "\x00BREAKABLE_UNDERSCORE\x00"
    text = text.replace(r"\_\allowbreak{}", protected_break)
    text = text.replace(r"\_", r"\_\allowbreak{}")
    text = text.replace(protected_break, r"\_\allowbreak{}")
    protected_hashes: list[str] = []

    def protect_hash(match: re.Match[str]) -> str:
        protected_hashes.append(match.group(1))
        return f"@@SEQHASH{len(protected_hashes) - 1}@@"

    text = re.sub(r"\\seqsplit\{([0-9a-f]{64})\}", protect_hash, text)
    text = re.sub(
        r"(?<![0-9a-f])([0-9a-f]{64})(?![0-9a-f])",
        lambda match: rf"\seqsplit{{{match.group(1)}}}",
        text,
    )
    for index, value in enumerate(protected_hashes):
        text = text.replace(f"@@SEQHASH{index}@@", rf"\seqsplit{{{value}}}")
    natural_tables = re.findall(
        r"\\begin\{longtable\}\[\]\{@\{\}[lcr]+@\{\}\}", text
    )
    if natural_tables:
        raise RuntimeError(
            "unbounded Pandoc longtable specifications remain after normalization: "
            + ", ".join(sorted(set(natural_tables)))
        )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    write_manifest_table()
    write_registry_table()
    normalize_pandoc_rulebook_tables()
    print(f"Generated LaTeX fragments in {GENERATED}")


if __name__ == "__main__":
    main()
