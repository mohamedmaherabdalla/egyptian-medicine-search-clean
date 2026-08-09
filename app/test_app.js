#!/usr/bin/env node

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const MedSearch = require("./app.js");

const catalogPath = path.join(__dirname, "data", "catalog.json");
const payload = JSON.parse(fs.readFileSync(catalogPath, "utf8"));
const catalog = MedSearch.prepareCatalog(payload.records);

function search(query, options = {}) {
  return MedSearch.searchCatalog(catalog, query, 20, options);
}

function patternTargets(record) {
  const targets = [record._bc];
  if (record._headFamily && record._headc && record._headc !== record._bc) {
    targets.push(record._headc);
  }
  return targets;
}

function matchesUnreadablePattern(target, mode, visibleText, endingText) {
  if (mode === "after") return target.startsWith(visibleText) && target.length > visibleText.length;
  if (mode === "before") return target.endsWith(visibleText) && target.length > visibleText.length;
  return target.startsWith(visibleText) &&
    target.endsWith(endingText) &&
    target.length > visibleText.length + endingText.length;
}

function relevantFamilies(mode, visibleText, endingText = "") {
  const families = new Set();
  for (const record of catalog.records) {
    if (patternTargets(record).some(target =>
      matchesUnreadablePattern(target, mode, visibleText, endingText)
    )) {
      families.add(record._familyGroupKey);
    }
  }
  return families;
}

function familyOrder(response) {
  return [...new Set(response.results.map(result => result.family_group_key))];
}

const first = search("pndol");
const second = search("TEFA");
const repeated = search("pndol");

assert.ok(first.results.length > 0);
assert.ok(second.results.length > 0);
assert.deepEqual(
  repeated.results.map(result => result.base_group_key),
  first.results.map(result => result.base_group_key),
);
assert.equal(first.algorithm, "browser_consensus_search");
assert.equal(first.status, "ambiguous");
assert.equal(first.confirmation_required, true);
assert.equal(first.calibrated_likely_match, false);
assert.ok(
  first.results.every(
    result => result.needs_clarification && result.confirmation_required,
  ),
);

for (const [mode, query, endingFragment] of [
  ["before", "TRIL", ""],
  ["middle", "RIV", "RIL"],
  ["after", "RIVOTRI", ""],
]) {
  const response = search(query, { unreadableMode: mode, endingFragment });
  assert.equal(response.unreadable_mode, mode);
  assert.ok(response.results.length > 0);
  assert.ok(response.results.every(result => result.confirmation_required));
}

const splitPanadol = search("pana", {
  unreadableMode: "middle",
  endingFragment: "ol",
});
assert.equal(splitPanadol.results[0].family_group_key, "PANADOL");
assert.ok(
  splitPanadol.results.some(result => result.base_group_key === "PANAX PANTHENOL"),
);
assert.ok(splitPanadol.results[0].matched_signals.includes("unreadable_family_head"));

const generatedTargets = [];
const seenGeneratedTargets = new Set();
for (const record of catalog.records) {
  for (const target of patternTargets(record)) {
    if (target.length < 5 || target.length > 18 || seenGeneratedTargets.has(target)) continue;
    seenGeneratedTargets.add(target);
    generatedTargets.push(target);
  }
}
generatedTargets.sort();
const sampleStep = Math.max(1, Math.floor(generatedTargets.length / 48));
const generatedSample = generatedTargets.filter((_, index) => index % sampleStep === 0).slice(0, 48);
let generatedChecks = 0;
for (const target of generatedSample) {
  const edgeLength = Math.max(1, Math.min(4, Math.floor(target.length / 3)));
  const cases = [
    { mode: "after", visibleText: target.slice(0, target.length - edgeLength), endingText: "" },
    { mode: "before", visibleText: target.slice(edgeLength), endingText: "" },
    {
      mode: "middle",
      visibleText: target.slice(0, edgeLength),
      endingText: target.slice(-edgeLength),
    },
  ];
  for (const testCase of cases) {
    const relevant = relevantFamilies(testCase.mode, testCase.visibleText, testCase.endingText);
    assert.ok(relevant.size > 0);
    const indexedResponse = search(testCase.visibleText, {
      unreadableMode: testCase.mode,
      endingFragment: testCase.endingText,
      unreadableStrategy: "indexed",
    });
    const fullScanResponse = search(testCase.visibleText, {
      unreadableMode: testCase.mode,
      endingFragment: testCase.endingText,
      unreadableStrategy: "full_scan",
    });
    assert.ok(indexedResponse.results.length > 0);
    assert.equal(indexedResponse.confirmation_required, true);
    assert.ok(familyOrder(indexedResponse).every(family => relevant.has(family)));
    assert.deepEqual(
      familyOrder(indexedResponse),
      familyOrder(fullScanResponse),
      `${testCase.mode}:${testCase.visibleText}:${testCase.endingText}`,
    );
    generatedChecks++;
  }
}
assert.equal(generatedChecks, 144);

for (const query of ["MELI CAM", "MELI...CAM"]) {
  const response = search(query, { unreadableMode: "parts" });
  assert.equal(response.results[0].family_group_key, "MELOXICAM");
  assert.equal(response.decision_type, "partial_text_matches");
  assert.equal(response.confirmation_required, true);
}

