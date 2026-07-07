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

  const VOWELS = new Set(["A", "E", "I", "O", "U", "Y"]);
  const FIRST_CHAR_CONFUSION_GROUPS = [
    new Set(["C", "K", "Q"]),
    new Set(["S", "Z"]),
    new Set(["F", "V"]),
    new Set(["P", "B"]),
    new Set(["D", "T"]),
    new Set(["G", "J"]),
    new Set(["M", "N"]),
    new Set(["I", "E", "Y"]),
    new Set(["O", "U"]),
  ];

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

  function makeQuery(input) {
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
    query.skeleton = skeleton(input);
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
    return query;
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
    for (const variant of firstCharVariants(query.compact)) {
      addCandidates(ids, searchIndex.prefix.get(variant.slice(0, Math.min(12, variant.length))));
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

    if (query.compact.length >= 4 && query.compact.length <= 12 && ids.size < 1600) {
      const firstChars = new Set([query.compact[0], ...confusableChars(query.compact[0])].filter(Boolean));
      const lengths = [];
      for (let length = Math.max(1, query.compact.length - 3); length <= query.compact.length + 3; length++) {
        lengths.push(length);
      }
      lengths.sort((left, right) => Math.abs(left - query.compact.length) - Math.abs(right - query.compact.length));
      let scanned = 0;
      scanLengths:
      for (const length of lengths) {
        const bucket = searchIndex.baseLength.get(String(length));
        if (!bucket) continue;
        for (const record of bucket) {
          if (scanned >= 2400) break scanLengths;
          scanned++;
          if (record._bc && firstChars.has(record._bc[0])) ids.add(record);
        }
      }
    }

    return ids;
  }

  function searchCurrentCatalog(searchState, input, limit = 20) {
    const started = performance.now ? performance.now() : Date.now();
    const records = Array.isArray(searchState) ? searchState : searchState.records;
    const state = Array.isArray(searchState)
      ? { records, stats: { prefixDanger: new Map(), shortRegistry: new Set() }, length: records.length }
      : searchState;
    const query = makeQuery(input);
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
      source: "current",
    };
  }

  const EXTERNAL_CONFIDENT_STATUSES = new Set(["high_confidence", "medium_confidence"]);
  const RRF_K = 8.0;
  const DEFAULT_EXTERNAL_RANK_WEIGHT = 1.22;
  const DEFAULT_CURRENT_RANK_WEIGHT = 1.00;
  const CONTEXT_CURRENT_RANK_WEIGHT = 1.45;
  const CONTEXT_EXTERNAL_RANK_WEIGHT = 0.78;
  const SHORT_QUERY_CURRENT_RANK_WEIGHT = 1.60;
  const SHORT_QUERY_EXTERNAL_RANK_WEIGHT = 0.55;
  const STRONG_AGREEMENT_BONUS = 0.16;
  const WEAK_AGREEMENT_BONUS = 0.035;
  const CURRENT_EXACT_BONUS = 0.18;
  const EXTERNAL_EXACT_BONUS = 0.12;
  const CONTEXT_CURRENT_BONUS = 0.08;
  const TYPO_EXTERNAL_TOP1_BONUS = 0.22;
  const TYPO_EXTERNAL_TOP2_BONUS = 0.09;
  const CURRENT_KEYBOARD_TOP_BONUS_WHEN_EXTERNAL_UNSURE = 0.34;
  const HIGH_CONFIDENCE_SCORE = 0.26;
  const MEDIUM_CONFIDENCE_SCORE = 0.20;
  const HIGH_CONFIDENCE_MARGIN = 0.055;
  const MEDIUM_CONFIDENCE_MARGIN = 0.030;

  function charNgrams(value, size) {
    const grams = new Set();
    if (!value || value.length < size) return grams;
    for (let index = 0; index <= value.length - size; index++) {
      grams.add(value.slice(index, index + size));
    }
    return grams;
  }

  function setJaccard(left, right) {
    if (!left.size || !right.size) return 0;
    let intersection = 0;
    for (const value of left) {
      if (right.has(value)) intersection++;
    }
    return intersection / (left.size + right.size - intersection);
  }

  function substitutionCost(left, right, weighted) {
    if (left === right) return 0;
    if (!weighted) return 1;
    const pair = new Set([left, right]);
    const close = (
      pair.has("V") && pair.has("F") ||
      pair.has("P") && pair.has("B") ||
      pair.has("C") && pair.has("K") ||
      pair.has("Q") && pair.has("K") ||
      pair.has("M") && pair.has("N") ||
      pair.has("I") && pair.has("E") ||
      pair.has("O") && pair.has("U") ||
      pair.has("Y") && pair.has("I") ||
      pair.has("S") && pair.has("Z") ||
      pair.has("T") && pair.has("D") ||
      pair.has("G") && pair.has("J")
    );
    if (VOWELS.has(left) && VOWELS.has(right)) return 0.70;
    return close ? 0.45 : 1;
  }

  function damerauDistance(left, right, weighted = false) {
    if (left === right) return 0;
    if (!left) return right.length;
    if (!right) return left.length;
    const cols = right.length + 1;
    let prevprev = null;
    let prev = Array.from({ length: cols }, (_, index) => index);
    for (let i = 1; i <= left.length; i++) {
      const cur = [i, ...Array(right.length).fill(0)];
      for (let j = 1; j < cols; j++) {
        const cost = substitutionCost(left[i - 1], right[j - 1], weighted);
        let val = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prevprev && j > 1 && left[i - 1] === right[j - 2] && left[i - 2] === right[j - 1]) {
          val = Math.min(val, prevprev[j - 2] + (weighted ? 0.45 : 1));
        }
        cur[j] = val;
      }
      prevprev = prev;
      prev = cur;
    }
    return prev[right.length];
  }

  function editSimilarity(queryCompact, targetCompact, weighted = false) {
    if (!queryCompact || !targetCompact) return 0;
    const maxLen = Math.max(queryCompact.length, targetCompact.length);
    if (!maxLen) return 1;
    if (Math.abs(queryCompact.length - targetCompact.length) > Math.max(4, Math.ceil(maxLen * 0.45))) return 0;
    return Math.max(0, 1 - damerauDistance(queryCompact, targetCompact, weighted) / maxLen);
  }

  function confusableChars(char) {
    if (!char) return new Set();
    const out = new Set();
    const upper = char.toUpperCase();
    for (const group of FIRST_CHAR_CONFUSION_GROUPS) {
      if (!group.has(upper)) continue;
      for (const item of group) {
        if (item !== upper) out.add(item);
      }
    }
    return out;
  }

  function firstCharVariants(value) {
    if (!value) return new Set();
    const variants = new Set();
    for (const char of confusableChars(value[0])) variants.add(char + value.slice(1));
    return variants;
  }

  function prefixSimilarity(queryCompact, targetCompact) {
    if (queryCompact.length < 3 || !targetCompact.startsWith(queryCompact)) return 0;
    return Math.min(1, queryCompact.length / targetCompact.length);
  }

  function containsSimilarity(queryCompact, targetCompact) {
    if (queryCompact.length < 3 || !targetCompact.includes(queryCompact)) return 0;
    return Math.min(1, queryCompact.length / targetCompact.length);
  }

  function subsequenceScore(queryCompact, targetCompact) {
    if (!queryCompact || !targetCompact || queryCompact.length > targetCompact.length) return 0;
    const positions = [];
    let start = 0;
    for (const char of queryCompact) {
      const found = targetCompact.indexOf(char, start);
      if (found < 0) return 0;
      positions.push(found);
      start = found + 1;
    }
    const span = positions[positions.length - 1] - positions[0] + 1;
    const coverage = queryCompact.length / targetCompact.length;
    const density = queryCompact.length / span;
    let edgeBonus = 0;
    if (queryCompact[0] === targetCompact[0]) edgeBonus += 0.10;
    if (queryCompact[queryCompact.length - 1] === targetCompact[targetCompact.length - 1]) edgeBonus += 0.10;
    return Math.min(1, 0.55 * density + 0.35 * coverage + edgeBonus);
  }

  function tokenScoreForExternal(query, record) {
    if (!query.tokens.length) return { token: 0, specific: 0, common: 0 };
    let total = 0;
    let specific = 0;
    let common = 0;
    for (let index = 0; index < query.tokens.length; index++) {
      const token = query.tokens[index];
      const compact = query.tokenCompacts[index];
      const isCommon = GENERIC_TOKENS.has(token);
      let strength = 0;
      if (record._bn.split(" ").includes(token) || record._nn.split(" ").includes(token)) strength = 1;
      else if (compact.length >= 4 && (record._bc.startsWith(compact) || record._c.startsWith(compact))) strength = 0.85;
      else if (compact.length >= 4 && (record._bc.includes(compact) || record._c.includes(compact))) strength = 0.75;
      const weighted = strength * (isCommon ? 0.25 : 1.0);
      total += weighted;
      if (isCommon) common += weighted;
      else specific += weighted;
    }
    const denom = Math.max(1, query.tokens.length);
    return {
      token: Math.min(1, total / denom),
      specific: Math.min(1, specific / denom),
      common: Math.min(1, common / denom),
    };
  }

  function scoreExternalRecord(record, query, sources, candidateCount) {
    const exact = query.compact === record._bc ? 1 : 0;
    const aliasTarget = aliasTargetFor(query.compact) || aliasTargetFor(query.norm);
    const aliasCompact = aliasTarget ? compactKey(aliasTarget) : "";
    const alias = aliasCompact && (record._bc === aliasCompact || record._bc.startsWith(aliasCompact)) ? 1 : 0;
    const edit = editSimilarity(query.compact, record._bc);
    const weightedEdit = editSimilarity(query.compact, record._bc, true);
    const prefix = prefixSimilarity(query.compact, record._bc);
    const contains = containsSimilarity(query.compact, record._bc);
    const subsequence = subsequenceScore(query.compact, record._bc);
    const skeletonScore = query.skeleton && record._sk
      ? (query.skeleton === record._sk ? 0.98 : record._sk.startsWith(query.skeleton) ? 0.82 : 0)
      : 0;
    const phoneticScore = query.phonetic && record._ph
      ? (query.phonetic === record._ph ? 1 : record._ph.startsWith(query.phonetic) ? 0.80 : 0)
      : 0;
    const tokenScores = tokenScoreForExternal(query, record);
    const grams = query.compact.length >= 4 ? charNgrams(query.compact, 4) : charNgrams(query.compact, 3);
    const recordGrams = query.compact.length >= 4 ? charNgrams(record._bc, 4) : charNgrams(record._bc, 3);
    const ngram = setJaccard(grams, recordGrams);

    const scores = [];
    if (exact) scores.push(["exact_mode", 1.0]);
    else if (alias) scores.push(["exact_mode", 0.97]);
    if (query.compact.length >= 4) {
      scores.push(["full_typo_mode", (
        0.32 * edit +
        0.22 * weightedEdit +
        0.15 * phoneticScore +
        0.13 * skeletonScore +
        0.10 * ngram +
        0.05 * subsequence +
        0.03 * tokenScores.token
      )]);
    }
    if (query.compact.length >= 3) {
      scores.push(["prefix_mode", (
        0.48 * prefix +
        0.14 * ngram +
        0.12 * edit +
        0.10 * phoneticScore +
        0.08 * skeletonScore +
        0.08 * tokenScores.token
      )]);
      scores.push(["middle_mode", (
        0.38 * contains +
        0.25 * ngram +
        0.20 * subsequence +
        0.10 * tokenScores.token +
        0.07 * edit
      )]);
    }
    if (query.tokens.length > 1) {
      scores.push(["phrase_mode", (
        0.34 * tokenScores.token +
        0.20 * tokenScores.specific +
        0.16 * Math.max(edit, contains, prefix) +
        0.14 * tokenScores.common +
        0.10 * phoneticScore +
        0.06 * ngram
      )]);
    }
    if (query.skeleton.length >= 3) {
      scores.push(["skeleton_mode", 0.40 * skeletonScore + 0.25 * subsequence + 0.20 * phoneticScore + 0.15 * ngram]);
    }
    if (!scores.length) return null;
    let [mode, rawScore] = scores.sort((a, b) => b[1] - a[1])[0];
    let penalty = 0;
    if (query.compact.length <= 3 && !exact) penalty += 0.15;
    if (query.tokens.length && query.specificTokens.length === 0 && query.genericTokens.length > 0 && !exact) penalty += 0.20;
    if (candidateCount > 1000 && query.compact.length <= 5) penalty += 0.18;
    else if (candidateCount > 400 && query.compact.length <= 5) penalty += 0.10;
    const strongEvidence = exact || alias || prefix >= 0.45 || skeletonScore >= 0.85 || tokenScores.token >= 0.70;
    if (!strongEvidence && (contains > 0 || phoneticScore > 0 || ngram > 0)) penalty += 0.08;
    const finalScore = Math.max(0, Math.min(1, rawScore - penalty));
    if (finalScore <= 0) return null;

    const reasons = new Set(sources);
    if (exact) reasons.add("exact_compact");
    if (alias) reasons.add("approved_alias");
    if (edit >= 0.78) reasons.add("edit_match");
    if (weightedEdit >= 0.78) reasons.add("weighted_edit_match");
    if (prefix >= 0.30) reasons.add("prefix_match");
    if (contains >= 0.25) reasons.add("contains_match");
    if (skeletonScore >= 0.70) reasons.add("skeleton_match");
    if (phoneticScore >= 0.75) reasons.add("phonetic_match");
    if (tokenScores.token >= 0.40) reasons.add("token_match");
    if (ngram >= 0.08) reasons.add("ngram_match");
    if (penalty) reasons.add("penalized");
    reasons.add(mode);
    return { record, score: finalScore, mode, reasons };
  }

  function searchExternalCatalog(searchState, input, limit = 40) {
    const records = Array.isArray(searchState) ? searchState : searchState.records;
    const state = Array.isArray(searchState)
      ? { records, index: null, length: records.length }
      : searchState;
    const query = makeQuery(input);
    if (!query.compact) return { status: "no_match", message: "Empty query.", results: [], candidate_count: 0 };
    const candidates = state.index ? candidateRecords(state.index, query) : new Set(records);
    const scored = [];
    for (const record of candidates) {
      const sources = new Set(["external_candidate"]);
      const item = scoreExternalRecord(record, query, sources, candidates.size);
      if (item) scored.push(item);
    }
    const grouped = new Map();
    for (const item of scored) {
      const key = item.record._bc || compactKey(item.record.b || item.record.n);
      const current = grouped.get(key);
      if (!current || item.score > current.score) {
        grouped.set(key, {
          key,
          name: item.record.b || item.record.n,
          record: item.record,
          score: item.score,
          mode: item.mode,
          reasons: new Set(item.reasons),
          commercial_examples: [item.record.n],
        });
      } else {
        current.reasons = new Set([...current.reasons, ...item.reasons]);
        if (!current.commercial_examples.includes(item.record.n) && current.commercial_examples.length < 3) {
          current.commercial_examples.push(item.record.n);
        }
      }
    }
    const results = [...grouped.values()].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
    const topScore = results[0]?.score || 0;
    const secondScore = results[1]?.score || 0;
    const closeCount = results.filter(item => item.score >= topScore - 0.08).length;
    let status = "no_match";
    let message = "No safe match found.";
    if (results.length) {
      if (query.compact.length <= 2 || closeCount >= 6) {
        status = "ambiguous";
        message = "Possible matches found, but the query is ambiguous.";
      } else if (topScore >= 0.85 && topScore - secondScore >= 0.12) {
        status = "high_confidence";
        message = "High confidence external match.";
      } else if (topScore >= 0.72 && topScore - secondScore >= 0.06) {
        status = "medium_confidence";
        message = "Medium confidence external match.";
      } else if (topScore >= 0.55) {
        status = "low_confidence";
        message = "Low confidence external match.";
      }
    }
    return {
      status,
      message,
      candidate_count: candidates.size,
      results: results.slice(0, limit).map((item, index) => ({
        rank: index + 1,
        candidate_id: `EXT-${item.key}`,
        commercial_name_en: item.record.n,
        commercial_name_ar: item.record.ar,
        base_group_key: item.name || "-",
        ingredient_key: item.record.ing || item.record.s || "-",
        route_family: item.record.r || "-",
        price_egp: item.record.p,
        manufacturer: item.record.m || "-",
        drug_class: item.record.dc || "-",
        score: item.score,
        matched_signals: [...item.reasons].sort().join("|"),
        warnings: item.record._warnings.join("|"),
        needs_clarification: status !== "high_confidence" && status !== "medium_confidence",
        mode: item.mode,
        commercial_examples: item.commercial_examples,
      })),
    };
  }

  function rankWeights(query, externalStatus, hasCurrentResults, hasExternalResults) {
    let currentWeight;
    let externalWeight;
    if (query.compact.length <= 4 && !query.numbers.size) {
      currentWeight = SHORT_QUERY_CURRENT_RANK_WEIGHT;
      externalWeight = SHORT_QUERY_EXTERNAL_RANK_WEIGHT;
    } else if (query.numbers.size || query.routes.size || query.tokens.length > 3) {
      currentWeight = CONTEXT_CURRENT_RANK_WEIGHT;
      externalWeight = CONTEXT_EXTERNAL_RANK_WEIGHT;
    } else {
      currentWeight = DEFAULT_CURRENT_RANK_WEIGHT;
      externalWeight = DEFAULT_EXTERNAL_RANK_WEIGHT;
    }
    if (!EXTERNAL_CONFIDENT_STATUSES.has(externalStatus)) externalWeight *= 0.78;
    if (!hasCurrentResults && hasExternalResults) externalWeight *= 1.22;
    if (hasCurrentResults && !hasExternalResults) currentWeight *= 1.12;
    return { currentWeight, externalWeight };
  }

  function hasCurrentExactSignal(candidate) {
    return [...candidate.currentSignals].some(signal =>
      signal === "heard_spelling_alias" ||
      signal === "exact_name" ||
      signal === "exact_compact" ||
      signal === "exact_arabic_alias" ||
      signal === "exact_base_group"
    );
  }

  function hasExternalExactSignal(candidate) {
    return [...candidate.externalSignals].some(signal =>
      signal === "exact_mode" ||
      signal === "exact_match" ||
      signal === "exact_compact" ||
      signal === "exact_norm" ||
      signal === "approved_alias"
    );
  }

  function typoLikeWithoutContext(query) {
    return query.compact.length >= 5 && query.tokens.length <= 3 && !query.numbers.size && !query.routes.size;
  }

  function agreementBonus(candidate) {
    if (!candidate.currentRank || !candidate.externalRank) return 0;
    return candidate.currentRank <= 3 && candidate.externalRank <= 3 ? STRONG_AGREEMENT_BONUS : WEAK_AGREEMENT_BONUS;
  }

  function fusedScore(candidate, query, weights, externalStatus) {
    let score = 0;
    if (candidate.currentRank) {
      score += weights.currentWeight / (RRF_K + candidate.currentRank);
      score += Math.min(candidate.currentScore / 1800, 1) * 0.030;
    }
    if (candidate.externalRank) {
      score += weights.externalWeight / (RRF_K + candidate.externalRank);
      score += Math.min(candidate.externalScore, 1) * 0.035;
    }
    if (candidate.currentRank && candidate.externalRank) score += agreementBonus(candidate);
    if (typoLikeWithoutContext(query)) {
      if (candidate.externalRank === 1) score += TYPO_EXTERNAL_TOP1_BONUS;
      else if (candidate.externalRank === 2) score += TYPO_EXTERNAL_TOP2_BONUS;
    }
    if (
      !EXTERNAL_CONFIDENT_STATUSES.has(externalStatus) &&
      candidate.currentRank === 1 &&
      candidate.currentSignals.has("keyboard_proximity") &&
      keyboardProximityRatio(query.compact, candidate.key) >= 0.95
    ) {
      score += CURRENT_KEYBOARD_TOP_BONUS_WHEN_EXTERNAL_UNSURE;
    }
    if (hasCurrentExactSignal(candidate)) score += CURRENT_EXACT_BONUS;
    if (hasExternalExactSignal(candidate)) score += EXTERNAL_EXACT_BONUS;
    if (query.numbers.size || query.routes.size || query.tokens.length > 3) {
      if (candidate.currentRank) score += CONTEXT_CURRENT_BONUS;
      else if (candidate.externalRank) score -= 0.025;
    }
    return score;
  }

  function fusionNeedsClarification(candidate, query) {
    if (candidate.currentRank && candidate.currentNeedsClarification) return true;
    if (query.compact.length <= 2) return true;
    if (!candidate.currentRank) return true;
    if (!candidate.externalRank) return candidate.currentNeedsClarification;
    if (hasCurrentExactSignal(candidate) && candidate.currentRank === 1) return false;
    if (candidate.currentRank <= 3 && candidate.externalRank <= 3 && !candidate.currentNeedsClarification) return false;
    return candidate.currentNeedsClarification;
  }

  function responseStatus(ranked, query) {
    if (!ranked.length) return { status: "no_match", message: "No candidate produced by either child algorithm." };
    const top = ranked[0];
    const secondScore = ranked[1]?.masterScore || 0;
    const margin = top.masterScore - secondScore;
    const closeCount = ranked.slice(0, 8).filter(item => item.masterScore >= top.masterScore - MEDIUM_CONFIDENCE_MARGIN).length;
    if (query.compact.length <= 2) return { status: "ambiguous", message: "Query is too short. Please enter more letters." };
    if (top.needsClarification || closeCount >= 4) return { status: "ambiguous", message: "Possible matches found, but the safe answer needs clarification." };
    if (top.masterScore >= HIGH_CONFIDENCE_SCORE && margin >= HIGH_CONFIDENCE_MARGIN) return { status: "high_confidence", message: "High confidence Algorithm 4 browser match." };
    if (top.masterScore >= MEDIUM_CONFIDENCE_SCORE && margin >= MEDIUM_CONFIDENCE_MARGIN) return { status: "medium_confidence", message: "Medium confidence Algorithm 4 browser match." };
    return { status: "ambiguous", message: "Possible matches found, but scores are close." };
  }

  function collectFusionCandidate(candidates, result, rank, source) {
    const key = compactKey(result.base_group_key && result.base_group_key !== "-" ? result.base_group_key : result.commercial_name_en);
    if (!key) return;
    if (!candidates.has(key)) {
      candidates.set(key, {
        key,
        display: { ...result },
        currentRank: 0,
        externalRank: 0,
        currentScore: 0,
        externalScore: 0,
        currentNeedsClarification: true,
        currentSignals: new Set(),
        externalSignals: new Set(),
        masterScore: 0,
        needsClarification: true,
      });
    }
    const candidate = candidates.get(key);
    if (source === "current" && (!candidate.currentRank || rank < candidate.currentRank)) {
      candidate.currentRank = rank;
      candidate.currentScore = Number(result.score) || 0;
      candidate.currentNeedsClarification = Boolean(result.needs_clarification);
      candidate.currentSignals = new Set(String(result.matched_signals || "").split("|").filter(Boolean));
      candidate.display = { ...result };
    }
    if (source === "external" && (!candidate.externalRank || rank < candidate.externalRank)) {
      candidate.externalRank = rank;
      candidate.externalScore = Number(result.score) || 0;
      candidate.externalSignals = new Set(String(result.matched_signals || "").split("|").filter(Boolean));
      if (!candidate.currentRank) candidate.display = { ...result };
    }
  }

  function searchCatalog(searchState, input, limit = 20) {
    const started = performance.now ? performance.now() : Date.now();
    const state = Array.isArray(searchState)
      ? { records: searchState, stats: { prefixDanger: new Map(), shortRegistry: new Set() }, length: searchState.length }
      : searchState;
    const query = makeQuery(input);
    if (!query.norm && !query.compact) return { results: [], elapsed_ms: 0, algorithm: "algorithm_4_browser" };

    const currentResponse = searchCurrentCatalog(state, input, 40);
    const externalResponse = searchExternalCatalog(state, input, 40);
    const candidates = new Map();
    currentResponse.results.forEach((result, index) => collectFusionCandidate(candidates, result, index + 1, "current"));
    externalResponse.results.forEach((result, index) => collectFusionCandidate(candidates, result, index + 1, "external"));
    const weights = rankWeights(query, externalResponse.status, currentResponse.results.length > 0, externalResponse.results.length > 0);
    for (const candidate of candidates.values()) {
      candidate.masterScore = fusedScore(candidate, query, weights, externalResponse.status);
      candidate.needsClarification = fusionNeedsClarification(candidate, query);
    }
    const ranked = [...candidates.values()].sort((a, b) => b.masterScore - a.masterScore || Math.min(a.currentRank || 999, a.externalRank || 999) - Math.min(b.currentRank || 999, b.externalRank || 999) || a.key.localeCompare(b.key));
    const response = responseStatus(ranked, query);
    const results = ranked.slice(0, limit).map((candidate, index) => {
      const display = candidate.display;
      const signals = new Set([...candidate.currentSignals, ...[...candidate.externalSignals].map(signal => `external:${signal}`)]);
      if (candidate.currentRank) signals.add(`current_rank_${candidate.currentRank}`);
      if (candidate.externalRank) signals.add(`external_rank_${candidate.externalRank}`);
      if (candidate.currentRank && candidate.externalRank) signals.add("child_agreement");
      if (candidate.needsClarification) signals.add("master_requires_clarification");
      const source = candidate.currentRank && candidate.externalRank ? "current+external" : candidate.currentRank ? "current" : "external";
      return {
        ...display,
        rank: index + 1,
        candidate_id: `MASTER-${candidate.key}`,
        score: Math.round(candidate.masterScore * 1000),
        master_score: Number(candidate.masterScore.toFixed(6)),
        current_rank: candidate.currentRank || "",
        external_rank: candidate.externalRank || "",
        current_score: candidate.currentScore,
        external_score: Number(candidate.externalScore.toFixed(4)),
        source,
        matched_signals: [...signals].sort().join("|"),
        needs_clarification: candidate.needsClarification,
      };
    });
    const ended = performance.now ? performance.now() : Date.now();
    return {
      results,
      elapsed_ms: ended - started,
      needs_clarification: response.status === "ambiguous" || results.some(result => result.needs_clarification),
      query_status: response.status,
      message: response.message,
      algorithm: "algorithm_4_browser",
      child_candidate_count: (currentResponse.results?.length || 0) + (externalResponse.candidate_count || externalResponse.results?.length || 0),
      current_child_status: currentResponse.query_status,
      external_child_status: externalResponse.status,
      prefix_risk: currentResponse.prefix_risk,
    };
  }

  return { EXAMPLES, normalizeSearch, compactKey, prepareCatalog, searchCatalog, searchCurrentCatalog, searchExternalCatalog };
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
      const source = r.source ? badge(`V2 ${String(r.source).replace("+", " + ")}`, "source") : "";
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
            <div class="badges">${route}${source}${clarify}${warnings}</div>
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
      statusEl.textContent = `${catalog.length.toLocaleString()} medicines · V2 master`;
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
