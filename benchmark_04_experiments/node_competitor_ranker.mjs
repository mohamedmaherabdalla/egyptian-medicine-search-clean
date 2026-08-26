#!/usr/bin/env node

import fs from "node:fs";
import readline from "node:readline";

import FlexSearch from "flexsearch";
import Fuse from "fuse.js";

const [catalogPath, algorithm] = process.argv.slice(2);
if (!catalogPath || !algorithm) {
  throw new Error("usage: node_competitor_ranker.mjs CATALOG_JSON ALGORITHM");
}

const families = JSON.parse(fs.readFileSync(catalogPath, "utf8"));

function prepareFuse(useTokenSearch) {
  const index = new Fuse(families, {
    keys: ["name"],
    includeScore: true,
    useTokenSearch,
  });
  return (query) =>
    index.search(query, { limit: 20 }).map((result) => result.item.id);
}

function prepareFlexSearch(tokenize, encoder) {
  const index = new FlexSearch.Index({
    tokenize,
    ...(encoder ? { encoder } : {}),
  });
  for (const family of families) {
    index.add(family.id, family.name);
  }
  return (query) =>
    index.search(query, { limit: 20, suggest: true });
}

const search = {
  fuse_default_bitap: () => prepareFuse(false),
  fuse_token_search: () => prepareFuse(true),
  flexsearch_tolerant_default: () => prepareFlexSearch("tolerant"),
  flexsearch_tolerant_advanced: () =>
    prepareFlexSearch("tolerant", "LatinAdvanced"),
  flexsearch_tolerant_extra: () =>
    prepareFlexSearch("tolerant", "LatinExtra"),
  flexsearch_full_advanced: () =>
    prepareFlexSearch("full", "LatinAdvanced"),
}[algorithm]?.();

if (!search) {
  throw new Error(`unsupported node competitor: ${algorithm}`);
}

process.stdout.write("READY\n");

const input = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

for await (const line of input) {
  if (!line) {
    continue;
  }
  const queries = JSON.parse(line);
  const rankings = queries.map((query) => search(query));
  process.stdout.write(`${JSON.stringify(rankings)}\n`);
}
