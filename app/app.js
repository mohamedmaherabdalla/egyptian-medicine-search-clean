const MedSearch = (() => {
  const ARABIC_DIGITS = new Map([
    ["٠", "0"], ["١", "1"], ["٢", "2"], ["٣", "3"], ["٤", "4"],
    ["٥", "5"], ["٦", "6"], ["٧", "7"], ["٨", "8"], ["٩", "9"],
  ]);

  const ARABIC_LETTERS = new Map([
    ["آ", "ا"], ["أ", "ا"], ["إ", "ا"], ["ٱ", "ا"], ["ى", "ي"],
    ["ئ", "ي"], ["ؤ", "و"], ["ة", "ه"],
  ]);

  const ENGLISH_NOISE = new Set([
    "AND", "PRICE", "DOSE", "DOS", "USE", "USES", "GENERIC", "FORTE",
    "TABLET", "TABLETS", "TAB", "TABS", "CAP", "CAPS", "CAPSULE",
    "SYRUP", "DROP", "DROPS", "MG", "MCG", "IU", "G", "GM", "ML",
    "VIAL", "AMP", "AMPOULE", "INJECTION", "PEN", "PENS",
  ]);

  const ARABIC_NOISE = new Set([
    "سعر", "بكام", "جرام", "جم", "مل", "اقراص", "قرص", "كبسول",
    "كبسوله", "كبسولة", "كبسولات", "شراب", "حقن", "حقنه", "حقنة",
    "فيال", "امبول", "امبوله", "امبولة",
  ]);

  const ROUTE_HINTS = new Map([
    ["TAB", "oral_solid"], ["TABS", "oral_solid"], ["TABLET", "oral_solid"], ["TABLETS", "oral_solid"],
    ["CAP", "oral_solid"], ["CAPS", "oral_solid"], ["CAPSULE", "oral_solid"],
    ["SYRUP", "oral_liquid"], ["SUSP", "oral_liquid"], ["SUSPENSION", "oral_liquid"], ["DROPS", "oral_liquid"],
    ["VIAL", "injection"], ["AMP", "injection"], ["AMPOULE", "injection"], ["INJ", "injection"], ["INF", "injection"],
    ["IV", "injection"], ["IM", "injection"], ["CREAM", "topical"], ["GEL", "topical"], ["OINT", "topical"],
    ["LOTION", "topical"], ["SOAP", "soap"], ["SPRAY", "spray"], ["EYE", "ophthalmic"], ["EAR", "otic"],
    ["MOUTH", "mouth"], ["RECTAL", "rectal"], ["SUPP", "rectal"], ["VAG", "vaginal"], ["VAGINAL", "vaginal"],
    ["قرص", "oral_solid"], ["اقراص", "oral_solid"], ["كبسول", "oral_solid"], ["كبسوله", "oral_solid"],
    ["كبسولة", "oral_solid"], ["شراب", "oral_liquid"], ["معلق", "oral_liquid"], ["نقط", "oral_liquid"],
    ["قطره", "oral_liquid"], ["قطرة", "oral_liquid"], ["حقن", "injection"], ["حقنة", "injection"],
    ["فيال", "injection"], ["امبول", "injection"], ["أمبول", "injection"], ["امبولة", "injection"],
    ["مرهم", "topical"], ["كريم", "topical"], ["جل", "topical"], ["بخاخ", "spray"], ["لبوس", "rectal"],
  ]);

  const BASE_ALIASES = new Map([
    ["BANADOL", "PANADOL"], ["BANADOLCOLD", "PANADOL"], ["BANADOLE", "PANADOL"],
    ["BANDOL", "PANADOL"], ["PANDOL", "PANADOL"], ["PANDOLCOLD", "PANADOL"], ["BANDOLCOLD", "PANADOL"],
    ["PANADL", "PANADOL"], ["PANADOLE", "PANADOL"], ["بنادول", "PANADOL"], ["باندول", "PANADOL"],
    ["OGMENTIN", "AUGMENTIN"], ["OGMNTIN", "AUGMENTIN"], ["AUGMNTIN", "AUGMENTIN"], ["AUGMANTIN", "AUGMENTIN"],
    ["اوجمنتين", "AUGMENTIN"], ["اوجمانتين", "AUGMENTIN"], ["اوجمنتن", "AUGMENTIN"],
    ["NEKSIUM", "NEXIUM"], ["NEKSUM", "NEXIUM"], ["NEXUM", "NEXIUM"], ["NEXEUM", "NEXIUM"], ["نكسيوم", "NEXIUM"],
    ["LIPTOR", "LIPITOR"], ["LEPITOR", "LIPITOR"], ["LIPTUR", "LIPITOR"], ["ليبتور", "LIPITOR"],
    ["BRUFN", "BRUFEN"], ["BRUFIN", "BRUFEN"], ["BROFEN", "BRUFEN"], ["بروفين", "BRUFEN"],
    ["KETOFN", "KETOFAN"], ["KETOFEN", "KETOFAN"], ["KETOFANE", "KETOFAN"], ["كيتوفان", "KETOFAN"],
    ["VOLTARIN", "VOLTAREN"], ["FOLTAREN", "VOLTAREN"], ["فولتارين", "VOLTAREN"],
  ]);

  const EXAMPLES = [
    { label: "English exact", query: "augmentin 1 gm tabs" },
    { label: "English typo", query: "ogmentin 625" },
    { label: "Heard spelling", query: "bandol cold" },
    { label: "Arabic brand", query: "اوجمنتين 1 جم" },
    { label: "Arabic hard", query: "ليبتور ٨٠" },
    { label: "Warning case", query: "data-version" },
    { label: "Ambiguous short", query: "CA" },
  ];

  function normalizeSearch(value) {
    if (value === null || value === undefined) return "";
    let text = String(value);
    text = Array.from(text, ch => ARABIC_DIGITS.get(ch) || ARABIC_LETTERS.get(ch) || ch).join("");
    text = text.replace(/[\u064b-\u065f\u0670\u0640]/g, "");
    text = text.toUpperCase();
    text = text.replace(/[^0-9A-Z\u0600-\u06ff]+/g, " ");
    return text.replace(/\s+/g, " ").trim();
  }

  function compactKey(value) {
    return normalizeSearch(value).replace(/[^0-9A-Z\u0600-\u06ff]+/g, "");
  }

  function tokensOf(value) {
    return normalizeSearch(value).split(" ").filter(token => {
      if (token.length < 2 || /^\d+$/.test(token)) return false;
      return !ENGLISH_NOISE.has(token) && !ARABIC_NOISE.has(token);
    });
  }

  function parseNumbers(value) {
    const matches = normalizeSearch(value).match(/\b\d+(?:\.\d+)?\b/g);
    return new Set(matches || []);
  }

  function parseRouteHints(value) {
    const hints = new Set();
    for (const token of normalizeSearch(value).split(" ")) {
      if (ROUTE_HINTS.has(token)) hints.add(ROUTE_HINTS.get(token));
    }
    return hints;
  }

  function boundedLevenshtein(a, b, maxDistance) {
    if (!a || !b) return null;
    if (Math.abs(a.length - b.length) > maxDistance) return null;
    let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      let rowMin = cur[0];
      for (let j = 1; j <= b.length; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        const val = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        cur[j] = val;
        if (val < rowMin) rowMin = val;
      }
      if (rowMin > maxDistance) return null;
      prev = cur;
    }
    return prev[b.length] <= maxDistance ? prev[b.length] : null;
  }

  function skeleton(value) {
    return compactKey(value)
      .replace(/PH/g, "F")
      .replace(/[CQK]/g, "K")
      .replace(/[PV]/g, "B")
      .replace(/[SZ]/g, "S")
      .replace(/[AEIOUY]/g, "")
      .replace(/(.)\1+/g, "$1");
  }

  function warningPipes(value) {
    return String(value || "").split("|").map(v => v.trim()).filter(Boolean);
  }

  function aliasTargetFor(query) {
    if (!query) return "";
    return BASE_ALIASES.get(compactKey(query)) || BASE_ALIASES.get(normalizeSearch(query)) || "";
  }

  function recordMatchesAliasTarget(record, target) {
    if (!target) return false;
    const targetNorm = normalizeSearch(target);
    const targetCompact = compactKey(target);
    return Boolean(
      record._bn === targetNorm ||
      record._bn.startsWith(`${targetNorm} `) ||
      record._bc === targetCompact ||
      record._bc.startsWith(targetCompact)
    );
  }

  function prepareCatalog(rawRecords) {
    return rawRecords.map((record) => {
      const nn = normalizeSearch(record.nn || record.n);
      const arn = normalizeSearch(record.arn || record.ar);
      const bn = normalizeSearch(record.b);
      const ingn = normalizeSearch(record.ing || record.s);
      const c = compactKey(record.c || record.n);
      const bc = compactKey(record.b);
      const ingc = compactKey(record.ing || record.s);
      const text = normalizeSearch(`${record.n} ${record.ar} ${record.b} ${record.ing} ${record.s}`);
      return {
        ...record,
        _nn: nn,
        _c: c,
        _arn: arn,
        _arc: compactKey(arn),
        _bn: bn,
        _bc: bc,
        _ingn: ingn,
        _ingc: ingc,
        _text: text,
        _tokens: tokensOf(`${record.n} ${record.b} ${record.ing}`).slice(0, 40),
        _nums: parseNumbers(`${record.st} ${record.n} ${record.ar}`),
        _routeHints: new Set([record.r, ...parseRouteHints(record.f || "")].filter(Boolean)),
        _sk: skeleton(record.b),
        _warnings: warningPipes(record.w),
      };
    });
  }

  function addScore(state, score, signal) {
    state.score += score;
    state.signals.add(signal);
  }

  function scoreRecord(record, query) {
    const state = { score: 0, signals: new Set() };
    const qn = query.norm;
    const qc = query.compact;

    if (!qn && !qc) return null;

    if (record._nn === qn) addScore(state, 1200, "exact_name");
    if (record._c === qc) addScore(state, 1160, "exact_compact");
    if (record._arn === qn || record._arc === qc) addScore(state, 1120, "exact_arabic_alias");
    if (record._bn === qn || record._bc === qc) addScore(state, 980, "exact_base_group");
    if (record._ingn === qn || record._ingc === qc) addScore(state, 720, "exact_ingredient");

    const aliasTarget = aliasTargetFor(qc) || aliasTargetFor(qn);
    if (recordMatchesAliasTarget(record, aliasTarget)) addScore(state, 1700, "heard_spelling_alias");

    if (qn.length >= 2) {
      if (record._nn.startsWith(qn)) addScore(state, 420 + Math.min(qn.length, 18), "prefix_name");
      if (record._arn.startsWith(qn)) addScore(state, 410 + Math.min(qn.length, 18), "prefix_arabic");
      if (record._bn.startsWith(qn)) addScore(state, 390 + Math.min(qn.length, 18), "prefix_base");
      if (record._ingn.startsWith(qn)) addScore(state, 260, "prefix_ingredient");
    }

    if (qc.length >= 3) {
      if (record._c.startsWith(qc)) addScore(state, 380 + Math.min(qc.length, 18), "prefix_compact");
      if (record._bc.startsWith(qc)) addScore(state, 390 + Math.min(qc.length, 18), "prefix_base_compact");
      if (record._arc.startsWith(qc)) addScore(state, 390 + Math.min(qc.length, 18), "prefix_arabic_compact");
      if (record._c.includes(qc)) addScore(state, 180, "contains_compact");
      if (record._bc && qc.includes(record._bc) && record._bc.length >= 4) addScore(state, 360, "query_contains_base");
    }

    let tokenHits = 0;
    for (const token of query.tokens) {
      const tc = compactKey(token);
      const tokenAliasTarget = aliasTargetFor(token) || aliasTargetFor(tc);
      if (recordMatchesAliasTarget(record, tokenAliasTarget)) {
        addScore(state, 1700, "heard_spelling_alias");
        tokenHits++;
        continue;
      }
      if (record._bn.split(" ").includes(token) || record._bc === tc) {
        addScore(state, 210, "token_base");
        tokenHits++;
      } else if (record._nn.split(" ").includes(token) || record._arn.split(" ").includes(token)) {
        addScore(state, 140, "token_name");
        tokenHits++;
      } else if (record._ingn.split(" ").includes(token)) {
        addScore(state, 80, "token_ingredient");
      } else if (record._text.includes(token) && token.length >= 3) {
        addScore(state, 42, "token_contains");
      }
    }
    if (tokenHits >= 2) addScore(state, 160 * tokenHits, "multi_token_match");

    const fuzzyUnits = [qc, ...query.tokens.map(compactKey)].filter(v => v.length >= 4).slice(0, 6);
    for (const unit of fuzzyUnits) {
      const threshold = unit.length <= 7 ? 1 : 2;
      const baseDist = boundedLevenshtein(unit, record._bc, threshold);
      if (baseDist !== null) addScore(state, 250 - 60 * baseDist, `fuzzy_base_ed${baseDist}`);
      const nameHead = record._c.slice(0, Math.max(unit.length - 1, 1));
      const nameDist = boundedLevenshtein(unit, nameHead, threshold);
      if (nameDist !== null) addScore(state, 120 - 35 * nameDist, `fuzzy_name_ed${nameDist}`);
      const sk = skeleton(unit);
      if (sk && sk === record._sk && sk.length >= 3) addScore(state, 170, "phonetic_skeleton");
    }

    if (query.numbers.size) {
      for (const num of query.numbers) {
        if (record._nums.has(num)) {
          addScore(state, 52, "number_match");
          break;
        }
      }
    }

    if (query.routes.size) {
      let routeHit = false;
      for (const route of query.routes) {
        if (record._routeHints.has(route)) routeHit = true;
      }
      if (routeHit) addScore(state, 58, "form_route_match");
      else if (record.r && record.r !== "unknown") addScore(state, -16, "form_route_mismatch");
    }

    if (record._warnings.includes("UNKNOWN_ROUTE")) addScore(state, -8, "quality_status_penalty");
    if (record._warnings.includes("MISSING_COMPOSITION")) addScore(state, -6, "quality_status_penalty");
    if (record._warnings.includes("N/A") || record._warnings.includes("CANCELLED") || record._warnings.includes("ILLEGAL_IMPORT")) {
      addScore(state, -28, "quality_status_penalty");
    }

    if (state.score <= 0) return null;
    return state;
  }

  function searchCatalog(records, input, limit = 20) {
    const started = performance.now ? performance.now() : Date.now();
    const query = {
      raw: input,
      norm: normalizeSearch(input),
      compact: compactKey(input),
      tokens: tokensOf(input),
      numbers: parseNumbers(input),
      routes: parseRouteHints(input),
    };
    if (!query.norm && !query.compact) return { results: [], elapsed_ms: 0 };

    const scored = [];
    for (const record of records) {
      const state = scoreRecord(record, query);
      if (!state) continue;
      scored.push({ record, score: state.score, signals: state.signals });
    }

    scored.sort((a, b) => b.score - a.score || String(a.record.n).localeCompare(String(b.record.n)));
    const top = scored.slice(0, limit);
    const topScore = top.length ? top[0].score : 0;
    const closeBases = new Set(top.slice(0, 8).filter(item => item.score >= topScore - 45).map(item => item.record.b).filter(Boolean));

    const results = top.map((item, index) => {
      const record = item.record;
      const exactProduct = item.signals.has("exact_name") || item.signals.has("exact_compact");
      const approximateOnly = [...item.signals].some(signal => signal.startsWith("fuzzy_") || signal.includes("phonetic")) &&
        ![...item.signals].some(signal => signal.startsWith("exact_") || signal.startsWith("prefix_") || signal === "heard_spelling_alias");
      const needsClarification = Boolean(
        query.norm.length <= 2 ||
        (record.bv > 1 && !query.numbers.size && !exactProduct) ||
        record.br > 1 ||
        record.bi > 1 && !exactProduct ||
        closeBases.size > 1 ||
        approximateOnly ||
        record._warnings.length
      );
      return {
        rank: index + 1,
        candidate_id: record.id,
        commercial_name_en: record.n,
        commercial_name_ar: record.ar,
        base_group_key: record.b || "-",
        ingredient_key: record.ing || record.s || "-",
        route_family: record.r || "-",
        price_egp: record.p,
        manufacturer: record.m || "-",
        drug_class: record.dc || "-",
        score: Math.round(item.score),
        matched_signals: [...item.signals].sort().join("|"),
        warnings: record._warnings.join("|"),
        needs_clarification: needsClarification,
      };
    });

    const ended = performance.now ? performance.now() : Date.now();
    return { results, elapsed_ms: ended - started };
  }

  return { EXAMPLES, normalizeSearch, compactKey, prepareCatalog, searchCatalog };
})();

