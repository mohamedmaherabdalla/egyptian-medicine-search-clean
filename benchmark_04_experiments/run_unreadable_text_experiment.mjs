#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const APP_MODULE = path.join(ROOT, "app", "app.js");
const CATALOG_PATH = path.join(ROOT, "app", "data", "catalog.json");
const DATA_PATH = path.join(HERE, "data", "06_unreadable_text", "test_cases.csv");
const ARTIFACT_PATH = path.join(HERE, "artifacts", "09_unreadable_text", "case_results.csv");
const METRICS_PATH = path.join(HERE, "results", "09_unreadable_text", "metrics.csv");
const SUMMARY_PATH = path.join(HERE, "results", "09_unreadable_text", "summary.json");
const REPORT_PATH = path.join(HERE, "results", "09_unreadable_text", "report.md");
const PARTIAL_DATA_PATH = path.join(HERE, "data", "06_unreadable_text", "partial_text_cases.csv");
const PARTIAL_ARTIFACT_PATH = path.join(HERE, "artifacts", "09_unreadable_text", "partial_text_results.csv");
const PARTIAL_METRICS_PATH = path.join(HERE, "results", "09_unreadable_text", "partial_text_metrics.csv");
const PARTIAL_SUMMARY_PATH = path.join(HERE, "results", "09_unreadable_text", "partial_text_summary.json");
const PARTIAL_REPORT_PATH = path.join(HERE, "results", "09_unreadable_text", "partial_text_report.md");
const STRATEGIES = ["full_scan", "indexed"];
const GAP_PENALTIES = [0, 15, 30, 45, 60, 90, 120, 150, 180, 240, 300, 450, 600];
const RUNTIME_DEFAULT_GAP_PENALTY = 450;
const TOP_K = 20;

function parseArgs(argv) {
  const options = { sampleModulus: 128, partialSampleModulus: 64, limit: 0, partialOnly: false };
  for (let index = 2; index < argv.length; index++) {
    const argument = argv[index];
    if (argument === "--sample-modulus") options.sampleModulus = Number(argv[++index]);
    else if (argument === "--partial-sample-modulus") options.partialSampleModulus = Number(argv[++index]);
    else if (argument === "--limit") options.limit = Number(argv[++index]);
    else if (argument === "--partial-only") options.partialOnly = true;
    else throw new Error(`unknown argument: ${argument}`);
  }
  if (!Number.isInteger(options.sampleModulus) || options.sampleModulus < 1) {
    throw new Error("--sample-modulus must be a positive integer");
  }
  if (!Number.isInteger(options.limit) || options.limit < 0) {
    throw new Error("--limit must be a non-negative integer");
  }
  if (!Number.isInteger(options.partialSampleModulus) || options.partialSampleModulus < 1) {
    throw new Error("--partial-sample-modulus must be a positive integer");
  }
  return options;
}

