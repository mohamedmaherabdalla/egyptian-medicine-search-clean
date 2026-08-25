#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
latex_dir="$repo_root/algorithm_6_rule_evaluation/latex"
output_dir="$repo_root/output/pdf"

mkdir -p "$output_dir"
cd "$latex_dir"
latexmk -xelatex -interaction=nonstopmode -halt-on-error \
  -output-directory="$output_dir" \
  team_handbook.tex

cp "$output_dir/team_handbook.pdf" \
  "$output_dir/medicine_search_team_handbook.pdf"