if (typeof module !== "undefined") {
  module.exports = MedSearch;
}

if (typeof window !== "undefined") {
  window.MedSearch = MedSearch;

  const queryInput = document.getElementById("query");
  const searchBtn = document.getElementById("searchBtn");
  const searchForm = document.getElementById("searchForm");
  const resultsEl = document.getElementById("results");
  const errorEl = document.getElementById("error");
  const statusEl = document.getElementById("status");
  const summaryEl = document.getElementById("summary");

  let catalog = [];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
    }[ch]));
  }

  function splitPipes(value) {
    if (!value) return [];
    return String(value).split("|").map(v => v.trim()).filter(Boolean);
  }

  function humanWarning(flag) {
    const labels = {
      NON_MEDICINE_OR_METADATA: "Not a medicine record",
      UNKNOWN_ROUTE: "Unknown route",
      MISSING_COMPOSITION: "Missing composition",
      ROUTE_CONFLICT: "Route conflict",
      QUALITY_REVIEW: "Review",
      ILLEGAL_IMPORT: "Illegal import",
      CANCELLED: "Cancelled",
      "N/A": "N/A",
    };
    return labels[flag] || flag.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, ch => ch.toUpperCase());
  }

  function humanRoute(route) {
    const labels = {
      oral_solid: "Tablet / capsule",
      oral_liquid: "Oral liquid",
      injection: "Injection",
      topical: "Topical",
      ophthalmic: "Eye",
      otic: "Ear",
      rectal: "Rectal",
      vaginal: "Vaginal",
      mouth: "Mouth",
      spray: "Spray",
      soap: "Soap",
      unknown: "Unknown route",
    };
    return labels[route] || route.replaceAll("_", " ");
  }

  function badge(text, cls = "") {
    return `<span class="badge ${cls}">${esc(text)}</span>`;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.style.display = message ? "block" : "none";
  }

  function renderSummary(data, query) {
    const rows = data.results || [];
    if (!query) {
      summaryEl.textContent = "";
      return;
    }
    const count = rows.length === 1 ? "1 match" : `${rows.length} matches`;
    summaryEl.textContent = `${count} for "${query}"`;
  }

  function renderResults(data) {
    const rows = data.results || [];
    if (!rows.length) {
      resultsEl.innerHTML = `<div class="empty">No matches. Try the brand only, remove the strength, or use the Arabic name.</div>`;
      return;
    }
    resultsEl.innerHTML = rows.map(r => {
      const warnings = splitPipes(r.warnings).map(w => badge(humanWarning(w), "warn")).join("");
      const clarify = r.needs_clarification ? badge("confirm exact product", "ask") : "";
      const route = r.route_family && r.route_family !== "-" ? badge(humanRoute(r.route_family)) : "";
      return `
        <article class="result">
          <div class="rank">${esc(r.rank)}</div>
          <div>
            <div class="name-row">
              <div class="name" dir="auto">${esc(r.commercial_name_en)}</div>
              <div class="price">${esc(r.price_egp || "-")} EGP</div>
            </div>
            <div class="primary-meta">
              <span dir="auto">${esc(r.commercial_name_ar || "-")}</span>
              <span dir="auto">${esc(r.ingredient_key || "-")}</span>
            </div>
            <div class="secondary-meta">
              <div><b>Family:</b> ${esc(r.base_group_key || "-")}</div>
              <div><b>Manufacturer:</b> ${esc(r.manufacturer || "-")}</div>
              <div><b>Class:</b> ${esc(r.drug_class || "-")}</div>
            </div>
            <div class="badges">${route}${clarify}${warnings}</div>
          </div>
        </article>`;
    }).join("");
  }

  function search() {
    const q = queryInput.value.trim();
    showError("");
    if (!q) {
      resultsEl.innerHTML = `<div class="empty">Type a medicine name first.</div>`;
      renderSummary({ results: [] }, "");
      return;
    }
    const data = MedSearch.searchCatalog(catalog, q, 20);
    renderSummary(data, q);
    renderResults(data);
  }

  async function loadCatalog() {
    try {
      searchBtn.disabled = true;
      const res = await fetch("data/catalog.json");
      if (!res.ok) throw new Error(`Catalog request failed: ${res.status}`);
      const payload = await res.json();
      catalog = MedSearch.prepareCatalog(payload.records);
      statusEl.textContent = `${catalog.length.toLocaleString()} medicines`;
      renderSummary({ results: [] }, "");
      searchBtn.disabled = false;
    } catch (err) {
      statusEl.textContent = "Catalog failed";
      showError(err.message || String(err));
    }
  }

  searchForm.addEventListener("submit", event => {
    event.preventDefault();
    search();
  });
  queryInput.addEventListener("keydown", event => {
    if (event.key === "Enter") search();
  });

  searchBtn.disabled = true;
  loadCatalog();
}