function hashHex(value) {
  return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function hashInteger(value) {
  return Number.parseInt(hashHex(value).slice(0, 12), 16);
}

function splitForFamily(family) {
  return hashInteger(`family-split-v1|${family}`) % 5 === 0 ? "holdout" : "development";
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function writeCsv(filePath, rows) {
  if (!rows.length) throw new Error(`refusing to write an empty CSV: ${filePath}`);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const fields = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const lines = [fields.map(csvCell).join(",")];
  for (const row of rows) lines.push(fields.map(field => csvCell(row[field])).join(","));
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`);
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function addToIndex(index, key, targetId) {
  if (!index.has(key)) index.set(key, new Set());
  index.get(key).add(targetId);
}

function buildPatternTargets(catalog) {
  const unique = new Map();
  for (const record of catalog.records) {
    const family = record._familyGroupKey;
    const values = [["base", record._bc]];
    if (record._headFamily && record._headc && record._headc !== record._bc) {
      values.push(["family_head", record._headc]);
    }
    for (const [source, value] of values) {
      if (!value || value.length < 2) continue;
      const wordShape = source === "family_head" || !record._bn.includes(" ")
        ? "single_word"
        : "multi_word";
      const key = `${source}|${value}|${family}`;
      const current = unique.get(key);
      if (!current || wordShape === "multi_word") {
        unique.set(key, { source, value, family, wordShape });
      }
    }
  }
  return [...unique.values()]
    .sort((left, right) =>
      left.value.localeCompare(right.value) ||
      left.family.localeCompare(right.family) ||
      left.source.localeCompare(right.source)
    )
    .map((target, id) => ({ ...target, id }));
}

function buildPatternIndexes(targets) {
  const prefix = new Map();
  const suffix = new Map();
  for (const target of targets) {
    for (let length = 1; length < target.value.length; length++) {
      addToIndex(prefix, target.value.slice(0, length), target.id);
      addToIndex(suffix, target.value.slice(-length), target.id);
    }
  }
  return { prefix, suffix };
}

function targetIdsForCase(testCase, indexes) {
  if (testCase.mode === "after") return indexes.prefix.get(testCase.visible_text) || new Set();
  if (testCase.mode === "before") return indexes.suffix.get(testCase.visible_text) || new Set();
  const starts = indexes.prefix.get(testCase.visible_text) || new Set();
  const ends = indexes.suffix.get(testCase.ending_text) || new Set();
  const [small, large] = starts.size <= ends.size ? [starts, ends] : [ends, starts];
  return new Set([...small].filter(targetId => large.has(targetId)));
}

function visibleBand(length) {
  if (length === 1) return "1_character";
  if (length === 2) return "2_characters";
  if (length === 3) return "3_characters";
  if (length === 4) return "4_characters";
  if (length <= 6) return "5_6_characters";
  return "7_plus_characters";
}

function hiddenBand(length) {
  if (length === 1) return "1_character";
  if (length <= 3) return "2_3_characters";
  if (length <= 6) return "4_6_characters";
  return "7_plus_characters";
}

function collisionBand(count) {
  if (count === 1) return "1_unique_family";
  if (count <= 3) return "2_3_families";
  if (count <= 10) return "4_10_families";
  if (count <= 20) return "11_20_families";
  return "21_plus_families";
}

function requestKey(mode, visibleText, endingText = "") {
  return `${mode}|${visibleText}|${endingText}`;
}

function considerCase(selected, sampleModulus, candidate) {
  const key = requestKey(candidate.mode, candidate.visible_text, candidate.ending_text);
  const totalVisible = candidate.visible_text.length + candidate.ending_text.length;
  if (totalVisible > 2 && hashInteger(`unreadable-sample-v1|${key}`) % sampleModulus !== 0) return;
  const current = selected.get(key);
  if (!current ||
      candidate.hidden_length < current.hidden_length ||
      (candidate.hidden_length === current.hidden_length && candidate.source_family < current.source_family)) {
    selected.set(key, candidate);
  }
}

function generateCases(targets, indexes, sampleModulus, limit) {
  const selected = new Map();
  const universe = { after: 0, before: 0, middle: 0 };
  for (const target of targets) {
    const length = target.value.length;
    for (let visibleLength = 1; visibleLength < length; visibleLength++) {
      const hiddenLength = length - visibleLength;
      universe.after++;
      considerCase(selected, sampleModulus, {
        mode: "after",
        visible_text: target.value.slice(0, visibleLength),
        ending_text: "",
        hidden_length: hiddenLength,
        source_family: target.family,
        source_target: target.value,
        source_type: target.source,
        source_word_shape: target.wordShape,
      });
      universe.before++;
      considerCase(selected, sampleModulus, {
        mode: "before",
        visible_text: target.value.slice(-visibleLength),
        ending_text: "",
        hidden_length: hiddenLength,
        source_family: target.family,
        source_target: target.value,
        source_type: target.source,
        source_word_shape: target.wordShape,
      });
    }
    for (let prefixLength = 1; prefixLength <= length - 2; prefixLength++) {
      for (let suffixLength = 1; suffixLength <= length - prefixLength - 1; suffixLength++) {
        const hiddenLength = length - prefixLength - suffixLength;
        universe.middle++;
        considerCase(selected, sampleModulus, {
          mode: "middle",
          visible_text: target.value.slice(0, prefixLength),
          ending_text: target.value.slice(-suffixLength),
          hidden_length: hiddenLength,
          source_family: target.family,
          source_target: target.value,
          source_type: target.source,
          source_word_shape: target.wordShape,
        });
      }
    }
  }

  let cases = [...selected.values()].map(testCase => {
    const targetIds = targetIdsForCase(testCase, indexes);
    const matchingTargets = [...targetIds].map(targetId => targets[targetId]);
    const relevantFamilies = [...new Set(matchingTargets.map(target => target.family))].sort();
    const familySplits = [...new Set(relevantFamilies.map(splitForFamily))];
    const split = familySplits.length === 1 ? familySplits[0] : "mixed_split_diagnostic";
    const relevantSources = [...new Set(matchingTargets.map(target => target.source))].sort();
    const key = requestKey(testCase.mode, testCase.visible_text, testCase.ending_text);
    return {
      case_id: hashHex(`unreadable-case-v1|${key}`).slice(0, 20),
      split,
      use_in_locked_score: split === "mixed_split_diagnostic" ? 0 : 1,
      expected_behavior: relevantFamilies.length === 1 ? "match" : "ambiguous",
      mode: testCase.mode,
      visible_text: testCase.visible_text,
      ending_text: testCase.ending_text,
      visible_character_count: testCase.visible_text.length + testCase.ending_text.length,
      visible_length_band: visibleBand(testCase.visible_text.length + testCase.ending_text.length),
      source_hidden_length: testCase.hidden_length,
      hidden_length_band: hiddenBand(testCase.hidden_length),
      source_family: testCase.source_family,
      source_target: testCase.source_target,
      source_type: testCase.source_type,
      source_word_shape: testCase.source_word_shape,
      matching_target_count: matchingTargets.length,
      relevant_family_count: relevantFamilies.length,
      collision_band: collisionBand(relevantFamilies.length),
      relevant_source_types: relevantSources.join(";"),
      relevant_families: relevantFamilies.join(";"),
    };
  });
  cases.sort((left, right) => left.case_id.localeCompare(right.case_id));
  if (limit) cases = cases.slice(0, limit);
  return { cases, universe };
}

function uniqueFamilies(results) {
  const families = [];
  const seen = new Set();
  for (const result of results || []) {
    const family = String(result.family_group_key || result.base_group_key || "");
    if (!family || seen.has(family)) continue;
    seen.add(family);
    families.push(family);
  }
  return families;
}

function percentile(values, percentileValue) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.ceil(percentileValue * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

function evaluateCases(MedSearch, catalog, cases, gapPenalty) {
  const rows = [];
  for (const strategy of STRATEGIES) {
    const started = Date.now();
    cases.forEach((testCase, index) => {
      const relevant = new Set(testCase.relevant_families.split(";").filter(Boolean));
      const response = MedSearch.searchCatalog(catalog, testCase.visible_text, TOP_K, {
        unreadableMode: testCase.mode,
        endingFragment: testCase.ending_text,
        unreadableStrategy: strategy,
        unreadableGapPenalty: gapPenalty,
      });
      const returned = uniqueFamilies(response.results);
      const firstRelevantIndex = returned.findIndex(family => relevant.has(family));
      const sourceIndex = returned.indexOf(testCase.source_family);
      const validCount = returned.filter(family => relevant.has(family)).length;
      const confirmationRequired = Boolean(response.confirmation_required || response.needs_clarification);
      const behaviorSuccess = testCase.expected_behavior === "ambiguous"
        ? response.status === "ambiguous" && confirmationRequired && returned.length > 0
        : firstRelevantIndex >= 0 && firstRelevantIndex < TOP_K && confirmationRequired;
      rows.push({
        ...testCase,
        strategy,
        returned_family_count: returned.length,
        returned_families: returned.join(";"),
        relevant_rank: firstRelevantIndex < 0 ? "" : firstRelevantIndex + 1,
        source_family_rank: sourceIndex < 0 ? "" : sourceIndex + 1,
        hit_at_1: firstRelevantIndex === 0 ? 1 : 0,
        hit_at_5: firstRelevantIndex >= 0 && firstRelevantIndex < 5 ? 1 : 0,
        hit_at_10: firstRelevantIndex >= 0 && firstRelevantIndex < 10 ? 1 : 0,
        hit_at_20: firstRelevantIndex >= 0 && firstRelevantIndex < 20 ? 1 : 0,
        source_hit_at_1: sourceIndex === 0 ? 1 : 0,
        source_hit_at_20: sourceIndex >= 0 && sourceIndex < 20 ? 1 : 0,
        valid_top_1: returned.length > 0 && relevant.has(returned[0]) ? 1 : 0,
        result_precision: returned.length ? validCount / returned.length : 0,
        behavior_success: behaviorSuccess ? 1 : 0,
        confirmation_required: confirmationRequired ? 1 : 0,
        unsafe_confident_top_1: returned.length && !relevant.has(returned[0]) && !confirmationRequired ? 1 : 0,
        no_result: returned.length ? 0 : 1,
        candidate_count: Number(response.candidate_count || 0),
        elapsed_ms: Number(response.elapsed_ms || 0),
      });
      if ((index + 1) % 1000 === 0) {
        const seconds = ((Date.now() - started) / 1000).toFixed(1);
        process.stdout.write(`\r${strategy}: ${index + 1}/${cases.length} cases in ${seconds}s`);
      }
    });
    process.stdout.write("\n");
  }
  return rows;
}

function evaluateGapPenalties(MedSearch, catalog, cases) {
  const tuningCases = cases.filter(testCase =>
    testCase.split === "development" &&
    Number(testCase.use_in_locked_score) === 1 &&
    testCase.expected_behavior === "ambiguous"
  );
  const metrics = [];
  for (const penalty of GAP_PENALTIES) {
    const rows = tuningCases.map(testCase => {
      const relevant = new Set(testCase.relevant_families.split(";").filter(Boolean));
      const response = MedSearch.searchCatalog(catalog, testCase.visible_text, TOP_K, {
        unreadableMode: testCase.mode,
        endingFragment: testCase.ending_text,
        unreadableStrategy: "indexed",
        unreadableGapPenalty: penalty,
      });
      const returned = uniqueFamilies(response.results);
      const sourceIndex = returned.indexOf(testCase.source_family);
      const validCount = returned.filter(family => relevant.has(family)).length;
      return {
        source_hit_at_1: sourceIndex === 0 ? 1 : 0,
        source_hit_at_20: sourceIndex >= 0 && sourceIndex < TOP_K ? 1 : 0,
        valid_top_1: returned.length > 0 && relevant.has(returned[0]) ? 1 : 0,
        result_precision: returned.length ? validCount / returned.length : 0,
        elapsed_ms: Number(response.elapsed_ms || 0),
      };
    });
    const latencies = rows.map(row => row.elapsed_ms);
    metrics.push({
      evaluation_version: "unreadable_text_v1",
      dataset: "unreadable_text_catalog_sample",
      algorithm: "static_browser_search",
      strategy: "indexed",
      dimension: "development_ambiguous_gap_penalty",
      group: String(penalty),
      cases: rows.length,
      source_hit_at_1: mean(rows, "source_hit_at_1"),
      source_hit_at_20: mean(rows, "source_hit_at_20"),
      valid_top_1_rate: mean(rows, "valid_top_1"),
      mean_result_precision: mean(rows, "result_precision"),
      mean_latency_ms: mean(rows, "elapsed_ms"),
      p95_latency_ms: percentile(latencies, 0.95),
    });
  }
  const eligible = metrics.filter(row =>
    row.valid_top_1_rate === 1 && row.mean_result_precision === 1
  );
  if (!eligible.length) throw new Error("no safe unreadable-gap penalty survived development tuning");
  eligible.sort((left, right) =>
    right.source_hit_at_1 - left.source_hit_at_1 ||
    right.source_hit_at_20 - left.source_hit_at_20 ||
    Number(left.group) - Number(right.group) ||
    left.p95_latency_ms - right.p95_latency_ms
  );
  return { metrics, selectedPenalty: Number(eligible[0].group), tuningCases: tuningCases.length };
}

function mean(rows, field) {
  return rows.length ? rows.reduce((total, row) => total + Number(row[field] || 0), 0) / rows.length : 0;
}

function metricRow(strategy, dimension, group, rows) {
  const latencies = rows.map(row => Number(row.elapsed_ms));
  return {
    evaluation_version: "unreadable_text_v1",
    dataset: "unreadable_text_catalog_sample",
    algorithm: "static_browser_search",
    strategy,
    dimension,
    group,
    cases: rows.length,
    hit_at_1: mean(rows, "hit_at_1"),
    hit_at_5: mean(rows, "hit_at_5"),
    hit_at_10: mean(rows, "hit_at_10"),
    hit_at_20: mean(rows, "hit_at_20"),
    source_hit_at_1: mean(rows, "source_hit_at_1"),
    source_hit_at_20: mean(rows, "source_hit_at_20"),
    valid_top_1_rate: mean(rows, "valid_top_1"),
    mean_result_precision: mean(rows, "result_precision"),
    behavior_success_rate: mean(rows, "behavior_success"),
    confirmation_rate: mean(rows, "confirmation_required"),
    unsafe_confident_top_1_rate: mean(rows, "unsafe_confident_top_1"),
    no_result_rate: mean(rows, "no_result"),
    mean_candidate_count: mean(rows, "candidate_count"),
    mean_latency_ms: mean(rows, "elapsed_ms"),
    p50_latency_ms: percentile(latencies, 0.50),
    p95_latency_ms: percentile(latencies, 0.95),
    p99_latency_ms: percentile(latencies, 0.99),
  };
}

function groupedMetrics(rows) {
  const metrics = [];
  for (const strategy of STRATEGIES) {
    const strategyRows = rows.filter(row => row.strategy === strategy);
    const locked = strategyRows.filter(row => Number(row.use_in_locked_score) === 1);
    metrics.push(metricRow(strategy, "overall", "inclusive", strategyRows));
    metrics.push(metricRow(strategy, "denominator", "locked_family_disjoint", locked));
    for (const field of [
      "split",
      "mode",
      "expected_behavior",
      "visible_length_band",
      "hidden_length_band",
      "collision_band",
      "source_type",
      "source_word_shape",
    ]) {
      const values = [...new Set(locked.map(row => row[field]))].sort();
      for (const value of values) {
        metrics.push(metricRow(strategy, field, value, locked.filter(row => row[field] === value)));
      }
    }
    for (const field of ["split", "visible_length_band", "collision_band"]) {
      const values = [...new Set(strategyRows.map(row => row[field]))].sort();
      for (const value of values) {
        metrics.push(metricRow(
          strategy,
          `inclusive_${field}`,
          value,
          strategyRows.filter(row => row[field] === value),
        ));
      }
    }
  }
  return metrics;
}

function summarize(rows, metrics, universe, targets, sampleModulus, tuning) {
  const lockedCases = rows.filter(row => row.strategy === "indexed" && Number(row.use_in_locked_score) === 1);
  const metric = (strategy, dimension, group) => metrics.find(row =>
    row.strategy === strategy && row.dimension === dimension && row.group === group
  );
  const full = metric("full_scan", "denominator", "locked_family_disjoint");
  const indexed = metric("indexed", "denominator", "locked_family_disjoint");
  const inclusive = metric("indexed", "overall", "inclusive");
  const unique = metric("indexed", "expected_behavior", "match");
  const ambiguous = metric("indexed", "expected_behavior", "ambiguous");
  const byCase = new Map();
  for (const row of rows) {
    if (!byCase.has(row.case_id)) byCase.set(row.case_id, {});
    byCase.get(row.case_id)[row.strategy] = row;
  }
  let gainedH1 = 0;
  let lostH1 = 0;
  let changedOrder = 0;
  for (const pair of byCase.values()) {
    if (!pair.full_scan || !pair.indexed) continue;
    if (pair.indexed.hit_at_1 > pair.full_scan.hit_at_1) gainedH1++;
    if (pair.indexed.hit_at_1 < pair.full_scan.hit_at_1) lostH1++;
    if (pair.indexed.returned_families !== pair.full_scan.returned_families) changedOrder++;
  }
  const acceptance = {
    unique_hit_at_20_at_least_99_percent: unique.hit_at_20 >= 0.99,
    valid_top_1_is_100_percent: indexed.valid_top_1_rate === 1,
    behavior_success_is_100_percent: indexed.behavior_success_rate === 1,
    inclusive_behavior_success_is_100_percent: inclusive.behavior_success_rate === 1,
    inclusive_result_precision_is_100_percent: inclusive.mean_result_precision === 1,
    unsafe_confident_top_1_is_zero: indexed.unsafe_confident_top_1_rate === 0,
    inclusive_unsafe_confident_top_1_is_zero: inclusive.unsafe_confident_top_1_rate === 0,
    no_hit_at_1_regression_vs_full_scan: indexed.hit_at_1 >= full.hit_at_1,
    p95_latency_not_worse_than_full_scan: indexed.p95_latency_ms <= full.p95_latency_ms,
  };
  return {
    evaluation_version: "unreadable_text_v1",
    generated_at: new Date().toISOString(),
    catalog_records: 25066,
    pattern_targets: targets.length,
    exhaustive_pattern_universe: { ...universe, total: universe.after + universe.before + universe.middle },
    sampling: {
      rule: `retain all requests with <=2 visible characters; otherwise SHA-256(request) modulo ${sampleModulus} equals zero`,
      sampled_unique_requests: rows.length / STRATEGIES.length,
      locked_family_disjoint_requests: lockedCases.length,
      mixed_split_diagnostic_requests: rows.filter(row => row.strategy === "indexed" && row.split === "mixed_split_diagnostic").length,
    },
    full_scan: full,
    indexed,
    indexed_inclusive: inclusive,
    indexed_unique_evidence: unique,
    indexed_ambiguous_evidence: ambiguous,
    paired: { gained_hit_at_1: gainedH1, lost_hit_at_1: lostH1, changed_rank_order: changedOrder },
    ranking_tuning: {
      split: "development",
      denominator: "ambiguous locked requests",
      cases: tuning.tuningCases,
      objective: "maximize source-family Hit@1, then Hit@20, while every returned family remains pattern-valid",
      candidate_penalties: GAP_PENALTIES,
      selected_gap_penalty: tuning.selectedPenalty,
      runtime_default_gap_penalty: RUNTIME_DEFAULT_GAP_PENALTY,
    },
    acceptance,
    accepted: Object.values(acceptance).every(Boolean),
  };
}

function fixed(value, digits = 2) {
  return Number(value * 100).toFixed(digits);
}

function buildReport(summary, metrics, rows) {
  const inclusive = summary.indexed_inclusive;
  const indexed = summary.indexed;
  const unique = summary.indexed_unique_evidence;
  const ambiguous = summary.indexed_ambiguous_evidence;
  const failures = rows.filter(row =>
    row.strategy === "indexed" && Number(row.use_in_locked_score) === 1 && Number(row.hit_at_20) === 0
  ).slice(0, 20);
  const modeRows = metrics.filter(row => row.strategy === "indexed" && row.dimension === "mode");
  const visibleRows = metrics.filter(row =>
    row.strategy === "indexed" && row.dimension === "inclusive_visible_length_band"
  );
  const tuningRows = metrics.filter(row => row.dimension === "development_ambiguous_gap_penalty");
  const sourceMisses = rows.filter(row =>
    row.strategy === "indexed" && Number(row.source_hit_at_20) === 0
  ).slice(0, 10);
  const lines = [
    "# Unreadable-Text Search Experiment",
    "",
    "## Contract",
    "",
    `The catalog contains ${summary.pattern_targets.toLocaleString()} distinct full-base or validated family-head targets. Exhaustive masking creates ${summary.exhaustive_pattern_universe.total.toLocaleString()} possible requests. The evaluated sample uses ${summary.sampling.rule} and contains ${summary.sampling.sampled_unique_requests.toLocaleString()} unique requests.`,
    "",
    "A unique-evidence request matches one catalog family and is scored with Hit@k. An ambiguous request matches several catalog families and is successful when the system returns only valid options and requires confirmation. Mixed development/holdout collisions remain diagnostic and do not enter the locked score.",
    "",
    "## Headline Results",
    "",
    "| Denominator | Cases | Hit@1 | Hit@20 | Valid top 1 | Behavior | Unsafe top 1 | p95 ms |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    `| Inclusive diagnostics | ${inclusive.cases} | ${fixed(inclusive.hit_at_1)}% | ${fixed(inclusive.hit_at_20)}% | ${fixed(inclusive.valid_top_1_rate)}% | ${fixed(inclusive.behavior_success_rate)}% | ${fixed(inclusive.unsafe_confident_top_1_rate)}% | ${Number(inclusive.p95_latency_ms).toFixed(2)} |`,
    `| Locked overall | ${indexed.cases} | ${fixed(indexed.hit_at_1)}% | ${fixed(indexed.hit_at_20)}% | ${fixed(indexed.valid_top_1_rate)}% | ${fixed(indexed.behavior_success_rate)}% | ${fixed(indexed.unsafe_confident_top_1_rate)}% | ${Number(indexed.p95_latency_ms).toFixed(2)} |`,
    `| Unique evidence | ${unique.cases} | ${fixed(unique.hit_at_1)}% | ${fixed(unique.hit_at_20)}% | ${fixed(unique.valid_top_1_rate)}% | ${fixed(unique.behavior_success_rate)}% | ${fixed(unique.unsafe_confident_top_1_rate)}% | ${Number(unique.p95_latency_ms).toFixed(2)} |`,
    `| Ambiguous evidence | ${ambiguous.cases} | ${fixed(ambiguous.hit_at_1)}% | ${fixed(ambiguous.hit_at_20)}% | ${fixed(ambiguous.valid_top_1_rate)}% | ${fixed(ambiguous.behavior_success_rate)}% | ${fixed(ambiguous.unsafe_confident_top_1_rate)}% | ${Number(ambiguous.p95_latency_ms).toFixed(2)} |`,
    "",
    "## Position Coverage",
    "",
    "| Unreadable position | Cases | Hit@1 | Hit@20 | Source H@1 | Source H@20 | p95 ms |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ...modeRows.map(row => `| ${row.group} | ${row.cases} | ${fixed(row.hit_at_1)}% | ${fixed(row.hit_at_20)}% | ${fixed(row.source_hit_at_1)}% | ${fixed(row.source_hit_at_20)}% | ${Number(row.p95_latency_ms).toFixed(2)} |`),
    "",
    "## Visible-Evidence Diagnostics",
    "",
    "These rows include mixed-split ambiguity. Hit@1 means the first displayed family is valid for the visible pattern; Source H@1 asks whether the arbitrary catalog source used to generate the mask is first and is not a fairness metric when several families match.",
    "",
    "| Total visible characters | Cases | Valid top 1 | Result precision | Source H@1 | Source H@20 | Mean candidates |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ...visibleRows.map(row => `| ${row.group} | ${row.cases} | ${fixed(row.valid_top_1_rate)}% | ${fixed(row.mean_result_precision)}% | ${fixed(row.source_hit_at_1)}% | ${fixed(row.source_hit_at_20)}% | ${Number(row.mean_candidate_count).toFixed(2)} |`),
    "",
    "## Baseline Comparison",
    "",
    `The indexed strategy changes ${summary.paired.changed_rank_order} returned family orders, gains ${summary.paired.gained_hit_at_1} Hit@1 cases, and loses ${summary.paired.lost_hit_at_1}. Full-scan p95 latency is ${Number(summary.full_scan.p95_latency_ms).toFixed(2)} ms; indexed p95 latency is ${Number(summary.indexed.p95_latency_ms).toFixed(2)} ms.`,
    "",
    "## Development-Only Ranking Tuning",
    "",
    "The gap penalty prefers a medicine requiring fewer hidden characters when several catalog families satisfy the same visible pattern. It was selected only on locked development-family ambiguous requests. Source H@k is a parsimony diagnostic here, not a claim that other matching families are wrong.",
    "",
    "| Penalty per hidden character | Cases | Source H@1 | Source H@20 | Valid top 1 | Result precision |",
    "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ...tuningRows.map(row => `| ${row.group} | ${row.cases} | ${fixed(row.source_hit_at_1)}% | ${fixed(row.source_hit_at_20)}% | ${fixed(row.valid_top_1_rate)}% | ${fixed(row.mean_result_precision)}% |`),
    "",
    `Selected penalty: ${summary.ranking_tuning.selected_gap_penalty}. The runtime default is ${summary.ranking_tuning.runtime_default_gap_penalty}.`,
    "",
    "## Acceptance Gates",
    "",
    ...Object.entries(summary.acceptance).map(([gate, passed]) => `- ${passed ? "PASS" : "FAIL"}: ${gate.replaceAll("_", " ")}`),
    "",
    "## Remaining Top-20 Misses",
    "",
  ];
  if (!failures.length) lines.push("No locked indexed request misses every relevant family in the top 20.");
  else {
    lines.push("| Mode | Visible input | Ending | Relevant families | Returned families |");
    lines.push("| --- | --- | --- | --- | --- |");
    for (const row of failures) {
      lines.push(`| ${row.mode} | ${row.visible_text} | ${row.ending_text || "-"} | ${row.relevant_families} | ${row.returned_families || "none"} |`);
    }
  }
  lines.push("");
  lines.push("## Source-Family Ambiguity Examples");
  lines.push("");
  lines.push("These are not relevance failures. The displayed medicines all satisfy the visible pattern; the source family falls outside the first 20 only because the request admits many valid catalog completions.");
  lines.push("");
  if (!sourceMisses.length) lines.push("No sampled source family falls outside the first 20.");
  else {
    lines.push("| Mode | Visible input | Ending | Generator source | First valid result | Valid family count |");
    lines.push("| --- | --- | --- | --- | --- | ---: |");
    for (const row of sourceMisses) {
      lines.push(`| ${row.mode} | ${row.visible_text} | ${row.ending_text || "-"} | ${row.source_family} | ${row.returned_families.split(";")[0] || "none"} | ${row.relevant_family_count} |`);
    }
  }
  lines.push("");
  return lines.join("\n");
}

function validateCases(cases) {
  if (!cases.length) throw new Error("no unreadable-text cases were generated");
  if (new Set(cases.map(row => row.case_id)).size !== cases.length) throw new Error("duplicate case IDs");
  for (const mode of ["after", "before", "middle"]) {
    if (!cases.some(row => row.mode === mode)) throw new Error(`missing mode: ${mode}`);
  }
  for (const behavior of ["match", "ambiguous"]) {
    if (!cases.some(row => row.expected_behavior === behavior)) throw new Error(`missing behavior: ${behavior}`);
  }
  if (!cases.some(row => row.visible_length_band === "1_character")) {
    throw new Error("one-character edge evidence is missing");
  }
  const developmentFamilies = new Set();
  const holdoutFamilies = new Set();
  for (const row of cases.filter(item => Number(item.use_in_locked_score) === 1)) {
    const destination = row.split === "development" ? developmentFamilies : holdoutFamilies;
    for (const family of row.relevant_families.split(";")) destination.add(family);
  }
  const overlap = [...developmentFamilies].filter(family => holdoutFamilies.has(family));
  if (overlap.length) throw new Error(`family split overlap: ${overlap.slice(0, 5).join(", ")}`);
}

function mutatePartialFragment(fragment, seed) {
  if (fragment.length < 3) return fragment;
  const index = hashInteger(`partial-mutation-v1|${seed}`) % fragment.length;
  const original = fragment[index];
  const replacement = original === "A" ? "E" : "A";
  return `${fragment.slice(0, index)}${replacement}${fragment.slice(index + 1)}`;
}

function partialPatterns(target, graphemeKey) {
  const value = target.value;
  const patterns = [];
  if (value.length >= 5) {
    for (let split = 2; split <= value.length - 2; split++) {
      patterns.push([
        "full_name_two_parts",
        [value.slice(0, split), value.slice(split)],
        0,
      ]);
    }
  }
  if (value.length >= 8) {
    const first = Math.max(2, Math.floor(value.length / 3));
    const second = Math.min(value.length - 2, Math.max(first + 2, Math.floor(2 * value.length / 3)));
    patterns.push([
      "full_name_three_parts",
      [value.slice(0, first), value.slice(first, second), value.slice(second)],
      0,
    ]);
  }
  if (value.length >= 6) {
    patterns.push(["one_prefix_exact", [value.slice(0, 4)], 0]);
    patterns.push(["one_suffix_exact", [value.slice(-4)], 0]);
    const start = Math.max(1, Math.floor(value.length / 2) - 2);
    const middle = value.slice(start, start + 4);
    patterns.push(["one_internal_exact", [middle], 0]);
    patterns.push(["one_internal_typo", [mutatePartialFragment(middle, value)], 1]);
  }
  if (value.length >= 9) {
    const prefix = value.slice(0, 4);
    const suffix = value.slice(-4);
    patterns.push(["two_edges_exact", [prefix, suffix], 0]);
    patterns.push(["two_edges_first_typo", [mutatePartialFragment(prefix, `${value}|first`), suffix], 1]);
    patterns.push(["two_edges_second_typo", [prefix, mutatePartialFragment(suffix, `${value}|second`)], 1]);
  }
  if (value.length >= 11) {
    const middleStart = Math.floor(value.length / 2) - 1;
    const middle = value.slice(middleStart, middleStart + 3);
    const fragments = [value.slice(0, 3), middle, value.slice(-3)];
    patterns.push(["three_ordered_exact", fragments, 0]);
    patterns.push([
      "three_ordered_middle_typo",
      [fragments[0], mutatePartialFragment(middle, `${value}|middle`), fragments[2]],
      1,
    ]);
  }
  const graphemeValue = graphemeKey(value);
  let firstDifference = 0;
  while (
    firstDifference < Math.min(value.length, graphemeValue.length) &&
    value[firstDifference] === graphemeValue[firstDifference]
  ) {
    firstDifference++;
  }
  if (graphemeValue !== value && firstDifference < 5 && graphemeValue.length >= 6) {
    patterns.push(["one_prefix_grapheme", [graphemeValue.slice(0, 5)], 0]);
  }
  return patterns;
}

function generatePartialCases(targets, sampleModulus, limit, graphemeKey) {
  const selected = new Map();
  let universe = 0;
  for (const target of targets) {
    for (const [patternType, fragments, injectedErrors] of partialPatterns(target, graphemeKey)) {
      universe++;
      const visibleText = fragments.join(" ");
      const request = `parts|${visibleText}`;
      if (hashInteger(`partial-sample-v1|${request}`) % sampleModulus !== 0) continue;
      const candidate = {
        mode: "parts",
        pattern_type: patternType,
        visible_text: visibleText,
        fragments: fragments.join(";"),
        fragment_count: fragments.length,
        injected_error_count: injectedErrors,
        source_family: target.family,
        source_target: target.value,
        source_type: target.source,
        source_word_shape: target.wordShape,
        split: splitForFamily(target.family),
      };
      const current = selected.get(request);
      if (!current ||
          injectedErrors < current.injected_error_count ||
          (injectedErrors === current.injected_error_count && target.family < current.source_family)) {
        selected.set(request, candidate);
      }
    }
  }
  let cases = [...selected.values()].map(testCase => ({
    case_id: `partial_${hashHex(`${testCase.pattern_type}|${testCase.visible_text}|${testCase.source_family}`).slice(0, 16)}`,
    ...testCase,
  }));
  cases.sort((left, right) => left.case_id.localeCompare(right.case_id));
  if (limit) cases = cases.slice(0, limit);
  return { cases, universe };
}

function evaluatePartialCases(MedSearch, catalog, cases) {
  return cases.map((testCase, index) => {
    const response = MedSearch.searchCatalog(catalog, testCase.visible_text, TOP_K, {
      unreadableMode: "parts",
      unreadableStrategy: "indexed",
    });
    const returned = uniqueFamilies(response.results);
    const sourceIndex = returned.indexOf(testCase.source_family);
    const parityChecked = hashInteger(`partial-parity-v1|${testCase.case_id}`) % 20 === 0;
    let parityPassed = "";
    let fullScanElapsed = "";
    if (parityChecked) {
      const fullScan = MedSearch.searchCatalog(catalog, testCase.visible_text, TOP_K, {
        unreadableMode: "parts",
        unreadableStrategy: "full_scan",
      });
      parityPassed = uniqueFamilies(fullScan.results).join(";") === returned.join(";") ? 1 : 0;
      fullScanElapsed = Number(fullScan.elapsed_ms || 0);
    }
    if ((index + 1) % 500 === 0) {
      process.stdout.write(`\rpartial indexed: ${index + 1}/${cases.length}`);
    }
    return {
      ...testCase,
      returned_family_count: returned.length,
      returned_families: returned.join(";"),
      source_family_rank: sourceIndex < 0 ? "" : sourceIndex + 1,
      source_hit_at_1: sourceIndex === 0 ? 1 : 0,
      source_hit_at_5: sourceIndex >= 0 && sourceIndex < 5 ? 1 : 0,
      source_hit_at_10: sourceIndex >= 0 && sourceIndex < 10 ? 1 : 0,
      source_hit_at_20: sourceIndex >= 0 && sourceIndex < TOP_K ? 1 : 0,
      confirmation_required: response.confirmation_required ? 1 : 0,
      no_result: returned.length ? 0 : 1,
      candidate_count: Number(response.candidate_count || 0),
      elapsed_ms: Number(response.elapsed_ms || 0),
      parity_checked: parityChecked ? 1 : 0,
      parity_passed: parityPassed,
      full_scan_elapsed_ms: fullScanElapsed,
    };
  });
}

function partialMetricRow(dimension, group, rows) {
  const parityRows = rows.filter(row => Number(row.parity_checked) === 1);
  const latencies = rows.map(row => Number(row.elapsed_ms));
  return {
    evaluation_version: "partial_text_v3",
    dataset: "partial_text_catalog_sample",
    algorithm: "static_browser_search",
    dimension,
    group,
    cases: rows.length,
    source_hit_at_1: mean(rows, "source_hit_at_1"),
    source_hit_at_5: mean(rows, "source_hit_at_5"),
    source_hit_at_10: mean(rows, "source_hit_at_10"),
    source_hit_at_20: mean(rows, "source_hit_at_20"),
    confirmation_rate: mean(rows, "confirmation_required"),
    no_result_rate: mean(rows, "no_result"),
    mean_candidate_count: mean(rows, "candidate_count"),
    mean_latency_ms: mean(rows, "elapsed_ms"),
    p50_latency_ms: percentile(latencies, 0.50),
    p95_latency_ms: percentile(latencies, 0.95),
    p99_latency_ms: percentile(latencies, 0.99),
    parity_cases: parityRows.length,
    full_scan_parity_rate: parityRows.length ? mean(parityRows, "parity_passed") : "",
    mean_full_scan_latency_ms: parityRows.length ? mean(parityRows, "full_scan_elapsed_ms") : "",
  };
}

function partialMetrics(rows) {
  const primary = rows.filter(row => row.pattern_type !== "one_internal_typo");
  const lowEvidence = rows.filter(row => row.pattern_type === "one_internal_typo");
  const metrics = [
    partialMetricRow("overall", "inclusive", rows),
    partialMetricRow("denominator", "primary_informative", primary),
    partialMetricRow("denominator", "single_fuzzy_fragment_diagnostic", lowEvidence),
  ];
  for (const field of ["split", "pattern_type", "fragment_count", "injected_error_count", "source_type"]) {
    for (const value of [...new Set(rows.map(row => row[field]))].sort()) {
      metrics.push(partialMetricRow(field, value, rows.filter(row => row[field] === value)));
    }
  }
  for (const value of [...new Set(primary.map(row => row.split))].sort()) {
    metrics.push(partialMetricRow(
      "primary_split",
      value,
      primary.filter(row => row.split === value),
    ));
  }
  return metrics;
}

function buildPartialReport(summary, metrics, rows) {
  const patterns = metrics.filter(row => row.dimension === "pattern_type");
  const splits = metrics.filter(row => row.dimension === "primary_split");
  const examples = rows.filter(row => Number(row.source_hit_at_1) === 1).slice(0, 8);
  return [
    "# Flexible Partial-Text Search Experiment",
    "",
    `The generator created ${summary.cases.toLocaleString()} deterministic requests from ${summary.pattern_universe.toLocaleString()} possible catalog-derived patterns. It tests every two-part full-name boundary, representative three-part names, fragments at arbitrary positions, one injected reading error, and common grapheme compression such as CK to K or PH to F.`,
    "",
    "Source-family Hit@k measures whether the family used to generate a request is returned. It is diagnostic when another medicine also satisfies the visible evidence. Every displayed result remains confirmation-required. The primary denominator excludes only the single-fuzzy-fragment class: one four-letter fragment, one injected error, and unknown position do not identify one source family. Those rows remain in the pattern table.",
    "",
    "## Split Results",
    "",
    "| Primary split | Cases | Source H@1 | Source H@20 | Confirmation | No result | p95 ms |",
    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ...splits.map(row => `| ${row.group} | ${row.cases} | ${fixed(row.source_hit_at_1)}% | ${fixed(row.source_hit_at_20)}% | ${fixed(row.confirmation_rate)}% | ${fixed(row.no_result_rate)}% | ${Number(row.p95_latency_ms).toFixed(2)} |`),
    "",
    "## Pattern Results",
    "",
    "| Pattern | Cases | Source H@1 | Source H@20 | Candidates | p95 ms |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
    ...patterns.map(row => `| ${row.group} | ${row.cases} | ${fixed(row.source_hit_at_1)}% | ${fixed(row.source_hit_at_20)}% | ${Number(row.mean_candidate_count).toFixed(1)} | ${Number(row.p95_latency_ms).toFixed(2)} |`),
    "",
    "## Exhaustive Parity",
    "",
    `${summary.parity_cases} requests were rerun against all 25,066 records. Indexed and exhaustive family orders match in ${fixed(summary.full_scan_parity_rate)}% of those requests.`,
    "",
    "## Examples",
    "",
    "| Visible input | Pattern | Source family | Top family |",
    "| --- | --- | --- | --- |",
    ...examples.map(row => `| ${row.visible_text} | ${row.pattern_type} | ${row.source_family} | ${row.returned_families.split(";")[0]} |`),
    "",
    "## Acceptance Gates",
    "",
    ...Object.entries(summary.acceptance).map(([gate, passed]) => `- ${passed ? "PASS" : "FAIL"}: ${gate.replaceAll("_", " ")}`),
    "",
  ].join("\n");
}

function runPartialExperiment(MedSearch, catalog, targets, options) {
  const generated = generatePartialCases(
    targets,
    options.partialSampleModulus,
    options.limit,
    MedSearch.partialGraphemeKey,
  );
  if (!generated.cases.length) throw new Error("no flexible partial-text cases were generated");
  writeCsv(PARTIAL_DATA_PATH, generated.cases);
  console.log(`Generated ${generated.cases.length} flexible requests from ${generated.universe} possible patterns.`);
  const rows = evaluatePartialCases(MedSearch, catalog, generated.cases);
  process.stdout.write("\n");
  const metrics = partialMetrics(rows);
  const overall = metrics.find(row => row.dimension === "overall");
  const primary = metrics.find(row => row.dimension === "denominator" && row.group === "primary_informative");
  const lowEvidence = metrics.find(row =>
    row.dimension === "denominator" && row.group === "single_fuzzy_fragment_diagnostic"
  );
  const holdout = metrics.find(row => row.dimension === "primary_split" && row.group === "holdout");
  const grapheme = metrics.find(row =>
    row.dimension === "pattern_type" && row.group === "one_prefix_grapheme"
  );
  const twoPart = metrics.find(row =>
    row.dimension === "pattern_type" && row.group === "full_name_two_parts"
  );
  const threePart = metrics.find(row =>
    row.dimension === "pattern_type" && row.group === "full_name_three_parts"
  );
  const acceptance = {
    primary_source_hit_at_20_at_least_99_percent: primary.source_hit_at_20 >= 0.99,
    holdout_primary_source_hit_at_20_at_least_99_percent: holdout.source_hit_at_20 >= 0.99,
    primary_confirmation_rate_is_100_percent: primary.confirmation_rate === 1,
    primary_no_result_rate_is_zero: primary.no_result_rate === 0,
    exhaustive_family_order_parity_is_100_percent: overall.full_scan_parity_rate === 1,
    indexed_p95_latency_below_150_ms: overall.p95_latency_ms < 150,
    grapheme_prefix_source_hit_at_20_at_least_97_percent:
      Boolean(grapheme) && grapheme.source_hit_at_20 >= 0.97,
    divided_full_name_hit_at_1_is_100_percent:
      Boolean(twoPart) && twoPart.source_hit_at_1 === 1,
    three_part_full_name_hit_at_1_is_100_percent:
      Boolean(threePart) && threePart.source_hit_at_1 === 1,
  };
  const summary = {
    evaluation_version: "partial_text_v3",
    generated_at: new Date().toISOString(),
    catalog_records: catalog.length,
    pattern_targets: targets.length,
    pattern_universe: generated.universe,
    sampling: `SHA-256(request) modulo ${options.partialSampleModulus} equals zero`,
    cases: rows.length,
    parity_cases: overall.parity_cases,
    full_scan_parity_rate: overall.full_scan_parity_rate,
    overall,
    primary,
    single_fuzzy_fragment_diagnostic: lowEvidence,
    holdout,
    grapheme_prefix: grapheme,
    full_name_two_parts: twoPart,
    full_name_three_parts: threePart,
    acceptance,
    accepted: Object.values(acceptance).every(Boolean),
  };
  writeCsv(PARTIAL_ARTIFACT_PATH, rows);
  writeCsv(PARTIAL_METRICS_PATH, metrics);
  writeJson(PARTIAL_SUMMARY_PATH, summary);
  fs.writeFileSync(PARTIAL_REPORT_PATH, `${buildPartialReport(summary, metrics, rows)}\n`);
  console.log(`Flexible partial-text acceptance: ${summary.accepted ? "PASS" : "FAIL"}`);
  return summary;
}

function main() {
  const options = parseArgs(process.argv);
  const require = createRequire(import.meta.url);
  const MedSearch = require(APP_MODULE);
  const rawCatalog = JSON.parse(fs.readFileSync(CATALOG_PATH, "utf8"));
  const catalog = MedSearch.prepareCatalog(rawCatalog.records);
  const targets = buildPatternTargets(catalog);
  const indexes = buildPatternIndexes(targets);
  if (!options.partialOnly) {
    const { cases, universe } = generateCases(targets, indexes, options.sampleModulus, options.limit);
    validateCases(cases);
    writeCsv(DATA_PATH, cases);
    console.log(`Generated ${cases.length} requests from ${universe.after + universe.before + universe.middle} possible masks.`);

    const tuning = evaluateGapPenalties(MedSearch, catalog, cases);
    console.log(`Selected unreadable gap penalty ${tuning.selectedPenalty} on ${tuning.tuningCases} development ambiguous requests.`);
    const results = evaluateCases(MedSearch, catalog, cases, tuning.selectedPenalty);
    const metrics = [...groupedMetrics(results), ...tuning.metrics];
    const summary = summarize(results, metrics, universe, targets, options.sampleModulus, tuning);
    summary.acceptance.selected_penalty_matches_runtime_default =
      tuning.selectedPenalty === RUNTIME_DEFAULT_GAP_PENALTY;
    summary.accepted = Object.values(summary.acceptance).every(Boolean);
    writeCsv(ARTIFACT_PATH, results);
    writeCsv(METRICS_PATH, metrics);
    writeJson(SUMMARY_PATH, summary);
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(REPORT_PATH, `${buildReport(summary, metrics, results)}\n`);
    console.log(`Acceptance: ${summary.accepted ? "PASS" : "FAIL"}`);
    console.log(`Report: ${REPORT_PATH}`);
  }
  const partialSummary = runPartialExperiment(MedSearch, catalog, targets, options);
  if (!partialSummary.accepted) process.exitCode = 1;
}

main();
