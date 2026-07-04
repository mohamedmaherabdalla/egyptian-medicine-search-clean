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

  const GENERIC_TOKENS = new Set([
    "PLUS", "EXTRA", "FORTE", "ADVANCE", "MAX", "SUPER", "ULTRA",
    "NEW", "ACTIVE", "NATURAL", "GOLD", "SILVER", "BIO", "VITA", "VIT",
    "PRO", "CARE", "SKIN", "HAIR", "BABY", "KIDS", "ADULT", "DRUG",
    "MEDICINE", "CREAM", "GEL", "LOTION", "SOAP", "SHAMPOO", "MASK",
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
      if (token.length < 2) return false;
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

  function deletes(value, maxDeletes) {
    const results = new Set([value]);
    let frontier = new Set([value]);
    for (let depth = 0; depth < maxDeletes; depth++) {
      const next = new Set();
      for (const item of frontier) {
        for (let i = 0; i < item.length; i++) {
          const deleted = item.slice(0, i) + item.slice(i + 1);
          if (!results.has(deleted)) {
            results.add(deleted);
            next.add(deleted);
          }
        }
      }
      frontier = next;
    }
    return results;
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

  function drugPhoneticKey(value) {
    return compactKey(value)
      .replace(/PH/g, "F")
      .replace(/CK/g, "K")
      .replace(/GH/g, "G")
      .replace(/[BPFV]/g, "P")
      .replace(/[DT]/g, "T")
      .replace(/[CGKQ]/g, "K")
      .replace(/[SZ]/g, "S")
      .replace(/[J]/g, "G")
      .replace(/[AEIOUY]/g, "")
      .replace(/(.)\1+/g, "$1");
  }

  const KEY_NEIGHBORS = (() => {
    const rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
    const map = new Map();
    for (const row of rows) {
      for (let i = 0; i < row.length; i++) {
        const neighbors = new Set([row[i]]);
        if (i > 0) neighbors.add(row[i - 1]);
        if (i < row.length - 1) neighbors.add(row[i + 1]);
        map.set(row[i], neighbors);
      }
    }
    const vertical = {
      Q: "A", W: "AS", E: "SD", R: "DF", T: "FG", Y: "GH", U: "HJ", I: "JK", O: "KL", P: "L",
      A: "QWZ", S: "QWEXZ", D: "WERFCX", F: "ERTGVC", G: "RTYHBV", H: "TYUJNB", J: "YUIKMN", K: "UIOLM", L: "OPK",
      Z: "ASX", X: "ASDCZ", C: "SDFVX", V: "DFGBC", B: "FGHNV", N: "GHJMB", M: "HJKN",
    };
    for (const [key, chars] of Object.entries(vertical)) {
      if (!map.has(key)) map.set(key, new Set([key]));
      for (const ch of chars) map.get(key).add(ch);
    }
    return map;
  })();

  function keyboardProximityRatio(queryCompact, targetCompact) {
    if (!queryCompact || !targetCompact || queryCompact.length !== targetCompact.length) return 0;
    if (queryCompact.length < 4 || queryCompact.length > 18) return 0;
    let hits = 0;
    for (let i = 0; i < queryCompact.length; i++) {
      const q = queryCompact[i];
      const t = targetCompact[i];
      if (q === t || (KEY_NEIGHBORS.get(t) && KEY_NEIGHBORS.get(t).has(q))) hits++;
    }
    return hits / queryCompact.length;
  }

  const VISUAL_REPLACEMENTS = [
    ["RN", "M"], ["M", "RN"], ["CL", "D"], ["D", "CL"], ["RI", "N"],
    ["N", "RI"], ["LI", "H"], ["H", "LI"], ["VV", "W"], ["W", "VV"],
    ["0", "O"], ["O", "0"], ["1", "I"], ["I", "1"], ["1", "L"],
    ["L", "1"], ["5", "S"], ["S", "5"], ["8", "B"], ["B", "8"],
    ["2", "Z"], ["Z", "2"], ["6", "G"], ["G", "6"],
  ];

  function visualVariants(value) {
    const base = compactKey(value);
    const variants = new Set();
    if (!base || base.length < 3) return variants;
    for (const [from, to] of VISUAL_REPLACEMENTS) {
      if (base.includes(from)) variants.add(base.replaceAll(from, to));
    }
    variants.delete(base);
    return variants;
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

  function addPrefixStats(stats, record) {
    const keys = new Set([record._bc, record._c, record._arc].filter(Boolean));
    for (const key of keys) {
      for (let length = 1; length <= Math.min(6, key.length); length++) {
        const prefix = key.slice(0, length);
        if (!stats.prefixDanger.has(prefix)) {
          stats.prefixDanger.set(prefix, {
            bases: new Set(),
            products: new Set(),
            ingredients: new Set(),
            routes: new Set(),
          });
        }
        const item = stats.prefixDanger.get(prefix);
        if (record._bc) item.bases.add(record._bc);
        if (record._c) item.products.add(record._c);
        if (record._ingc) item.ingredients.add(record._ingc);
        if (record.r) item.routes.add(record.r);
      }
    }
  }

  function addShortRegistry(stats, record) {
    const keys = [
      record._bn, record._bc, record._arn, record._arc,
      record._nn, record._c,
    ];
    for (const key of keys) {
      const compact = compactKey(key);
      if (compact && compact.length <= 4) stats.shortRegistry.add(compact);
    }
  }

  function addIndex(index, key, record) {
    if (!key) return;
    if (!index.has(key)) index.set(key, new Set());
    index.get(key).add(record);
  }

  function addPrefixIndex(index, value, record, maxLen = 12) {
    if (!value) return;
    for (let length = 2; length <= Math.min(maxLen, value.length); length++) {
      addIndex(index, value.slice(0, length), record);
    }
  }

  function addGramsIndex(index, value, record) {
    if (!value || value.length < 3) return;
    const seen = new Set();
    for (let i = 0; i <= value.length - 3; i++) seen.add(value.slice(i, i + 3));
    for (const gram of seen) addIndex(index, gram, record);
  }

  function buildIndex(records) {
    const index = {
      exact: new Map(),
      prefix: new Map(),
      grams: new Map(),
      token: new Map(),
      skeleton: new Map(),
      baseExact: new Map(),
      delete: new Map(),
      phonetic: new Map(),
      phoneticPrefix: new Map(),
      baseLength: new Map(),
    };
    for (const record of records) {
      const exactFields = [
        record._nn, record._c, record._arn, record._arc,
        record._bn, record._bc, record._ingn, record._ingc,
      ];
      for (const value of exactFields) addIndex(index.exact, value, record);
      for (const value of exactFields) addPrefixIndex(index.prefix, value, record);
      for (const value of [record._c, record._arc, record._bc, record._ingc]) {
        addGramsIndex(index.grams, value, record);
      }
      for (const token of new Set(tokensOf(`${record.n || ""} ${record.b || ""} ${record.ing || ""} ${record.s || ""}`))) {
        addIndex(index.token, token, record);
      }
      addIndex(index.skeleton, record._sk, record);
      addIndex(index.baseExact, record._bc, record);
      if (record._bc) {
        addIndex(index.baseLength, String(record._bc.length), record);
        const maxDeletes = record._bc.length <= 7 ? 1 : 2;
        for (const deleted of deletes(record._bc, maxDeletes)) {
          if (deleted.length >= 3) addIndex(index.delete, deleted, record);
        }
      }
      if (record._ph) {
        addIndex(index.phonetic, record._ph, record);
        for (let length = 3; length <= Math.min(12, record._ph.length); length++) {
          addIndex(index.phoneticPrefix, record._ph.slice(0, length), record);
        }
      }
    }
    return index;
  }

  function prepareCatalog(rawRecords) {
    const records = rawRecords.map((record) => {
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
        _ph: drugPhoneticKey(record.b),
        _warnings: warningPipes(record.w),
      };
    });
    const stats = {
      prefixDanger: new Map(),
      shortRegistry: new Set(),
    };
    for (const record of records) {
      addPrefixStats(stats, record);
      addShortRegistry(stats, record);
    }
    return { records, stats, index: buildIndex(records), length: records.length };
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
      const genericToken = GENERIC_TOKENS.has(token);
      if (!genericToken && (record._bn.split(" ").includes(token) || record._bc === tc)) {
        addScore(state, 210, "token_base");
        tokenHits++;
      } else if (record._arc.startsWith(tc) && /^\d+$/.test(tc)) {
        addScore(state, 940, "token_exact_arabic_alias");
        tokenHits++;
      } else if (record._nn.split(" ").includes(token) || record._arn.split(" ").includes(token)) {
        addScore(state, 140, "token_name");
        tokenHits++;
      } else if (record._ingn.split(" ").includes(token)) {
        addScore(state, 80, "token_ingredient");
      } else if (!genericToken && record._text.includes(token) && token.length >= 3) {
        addScore(state, 42, "token_contains");
      }
    }
    if (tokenHits >= 2) addScore(state, 160 * tokenHits, "multi_token_match");

    const specificContextHit = query.specificTokens.some((token, index) => {
      const tc = query.specificTokenCompacts[index];
      return record._arn.split(" ").includes(token) ||
        record._nn.split(" ").includes(token) ||
        record._bn.split(" ").includes(token) ||
        record._arc === tc ||
        record._c.includes(tc) ||
        record._bc.includes(tc);
    });
    if (specificContextHit) {
      for (let index = 0; index < query.genericTokens.length; index++) {
        const token = query.genericTokens[index];
        const tc = query.genericTokenCompacts[index];
        if (record._nn.split(" ").includes(token) || record._bn.split(" ").includes(token) || record._c.includes(tc) || record._bc.includes(tc)) {
          addScore(state, 560, "generic_context_match");
          break;
        }
      }
    }

    for (const unit of query.fuzzyUnits) {
      if (unit.value.length <= 32) {
        const baseDist = boundedLevenshtein(unit.value, record._bc, unit.threshold);
        if (baseDist !== null) addScore(state, 250 - 60 * baseDist, `fuzzy_base_ed${baseDist}`);
      }
      if (unit.skeleton && unit.skeleton === record._sk && unit.skeleton.length >= 3) {
        addScore(state, 170, "phonetic_skeleton");
      }
    }

    if (query.phonetic && record._ph && query.phonetic.length >= 3) {
      if (query.phonetic === record._ph) addScore(state, 500, "drug_phonetic_key");
      else if (record._ph.startsWith(query.phonetic)) addScore(state, 650, "drug_phonetic_prefix");
      if (query.compact[0] && record._bc[0] && query.compact[0] === record._bc[0]) addScore(state, 250, "phonetic_first_char");
    }

    for (const variant of query.visualCompacts) {
      if (variant === record._bc || record._bc.startsWith(variant) || record._c.startsWith(variant)) {
        addScore(state, 210, "visual_confusion_candidate");
        break;
      }
    }

    const keyboardRatio = keyboardProximityRatio(qc, record._bc);
    if (keyboardRatio >= 0.68) {
      addScore(state, 250 * keyboardRatio, "keyboard_proximity");
      if (qc[0] && record._bc[0] && qc[0] === record._bc[0]) addScore(state, 160, "keyboard_first_char");
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

    if (query.specificTokens.length && GENERIC_TOKENS.has(record._bc)) {
      addScore(state, -420, "generic_dominance_penalty");
    }

    if (state.score <= 0) return null;
    return state;
  }

  function prefixRisk(searchState, query) {
    const compact = query.compact;
    let worst = { baseCount: 0, productCount: 0, ingredientCount: 0, routeCount: 0, force: false };
    if (!compact) return worst;
    for (let length = 1; length <= Math.min(6, compact.length); length++) {
      const item = searchState.stats.prefixDanger.get(compact.slice(0, length));
      if (!item) continue;
      const current = {
        baseCount: item.bases.size,
        productCount: item.products.size,
        ingredientCount: item.ingredients.size,
        routeCount: item.routes.size,
      };
      if (current.baseCount > worst.baseCount || current.ingredientCount > worst.ingredientCount) {
        worst = { ...current, force: false };
      }
    }
    const exactShort = query.compact.length <= 4 && searchState.stats.shortRegistry.has(query.compact);
    worst.force = Boolean(
      !exactShort && (
        (query.compact.length <= 2 && worst.baseCount > 1) ||
        (query.compact.length <= 4 && (worst.baseCount >= 4 || worst.ingredientCount >= 3)) ||
        (worst.baseCount >= 12 || worst.ingredientCount >= 6)
      )
    );
    return worst;
  }

  function signalHasStrongEvidence(signals) {
    return [...signals].some(signal =>
      signal === "heard_spelling_alias" ||
      signal === "exact_name" ||
      signal === "exact_compact" ||
      signal === "exact_arabic_alias" ||
      signal === "exact_base_group"
    );
  }

  function addCandidates(ids, source) {
    if (!source) return;
    for (const record of source) ids.add(record);
  }

  function candidateRecords(searchIndex, query) {
    if (!searchIndex) return null;
    const ids = new Set();
    const qValues = [query.norm, query.compact].filter(Boolean);
    for (const value of qValues) {
      addCandidates(ids, searchIndex.exact.get(value));
      addCandidates(ids, searchIndex.prefix.get(value.slice(0, Math.min(12, value.length))));
    }

    if (query.compact.length >= 3) {
      const grams = [];
      for (let i = 0; i <= query.compact.length - 3; i++) grams.push(query.compact.slice(i, i + 3));
      if (grams.length) {
        const rare = grams.reduce((best, gram) =>
          (searchIndex.grams.get(gram)?.size || 0) < (searchIndex.grams.get(best)?.size || 0) ? gram : best
        );
        addCandidates(ids, searchIndex.grams.get(rare));
      }
    }

    const compactTokens = query.tokenCompacts.filter(token => token.length >= 2);
    for (let i = 0; i < compactTokens.length; i++) {
      let combined = "";
      for (const token of compactTokens.slice(i, i + 3)) {
        combined += token;
        if (combined.length >= 4) addCandidates(ids, searchIndex.baseExact.get(combined));
      }
    }

    const longContextQuery = query.tokens.length > 3;
    for (let i = 0; i < query.tokens.length; i++) {
      const token = query.tokens[i];
      const tc = query.tokenCompacts[i];
      const genericToken = GENERIC_TOKENS.has(token);
      const rankingOnlyToken = (
        (/^\d+$/.test(tc) && query.tokens.length > 1) ||
        (ROUTE_HINTS.has(token) && query.tokens.length > 1) ||
        (tc.length <= 2 && query.tokens.length > 2)
      );
      if (!rankingOnlyToken && !(genericToken && query.specificTokens.length)) {
        addCandidates(ids, searchIndex.token.get(token));
      }
      if (/^\d+$/.test(tc) && query.genericTokens.length && query.tokens.length <= 3 && tc.length >= 3 && tc.length <= 4) {
        addCandidates(ids, searchIndex.prefix.get(tc));
      }
      const target = aliasTargetFor(token) || aliasTargetFor(tc);
      if (target) addCandidates(ids, searchIndex.baseExact.get(compactKey(target)));
      if (tc.length >= 3 && !rankingOnlyToken && !longContextQuery && !(genericToken && query.specificTokens.length)) {
        const grams = [];
        for (let j = 0; j <= tc.length - 3; j++) grams.push(tc.slice(j, j + 3));
        if (grams.length) {
          const rare = grams.reduce((best, gram) =>
            (searchIndex.grams.get(gram)?.size || 0) < (searchIndex.grams.get(best)?.size || 0) ? gram : best
          );
          addCandidates(ids, searchIndex.grams.get(rare));
        }
      }
    }

    const aliasTarget = aliasTargetFor(query.compact) || aliasTargetFor(query.norm);
    if (aliasTarget) addCandidates(ids, searchIndex.baseExact.get(compactKey(aliasTarget)));

    for (const unit of query.fuzzyUnits) {
      if (ids.size < 100) {
        for (const deleted of deletes(unit.value, unit.threshold)) {
          if (deleted.length >= 3) {
            const bucket = searchIndex.delete.get(deleted);
            if (!bucket || bucket.size <= 600) addCandidates(ids, bucket);
          }
        }
      }
      if (unit.skeleton.length >= 3 && ids.size < 500) {
        addCandidates(ids, searchIndex.skeleton.get(unit.skeleton));
      }
    }

    for (const variant of query.visualCompacts) {
      addCandidates(ids, searchIndex.exact.get(variant));
      addCandidates(ids, searchIndex.prefix.get(variant.slice(0, Math.min(12, variant.length))));
    }

    if (query.phonetic.length >= 3) {
      addCandidates(ids, searchIndex.phonetic.get(query.phonetic));
      if (ids.size < 500) {
        addCandidates(ids, searchIndex.phoneticPrefix.get(query.phonetic.slice(0, Math.min(12, query.phonetic.length))));
      }
    }

    if (ids.size < 20 && query.compact.length >= 4 && query.compact.length <= 18) {
      const sameLength = searchIndex.baseLength.get(String(query.compact.length));
      if (sameLength) {
        for (const record of sameLength) {
          if (keyboardProximityRatio(query.compact, record._bc) >= 0.68) ids.add(record);
        }
      }
    }

    return ids;
  }

  function searchCatalog(searchState, input, limit = 20) {
    const started = performance.now ? performance.now() : Date.now();
    const records = Array.isArray(searchState) ? searchState : searchState.records;
    const state = Array.isArray(searchState)
      ? { records, stats: { prefixDanger: new Map(), shortRegistry: new Set() }, length: records.length }
      : searchState;
    const query = {
      raw: input,
      norm: normalizeSearch(input),
      compact: compactKey(input),
      tokens: tokensOf(input),
      numbers: parseNumbers(input),
      routes: parseRouteHints(input),
    };
    query.tokenCompacts = query.tokens.map(compactKey);
    query.genericTokens = query.tokens.filter(token => GENERIC_TOKENS.has(token));
    query.specificTokens = query.tokens.filter(token => !GENERIC_TOKENS.has(token));
    query.genericTokenCompacts = query.genericTokens.map(compactKey);
    query.specificTokenCompacts = query.specificTokens.map(compactKey);
    query.visualCompacts = visualVariants(input);
    query.phonetic = drugPhoneticKey(input);
    const fuzzyValues = query.tokens.length > 4 ? [] : [query.compact, ...query.tokenCompacts];
    query.fuzzyUnits = [];
    const seenFuzzy = new Set();
    for (const value of fuzzyValues) {
      if (value.length < 4 || seenFuzzy.has(value)) continue;
      seenFuzzy.add(value);
      query.fuzzyUnits.push({
        value,
        threshold: value.length <= 7 ? 1 : 2,
        skeleton: skeleton(value),
      });
      if (query.fuzzyUnits.length >= 6) break;
    }
    if (!query.norm && !query.compact) return { results: [], elapsed_ms: 0 };

    const scored = [];
    const candidates = state.index ? candidateRecords(state.index, query) : null;
    for (const record of (candidates || records)) {
      const state = scoreRecord(record, query);
      if (!state) continue;
      scored.push({ record, score: state.score, signals: state.signals });
    }

    scored.sort((a, b) => b.score - a.score || String(a.record.n).localeCompare(String(b.record.n)));
    const top = scored.slice(0, limit);
    const topScore = top.length ? top[0].score : 0;
    const closeBases = new Set(top.slice(0, 8).filter(item => item.score >= topScore - 45).map(item => item.record.b).filter(Boolean));
    const closeIngredients = new Set(top.slice(0, 5).filter(item => item.score >= topScore - 90).map(item => item.record.ing || item.record.s).filter(Boolean));
    const risk = prefixRisk(state, query);
    const exactShort = query.compact.length <= 4 && state.stats.shortRegistry.has(query.compact);
    const shortUnregistered = query.compact.length <= 4 && !exactShort && !query.numbers.size;
    const exactShortButDangerous = exactShort && query.compact.length <= 4 && risk.baseCount >= 8 && risk.ingredientCount >= 4;
    const genericOnly = query.tokens.length > 0 && query.specificTokens.length === 0 && query.genericTokens.length > 0;

    const results = top.map((item, index) => {
      const record = item.record;
      const exactProduct = item.signals.has("exact_name") || item.signals.has("exact_compact");
      const approximateOnly = [...item.signals].some(signal =>
        signal.startsWith("fuzzy_") ||
        signal.includes("phonetic") ||
        signal === "keyboard_proximity" ||
        signal === "visual_confusion_candidate"
      ) &&
        ![...item.signals].some(signal => signal.startsWith("exact_") || signal.startsWith("prefix_") || signal === "heard_spelling_alias");
      const weakEvidence = !signalHasStrongEvidence(item.signals) && (
        item.signals.has("contains_compact") ||
        item.signals.has("query_contains_base") ||
        item.signals.has("keyboard_proximity") ||
        item.signals.has("visual_confusion_candidate") ||
        item.signals.has("drug_phonetic_key") ||
        item.signals.has("phonetic_skeleton")
      );
      const needsClarification = Boolean(
        (query.compact.length <= 2 && !exactShort) ||
        (shortUnregistered && !exactProduct) ||
        (exactShortButDangerous && !exactProduct) ||
        risk.force ||
        genericOnly ||
        (closeIngredients.size > 1 && !exactProduct && !signalHasStrongEvidence(item.signals)) ||
        (record.bv > 1 && !query.numbers.size && !exactProduct) ||
        record.br > 1 ||
        record.bi > 1 && !exactProduct ||
        closeBases.size > 1 ||
        approximateOnly ||
        weakEvidence ||
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
    const needsClarification = results.some(result => result.needs_clarification);
    return {
      results,
      elapsed_ms: ended - started,
      needs_clarification: needsClarification,
      query_status: needsClarification ? "possible_matches" : "ranked_matches",
      prefix_risk: risk,
    };
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
    const count = rows.length === 1 ? "1 possible match" : `${rows.length} possible matches`;
    const confidentCount = rows.length === 1 ? "1 match" : `${rows.length} matches`;
    summaryEl.textContent = data.needs_clarification
      ? `${count} for "${query}"`
      : `${confidentCount} for "${query}"`;
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
