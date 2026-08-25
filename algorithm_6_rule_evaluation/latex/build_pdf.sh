#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
package_dir="$(cd "${script_dir}/.." && pwd)"
repo_root="$(cd "${package_dir}/.." && pwd)"
generated_dir="${script_dir}/generated"
output_dir="${repo_root}/output/pdf"

command -v pandoc >/dev/null
command -v latexmk >/dev/null
command -v xelatex >/dev/null

python_bin="${PYTHON_BIN:-}"
if [[ -n "${python_bin}" ]]; then
  if [[ "$("${python_bin}" -c 'print("algorithm-6-python-ok")' 2>/dev/null)" != \
    "algorithm-6-python-ok" ]]; then
    printf 'PYTHON_BIN does not identify a working Python interpreter: %s\n' \
      "${python_bin}" >&2
    exit 1
  fi
else
  for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 python3; do
    if [[ "$("${candidate}" -c 'print("algorithm-6-python-ok")' 2>/dev/null)" == \
      "algorithm-6-python-ok" ]]; then
      python_bin="${candidate}"
      break
    fi
  done
fi
if [[ -z "${python_bin}" ]]; then
  printf 'No working Python 3 interpreter was found.\n' >&2
  exit 1
fi

mkdir -p "${generated_dir}" "${output_dir}"

pandoc "${repo_root}/docs/ALGORITHM_6_COMPLETE_RULEBOOK.md" \
  -f gfm -t latex --top-level-division=chapter --wrap=preserve \
  --syntax-highlighting=none \
  -o "${generated_dir}/complete_rulebook.tex"

pandoc "${package_dir}/results/failure_history.md" \
  -f gfm -t latex --top-level-division=section \
  --shift-heading-level-by=1 --wrap=preserve --syntax-highlighting=none \
  -o "${generated_dir}/failure_history.tex"

PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/a6-rule-pyc" \
  "${python_bin}" -B "${package_dir}/generators/generate_latex_fragments.py"

if rg -q '\\begin\{longtable\}\[\]\{@\{\}[lcr]+@\{\}\}' \
  "${generated_dir}/complete_rulebook.tex"; then
  printf 'Unbounded Pandoc longtable survived LaTeX normalization.\n' >&2
  exit 1
fi

cd "${script_dir}"
latexmk -xelatex -interaction=nonstopmode -halt-on-error -silent \
  -outdir="${output_dir}" algorithm_6_rule_evaluation.tex

printf 'Built %s\n' "${output_dir}/algorithm_6_rule_evaluation.pdf"