const graphemePrefix = search("JAK", { unreadableMode: "parts" });
const graphemeFamilies = familyOrder(graphemePrefix);
assert.ok(graphemeFamilies.indexOf("JACKODAN") >= 0);
assert.ok(graphemeFamilies.indexOf("JACKODAN") < 5);
assert.ok(
  graphemePrefix.results
    .filter(result => result.family_group_key === "JACKODAN")
    .every(result => result.matched_signals.includes("unreadable_grapheme_equivalent")),
);

for (const [query, expectedFamily] of [
  ["JACK ODAN", "JACKODAN"],
  ["JACKO DAN", "JACKODAN"],
  ["PANA DOL", "PANADOL"],
  ["COUGH SED", "COUGHSED"],
]) {
  const response = search(query, { unreadableMode: "parts" });
  assert.equal(response.results[0].family_group_key, expectedFamily, query);
  assert.equal(response.confirmation_required, true, query);
}

function mutateLastCharacter(value) {
  return `${value.slice(0, -1)}${value.endsWith("A") ? "E" : "A"}`;
}

let partialChecks = 0;
for (const target of generatedSample.filter(value => value.length >= 9).slice(0, 16)) {
  const midpoint = Math.floor(target.length / 2);
  for (const query of [
    target.slice(2, -2),
    `${target.slice(0, 4)} ${target.slice(-4)}`,
    `${mutateLastCharacter(target.slice(0, 4))} ${target.slice(-4)}`,
    `${target.slice(0, 2)} ${target.slice(midpoint, midpoint + 2)} ${target.slice(-2)}`,
  ]) {
    const indexedResponse = search(query, {
      unreadableMode: "parts",
      unreadableStrategy: "indexed",
    });
    const fullScanResponse = search(query, {
      unreadableMode: "parts",
      unreadableStrategy: "full_scan",
    });
    assert.ok(indexedResponse.results.length > 0);
    assert.equal(indexedResponse.confirmation_required, true);
    assert.deepEqual(familyOrder(indexedResponse), familyOrder(fullScanResponse), query);
    partialChecks++;
  }
}
assert.equal(partialChecks, 64);

const graphemeTargets = [];
const seenGraphemeTargets = new Set();
for (const record of catalog.records) {
  for (const target of patternTargets(record)) {
    const key = `${record._familyGroupKey}|${target}`;
    if (!target || seenGraphemeTargets.has(key)) continue;
    seenGraphemeTargets.add(key);
    const grapheme = MedSearch.partialGraphemeKey(target);
    let firstDifference = 0;
    while (
      firstDifference < Math.min(target.length, grapheme.length) &&
      target[firstDifference] === grapheme[firstDifference]
    ) {
      firstDifference++;
    }
    if (grapheme !== target && firstDifference < 5 && grapheme.length >= 6) {
      graphemeTargets.push({
        family: record._familyGroupKey,
        target,
        query: grapheme.slice(0, 5),
      });
    }
  }
}
graphemeTargets.sort((left, right) =>
  `${left.family}|${left.target}`.localeCompare(`${right.family}|${right.target}`)
);
const graphemeStep = Math.max(1, Math.floor(graphemeTargets.length / 48));
const graphemeSample = graphemeTargets.filter((_, index) => index % graphemeStep === 0).slice(0, 48);
let graphemeHitAt20 = 0;
let graphemeParityChecks = 0;
for (const [index, testCase] of graphemeSample.entries()) {
  const indexedResponse = search(testCase.query, {
    unreadableMode: "parts",
    unreadableStrategy: "indexed",
  });
  const indexedFamilies = familyOrder(indexedResponse);
  if (indexedFamilies.includes(testCase.family)) graphemeHitAt20++;
  assert.equal(indexedResponse.confirmation_required, true);
  if (index % 4 === 0) {
    const fullScanResponse = search(testCase.query, {
      unreadableMode: "parts",
      unreadableStrategy: "full_scan",
    });
    assert.deepEqual(indexedFamilies, familyOrder(fullScanResponse));
    graphemeParityChecks++;
  }
}
assert.equal(graphemeSample.length, 48);
assert.ok(graphemeHitAt20 >= 46);
assert.equal(graphemeParityChecks, 12);

const empty = search("");
assert.equal(empty.results.length, 0);

for (const [query, expectedProduct, expectedSignals] of [
  ["augmentin 1 gm tabs", "AUGMENTIN 1 GM 14 F.C.TABS.", ["strength_match", "dosage_form_match", "form_route_match"]],
  ["augmentin 457mg/5ml suspension", "AUGMENTIN 457MG/5ML SUSP. 70 ML", ["strength_match", "dosage_form_match", "form_route_match"]],
  ["voltaren 100mg sr tablet", "VOLTAREN SR 100MG 20 F.C.TAB.", ["strength_match", "dosage_form_match", "release_type_match"]],
  ["voltaren gel 1%", "VOLTAREN 1% EMULGEL 100 GM", ["strength_match", "dosage_form_match", "form_route_match"]],
  ["devarol 200,000 I.U amp", "DEVAROL-S 200.000 I.U / 2 ML 1 I.M. AMP.", ["strength_match", "dosage_form_match", "form_route_match"]],
]) {
  const response = search(query);
  assert.equal(response.results[0].commercial_name_en, expectedProduct);
  assert.equal(response.decision_type, "product_context_selection");
  for (const signal of expectedSignals) {
    assert.ok(response.results[0].matched_context.includes(signal));
  }
}

const afterContextSearch = search("TEFA");
assert.deepEqual(
  afterContextSearch.results.map(result => result.base_group_key),
  second.results.map(result => result.base_group_key),
);

console.log("Browser search tests passed.");
