#!/usr/bin/env bash
set -u

BASE_URL="http://www.drugeye.pharorg.com/drugeyeapp/android-search/drugeye-android-live-go.aspx"
MODE="trade"
QUERIES=""
HTML_DIR=""
SLEEP_SECONDS="0.15"
TIMEOUT_SECONDS="20"
START_AT="1"
LIMIT_COUNT="0"
REFRESH_EVERY="200"

usage() {
  cat <<'EOF'
Usage:
  fetch_drugeye_html_cache.sh --queries queries.tsv --html-dir /tmp/drugeye_html [options]

Options:
  --mode trade|fuzzy|ingredient|price|pharmacology
  --sleep seconds
  --timeout seconds
  --start one_based_line
  --limit count
  --refresh-every count
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --queries) QUERIES="$2"; shift 2 ;;
    --html-dir) HTML_DIR="$2"; shift 2 ;;
    --sleep) SLEEP_SECONDS="$2"; shift 2 ;;
    --timeout) TIMEOUT_SECONDS="$2"; shift 2 ;;
    --start) START_AT="$2"; shift 2 ;;
    --limit) LIMIT_COUNT="$2"; shift 2 ;;
    --refresh-every) REFRESH_EVERY="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$QUERIES" || -z "$HTML_DIR" ]]; then
  usage >&2
  exit 2
fi

case "$MODE" in
  trade) BUTTON_NAME="b1"; BUTTON_VALUE="search" ;;
  fuzzy) BUTTON_NAME="BtnSearchEx"; BUTTON_VALUE="Ex" ;;
  ingredient) BUTTON_NAME="BG"; BUTTON_VALUE="G" ;;
  price) BUTTON_NAME="BP"; BUTTON_VALUE="P" ;;
  pharmacology) BUTTON_NAME="Button1"; BUTTON_VALUE="PH" ;;
  *) echo "Unsupported mode: $MODE" >&2; exit 2 ;;
esac

mkdir -p "$HTML_DIR"
COOKIE_FILE="$HTML_DIR/${MODE}_cookies.txt"
GET_FILE="$HTML_DIR/${MODE}_form.html"
LOG_FILE="$HTML_DIR/${MODE}_fetch_log.tsv"

VIEWSTATE=""
VIEWSTATEGENERATOR=""
EVENTVALIDATION=""

extract_value() {
  local name="$1"
  local file="$2"
  sed -n "s/.*name=\"$name\"[^>]*value=\"\([^\"]*\)\".*/\1/p" "$file" | head -n 1
}

refresh_form() {
  curl -sS --max-time "$TIMEOUT_SECONDS" -c "$COOKIE_FILE" -o "$GET_FILE" "$BASE_URL"
  VIEWSTATE="$(extract_value "__VIEWSTATE" "$GET_FILE")"
  VIEWSTATEGENERATOR="$(extract_value "__VIEWSTATEGENERATOR" "$GET_FILE")"
  EVENTVALIDATION="$(extract_value "__EVENTVALIDATION" "$GET_FILE")"
  if [[ -z "$VIEWSTATE" || -z "$EVENTVALIDATION" ]]; then
    echo "Failed to extract ASP.NET form fields from $GET_FILE" >&2
    return 1
  fi
}

line_number=0
processed=0
fetched=0
skipped=0
refresh_counter=999999

printf 'timestamp\tline\tid\thttp_code\tbytes\tquery\n' > "$LOG_FILE"

while IFS=$'\t' read -r query_id query; do
  line_number=$((line_number + 1))
  if (( line_number < START_AT )); then
    continue
  fi
  if (( LIMIT_COUNT > 0 && processed >= LIMIT_COUNT )); then
    break
  fi
  processed=$((processed + 1))

  out_file="$HTML_DIR/${MODE}_${query_id}.html"
  tmp_file="$out_file.tmp"

  if [[ -s "$out_file" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  if (( refresh_counter >= REFRESH_EVERY )); then
    if ! refresh_form; then
      printf '%s\t%d\t%s\tFORM_ERROR\t0\t%s\n' "$(date -u +%FT%TZ)" "$line_number" "$query_id" "$query" >> "$LOG_FILE"
      sleep "$SLEEP_SECONDS"
      continue
    fi
    refresh_counter=0
  fi

  http_code="$(
    curl -sS --max-time "$TIMEOUT_SECONDS" -b "$COOKIE_FILE" \
      --data-urlencode "__VIEWSTATE=$VIEWSTATE" \
      --data-urlencode "__VIEWSTATEGENERATOR=$VIEWSTATEGENERATOR" \
      --data-urlencode "__EVENTVALIDATION=$EVENTVALIDATION" \
      --data-urlencode "ttt=$query" \
      --data-urlencode "$BUTTON_NAME=$BUTTON_VALUE" \
      --data-urlencode "Passgenericname=" \
      -w "%{http_code}" -o "$tmp_file" "$BASE_URL" || printf "CURL_ERROR"
  )"

  bytes=0
  if [[ -f "$tmp_file" ]]; then
    bytes="$(wc -c < "$tmp_file" | tr -d ' ')"
  fi

  if [[ "$http_code" == "200" && -s "$tmp_file" ]]; then
    mv "$tmp_file" "$out_file"
    fetched=$((fetched + 1))
  else
    rm -f "$tmp_file"
  fi

  printf '%s\t%d\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$line_number" "$query_id" "$http_code" "$bytes" "$query" >> "$LOG_FILE"

  refresh_counter=$((refresh_counter + 1))
  if (( processed % 100 == 0 )); then
    echo "processed=$processed fetched=$fetched skipped=$skipped line=$line_number" >&2
  fi
  sleep "$SLEEP_SECONDS"
done < "$QUERIES"

echo "done processed=$processed fetched=$fetched skipped=$skipped html_dir=$HTML_DIR" >&2
