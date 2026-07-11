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

  const VARIANT_QUALIFIERS = new Set([
    "EXTRA", "PLUS", "FORTE", "MAX", "MONO", "DUO", "ADVANCE",
    "ACTIVE", "GOLD", "SILVER", "N", "S", "SR", "XR", "MR",
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

  const CONTEXT_NOISE_TOKENS = new Set([
    "MG", "MCG", "G", "GM", "GRAM", "GRAMS", "ML", "L", "IU", "UNIT", "UNITS",
    "PERCENT", "PER", "TAB", "TABS", "TABLET", "TABLETS", "CAP", "CAPS",
    "CAPSULE", "CAPSULES", "SYRUP", "SUSP", "SUSPENSION", "VIAL", "VIALS",
    "AMP", "AMPS", "AMPOULE", "AMPOULES", "CREAM", "GEL", "OINT", "OINTMENT",
    "DROPS", "DROP", "ORAL", "TOPICAL", "INJ", "INJECTION", "FC", "FCT", "SC",
    "SR", "XR", "MR", "RETARD", "SACHET", "SACHETS",
  ]);

  const UNIT_SUFFIX_RE = /^\d+(?:\.\d+)?(?:MG|MCG|G|GM|ML|L|IU|%)$/;
  const PURE_NUMBER_RE = /^\d+(?:\.\d+)?$/;
  const VOWELS = new Set(["A", "E", "I", "O", "U", "Y"]);
  const CONFUSION_GROUPS = [
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
  const CONFUSION_PAIRS = new Set();
  for (const group of CONFUSION_GROUPS) {
    for (const left of group) {
      for (const right of group) {
        if (left !== right) CONFUSION_PAIRS.add(`${left}:${right}`);
      }
    }
  }

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

  function cleanContextTokens(value) {
    const tokens = normalizeSearch(value).split(" ").filter(Boolean);
    if (tokens.length < 2) return tokens;
    const cleaned = [];
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      const previous = tokens[index - 1] || "";
      const next = tokens[index + 1] || "";
      if (CONTEXT_NOISE_TOKENS.has(token) || UNIT_SUFFIX_RE.test(token)) continue;
      if (PURE_NUMBER_RE.test(token) && index > 0 && (
        CONTEXT_NOISE_TOKENS.has(previous) ||
        CONTEXT_NOISE_TOKENS.has(next) ||
        UNIT_SUFFIX_RE.test(next)
      )) {
        continue;
      }
      cleaned.push(token);
    }
    return cleaned.length ? cleaned : tokens;
  }

  function cleanBrandCompacts(value) {
    const out = [];
    const seen = new Set();
    for (const token of cleanContextTokens(value)) {
      if (GENERIC_TOKENS.has(token) || CONTEXT_NOISE_TOKENS.has(token)) continue;
      const compact = compactKey(token);
      if (compact.length < 3 || PURE_NUMBER_RE.test(compact) || UNIT_SUFFIX_RE.test(compact)) continue;
      if (!seen.has(compact)) {
        seen.add(compact);
        out.push(compact);
      }
    }
    return out;
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

  function charNgrams(value, n) {
    const grams = new Set();
    if (!value || value.length < n) return grams;
    for (let i = 0; i <= value.length - n; i++) grams.add(value.slice(i, i + n));
    return grams;
  }

  function jaccard(left, right) {
    if (!left.size || !right.size) return 0;
    let intersection = 0;
    for (const item of left) {
      if (right.has(item)) intersection++;
    }
    return intersection / (left.size + right.size - intersection);
  }

  function prefixScore(query, target) {
    if (!query || !target) return 0;
    let shared = 0;
    for (let i = 0; i < Math.min(query.length, target.length); i++) {
      if (query[i] !== target[i]) break;
      shared++;
    }
    return shared / Math.max(query.length, target.length);
  }

  function suffixScore(query, target) {
    if (!query || !target) return 0;
    let shared = 0;
    for (let i = 1; i <= Math.min(query.length, target.length); i++) {
      if (query[query.length - i] !== target[target.length - i]) break;
      shared++;
    }
    return shared / Math.max(query.length, target.length);
  }

  function subsequenceScore(query, target) {
    if (!query || !target || query.length > target.length) return 0;
    let pos = 0;
    let start = -1;
    let end = -1;
    for (const ch of query) {
      const found = target.indexOf(ch, pos);
      if (found < 0) return 0;
      if (start < 0) start = found;
      end = found;
      pos = found + 1;
    }
    const span = end - start + 1;
    const density = span ? query.length / span : 0;
    const coverage = query.length / target.length;
    return Math.min(1, 0.6 * density + 0.4 * coverage);
  }

  function keySimilarity(queryKey, targetKey) {
    if (!queryKey || !targetKey) return 0;
    if (queryKey === targetKey) return 1;
    if (targetKey.startsWith(queryKey) || queryKey.startsWith(targetKey)) {
      return Math.min(queryKey.length, targetKey.length) / Math.max(queryKey.length, targetKey.length);
    }
    return 0.75 * subsequenceScore(queryKey, targetKey);
  }

  function samePositionScore(query, target) {
    if (!query || !target) return 0;
    let matches = 0;
    for (let i = 0; i < Math.min(query.length, target.length); i++) {
      if (query[i] === target[i]) matches++;
    }
    return matches / Math.max(query.length, target.length);
  }

  function lengthCoverage(query, target) {
    if (!query || !target) return 0;
    return Math.min(query.length, target.length) / Math.max(query.length, target.length);
  }

  function familyGroupKey(value) {
    const tokens = normalizeSearch(value).split(" ").filter(Boolean);
    while (tokens.length > 1 && VARIANT_QUALIFIERS.has(tokens[tokens.length - 1])) tokens.pop();
    return tokens.join(" ") || normalizeSearch(value);
  }

  function isBrandLikeQuery(query) {
    if (!query.compact || query.compact.length < 4 || query.compact.length > 20) return false;
    if (query.tokens.length > 3) return false;
    return !normalizeSearch(query.raw).split(" ").some(token =>
      CONTEXT_NOISE_TOKENS.has(token) || UNIT_SUFFIX_RE.test(token)
    );
  }

  function rankScoredCandidates(items, brandLike, compact) {
    const ranked = [...items].sort((a, b) =>
      b.score - a.score || String(a.record.n).localeCompare(String(b.record.n))
    );
    if (!brandLike || ranked.length < 2 || ranked[0].rawEditDistance === 0) return ranked;

    const top = ranked[0];
    const eligible = ranked.slice(1).filter(candidate => {
      if (candidate.rawEditDistance >= top.rawEditDistance) return false;
      const scoreGap = top.score - candidate.score;
      const pureGapEdit = candidate.rawEditDistance <= 2 &&
        Math.abs(compact.length - candidate.record._bc.length) === candidate.rawEditDistance &&
        scoreGap <= 120;
      const topTokens = normalizeSearch(top.record.b || top.record.n).split(" ").filter(Boolean);
      const candidateTokens = normalizeSearch(candidate.record.b || candidate.record.n).split(" ").filter(Boolean);
      const multiTokenFalsePositive = topTokens.length > 1 && candidateTokens.length === 1 &&
        candidate.rawEditDistance <= 2 && scoreGap <= 90;
      return pureGapEdit || multiTokenFalsePositive;
    });
    if (!eligible.length) return ranked;
    eligible.sort((a, b) => a.rawEditDistance - b.rawEditDistance || b.score - a.score);
    const best = eligible[0];
    return [best, ...ranked.filter(item => item !== best)];
  }

  function substitutionCost(left, right) {
    if (left === right) return 0;
    if (CONFUSION_PAIRS.has(`${left}:${right}`)) return 0.45;
    if (VOWELS.has(left) && VOWELS.has(right)) return 0.70;
    return 1;
  }

  function damerauDistance(left, right, weighted = false) {
    if (left === right) return 0;
    let prevPrev = null;
    let prev = Array.from({ length: right.length + 1 }, (_, i) => i);
    for (let i = 1; i <= left.length; i++) {
      const cur = [i, ...Array(right.length).fill(0)];
      const prevLeft = i > 1 ? left[i - 2] : "";
      for (let j = 1; j <= right.length; j++) {
        const leftChar = left[i - 1];
        const rightChar = right[j - 1];
        const subCost = weighted ? substitutionCost(leftChar, rightChar) : (leftChar === rightChar ? 0 : 1);
        let value = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + subCost);
        if (prevPrev && j > 1 && leftChar === right[j - 2] && prevLeft === rightChar) {
          value = Math.min(value, prevPrev[j - 2] + (weighted ? 0.55 : 1));
        }
        cur[j] = value;
      }
      prevPrev = prev;
      prev = cur;
    }
    return prev[right.length];
  }

  function normalizedEditSimilarity(left, right, weighted = false) {
    if (!left || !right) return 0;
    return Math.max(0, 1 - damerauDistance(left, right, weighted) / Math.max(left.length, right.length));
  }

  function confusableChars(char) {
    if (!char) return new Set();
    const upper = char.toUpperCase();
    const out = new Set();
    for (const group of CONFUSION_GROUPS) {
      if (group.has(upper)) {
        for (const member of group) {
          if (member !== upper) out.add(member);
        }
      }
    }
    return out;
  }

  function firstCharVariants(value) {
    if (!value) return new Set();
    const out = new Set();
    for (const char of confusableChars(value[0])) out.add(char + value.slice(1));
    return out;
  }

  function firstCharsConfusable(left, right) {
    if (!left || !right) return false;
    return confusableChars(left).has(right);
  }

  function isPartialPrefixMatch(query, target) {
    if (!query || !target) return false;
    if (Math.abs(query.length - target.length) < 2) return false;
    const shorter = query.length < target.length ? query : target;
    const longer = shorter === query ? target : query;
    return longer.startsWith(shorter) && shorter.length / longer.length < 0.86;
  }

  function maxDeletesFor(value) {
    if (value.length < 4) return 0;
    return value.length <= 7 ? 1 : 2;
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

  function rescueScoreForCompact(queryCompact, record) {
    if (!queryCompact || !record._bc) return null;
    if (queryCompact.length < 4 || queryCompact.length > 18 || record._bc.length > 24) return null;
    const lengthDelta = Math.abs(queryCompact.length - record._bc.length);
    if (lengthDelta > 5 && !record._bc.startsWith(queryCompact.slice(0, 4))) return null;

    const edit = normalizedEditSimilarity(queryCompact, record._bc, false);
    const weighted = normalizedEditSimilarity(queryCompact, record._bc, true);
    const prefix = prefixScore(queryCompact, record._bc);
    const suffix = suffixScore(queryCompact, record._bc);
    const grams = jaccard(charNgrams(queryCompact, 3), charNgrams(record._bc, 3));
    const skeletonScore = keySimilarity(skeleton(queryCompact), record._sk);
    const phoneticScore = keySimilarity(drugPhoneticKey(queryCompact), record._ph);
    const subseq = subsequenceScore(queryCompact, record._bc);
    const positional = samePositionScore(queryCompact, record._bc);
    const coverage = lengthCoverage(queryCompact, record._bc);

    let score = (
      0.58 * edit +
      0.52 * weighted +
      0.16 * prefix +
      0.10 * suffix +
      0.18 * grams +
      0.16 * skeletonScore +
      0.14 * phoneticScore +
      0.10 * subseq +
      0.24 * positional +
      0.16 * coverage
    );
    if (queryCompact[0] && record._bc[0] && queryCompact[0] === record._bc[0]) score += 0.12;
    else if (firstCharsConfusable(queryCompact[0], record._bc[0])) score += 0.06;
    if (lengthDelta <= 1 && weighted >= 0.76) score += 0.18;
    if (prefix >= 0.55 && weighted >= 0.66) score += 0.08;
    if (weighted >= 0.84 && positional >= 0.70) score += 0.22;
    if (isPartialPrefixMatch(queryCompact, record._bc) && weighted < 0.84) {
      score -= 0.18 + Math.min(0.24, 0.05 * lengthDelta);
    }
    if (Math.max(edit, weighted) < 0.58 && Math.max(skeletonScore, phoneticScore) < 0.72) score -= 0.20;
    if (prefix < 0.30 && grams < 0.12 && Math.max(edit, weighted) < 0.70) score -= 0.10;

    return { score, edit, weighted, prefix, suffix, grams, skeletonScore, phoneticScore, positional };
  }

  function bestRescueScore(record, query) {
    const values = [query.compact, ...(query.brandCompacts || [])].filter(Boolean);
    let best = null;
    for (const value of values) {
      const current = rescueScoreForCompact(value, record);
      if (current && (!best || current.score > best.score)) best = current;
    }
    return best;
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

  function addGramsIndex(index, value, record, n = 3) {
    if (!value || value.length < n) return;
    const seen = new Set();
    for (let i = 0; i <= value.length - n; i++) seen.add(value.slice(i, i + n));
    for (const gram of seen) addIndex(index, gram, record);
  }

  function addSuffixIndex(index, value, record, minLen = 3, maxLen = 12) {
    if (!value) return;
    const reversed = value.split("").reverse().join("");
    for (let length = minLen; length <= Math.min(maxLen, reversed.length); length++) {
      addIndex(index, reversed.slice(0, length), record);
    }
  }

  function rarestGrams(value, n, index, limit) {
    const grams = [...charNgrams(value, n)].filter(gram => index.has(gram));
    grams.sort((left, right) => (index.get(left)?.size || 0) - (index.get(right)?.size || 0));
    return grams.slice(0, limit);
  }

  function buildIndex(records) {
    const index = {
      exact: new Map(),
      prefix: new Map(),
      grams: new Map(),
      grams4: new Map(),
      suffix: new Map(),
      token: new Map(),
      skeleton: new Map(),
      skeletonPrefix: new Map(),
      baseExact: new Map(),
      delete: new Map(),
      phonetic: new Map(),
      phoneticPrefix: new Map(),
      baseLength: new Map(),
      firstChar: new Map(),
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
        addGramsIndex(index.grams4, value, record, 4);
        addSuffixIndex(index.suffix, value, record);
      }
      for (const token of new Set(tokensOf(`${record.n || ""} ${record.b || ""} ${record.ing || ""} ${record.s || ""}`))) {
        addIndex(index.token, token, record);
      }
      addIndex(index.skeleton, record._sk, record);
      addPrefixIndex(index.skeletonPrefix, record._sk, record, 10);
      addIndex(index.baseExact, record._bc, record);
      if (record._bc) {
        addIndex(index.baseLength, String(record._bc.length), record);
        addIndex(index.firstChar, record._bc[0], record);
        const maxDeletes = maxDeletesFor(record._bc);
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
      } else if (!genericToken && tc.length >= 4 && record._bc.startsWith(tc)) {
        addScore(state, 460 + Math.min(tc.length, 18), "context_clean_prefix_base");
        tokenHits++;
      } else if (!genericToken && tc.length >= 4 && record._bc.includes(tc)) {
        addScore(state, 260, "context_clean_contains_base");
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

    const rescue = bestRescueScore(record, query);
    if (rescue && rescue.score >= 0.88) {
      addScore(state, 620 * rescue.score, "algorithm4_family_rescue");
      if (rescue.weighted >= 0.76) state.signals.add("algorithm4_weighted_confusion_edit");
      if (rescue.positional >= 0.68) state.signals.add("algorithm4_position_overlap");
      if (rescue.phoneticScore >= 0.78) state.signals.add("algorithm4_phonetic_family");
      if (rescue.skeletonScore >= 0.80) state.signals.add("algorithm4_skeleton_family");
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
    for (const variant of firstCharVariants(query.compact)) {
      addCandidates(ids, searchIndex.prefix.get(variant.slice(0, Math.min(12, variant.length))));
    }

    if (query.compact.length >= 3) {
      for (const gram of rarestGrams(query.compact, 4, searchIndex.grams4, 4)) addCandidates(ids, searchIndex.grams4.get(gram));
      const gramLimit = ids.size < 160 ? 5 : 1;
      for (const gram of rarestGrams(query.compact, 3, searchIndex.grams, gramLimit)) addCandidates(ids, searchIndex.grams.get(gram));
    }

    if (query.compact.length >= 4) {
      const reversed = query.compact.split("").reverse().join("");
      addCandidates(ids, searchIndex.suffix.get(reversed.slice(0, Math.min(12, reversed.length))));
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
        addCandidates(ids, searchIndex.skeletonPrefix.get(unit.skeleton.slice(0, Math.min(10, unit.skeleton.length))));
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

    const shouldRescueScan = query.compact.length >= 4 && query.compact.length <= 12 && ids.size < 1600;
    if (shouldRescueScan) {
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

  function searchCatalog(searchState, input, limit = 20, options = {}) {
    const started = performance.now ? performance.now() : Date.now();
    const request = typeof input === "object" && input !== null ? input : options;
    const inputText = typeof input === "object" && input !== null
      ? String(input.text || input.query || "")
      : String(input || "");
    const unreadableContinuation = Boolean(
      request.unreadableContinuation || request.unreadable_continuation
    );
    const records = Array.isArray(searchState) ? searchState : searchState.records;
    const state = Array.isArray(searchState)
      ? { records, stats: { prefixDanger: new Map(), shortRegistry: new Set() }, length: records.length }
      : searchState;
    const query = {
      raw: inputText,
      norm: normalizeSearch(inputText),
      compact: compactKey(inputText),
      tokens: tokensOf(inputText),
      numbers: parseNumbers(inputText),
      routes: parseRouteHints(inputText),
    };
    query.tokenCompacts = query.tokens.map(compactKey);
    query.brandCompacts = cleanBrandCompacts(inputText);
    query.genericTokens = query.tokens.filter(token => GENERIC_TOKENS.has(token));
    query.specificTokens = query.tokens.filter(token => !GENERIC_TOKENS.has(token));
    query.genericTokenCompacts = query.genericTokens.map(compactKey);
    query.specificTokenCompacts = query.specificTokens.map(compactKey);
    query.visualCompacts = visualVariants(inputText);
    query.phonetic = drugPhoneticKey(inputText);
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
      const rawEditDistance = damerauDistance(query.compact, record._bc, false);
      const weightedEditDistance = damerauDistance(query.compact, record._bc, true);
      const positionalEvidence = samePositionScore(query.compact, record._bc);
      const edgeEvidence = Math.max(prefixScore(query.compact, record._bc), suffixScore(query.compact, record._bc));
      scored.push({
        record,
        score: state.score,
        signals: state.signals,
        rawEditDistance,
        weightedEditDistance,
        positionalEvidence,
        edgeEvidence,
      });
    }

    let rankedPool = scored;
    if (unreadableContinuation) {
      const longerPrefixMatches = scored.filter(item =>
        item.record._bc.startsWith(query.compact) && item.record._bc.length > query.compact.length
      );
      if (longerPrefixMatches.length) {
        rankedPool = longerPrefixMatches;
        for (const item of rankedPool) {
          item.score += 1800;
          item.signals.add("known_unreadable_continuation");
        }
      }
    }

    const brandLike = isBrandLikeQuery(query) && !unreadableContinuation;
    rankedPool = rankScoredCandidates(rankedPool, brandLike, query.compact);
    if (!unreadableContinuation && rankedPool.length && rankedPool[0].rawEditDistance === 0) {
      const exactGroup = familyGroupKey(rankedPool[0].record.b || rankedPool[0].record.n);
      const relatedVariants = rankedPool.filter((item, index) =>
        index > 0 &&
        familyGroupKey(item.record.b || item.record.n) === exactGroup &&
        item.record.b !== rankedPool[0].record.b
      );
      if (relatedVariants.length) {
        const relatedSet = new Set(relatedVariants);
        rankedPool = [rankedPool[0], ...relatedVariants, ...rankedPool.slice(1).filter(item => !relatedSet.has(item))];
      }
    }
    const top = rankedPool.slice(0, limit);
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
        raw_edit_distance: item.rawEditDistance,
        weighted_edit_distance: Number(item.weightedEditDistance.toFixed(3)),
        positional_evidence: Number(item.positionalEvidence.toFixed(3)),
        edge_evidence: Number(item.edgeEvidence.toFixed(3)),
        family_group_key: familyGroupKey(record.b || record.n),
        matched_signals: [...item.signals].sort().join("|"),
        warnings: record._warnings.join("|"),
        needs_clarification: needsClarification,
      };
    });

    const ended = performance.now ? performance.now() : Date.now();
    const needsClarification = results.some(result => result.needs_clarification);
    const topFamilyGroups = new Set(results.slice(0, 8).map(result => result.family_group_key));
    const equalTopDistance = results.length > 1 &&
      results[0].raw_edit_distance === results[1].raw_edit_distance &&
      results[0].base_group_key !== results[1].base_group_key;
    let decisionType = needsClarification ? "possible_matches" : "ranked_matches";
    if (unreadableContinuation) decisionType = "unreadable_continuation_matches";
    else if (results.length && results.some(result =>
      result.family_group_key === results[0].family_group_key &&
      result.base_group_key !== results[0].base_group_key
    )) decisionType = "family_variant_selection";
    else if (equalTopDistance) decisionType = "equal_distance_ambiguity";
    else if (topFamilyGroups.size > 1 && needsClarification) decisionType = "collision_ambiguity";
    return {
      results,
      elapsed_ms: ended - started,
      candidate_count: candidates ? candidates.size : records.length,
      needs_clarification: needsClarification,
      query_status: decisionType,
      decision_type: decisionType,
      unreadable_continuation: unreadableContinuation,
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
  const unreadableContinuationInput = document.getElementById("unreadableContinuation");
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
    const decision = data.decision_type || data.query_status;
    const messages = {
      unreadable_continuation_matches: `Longer names beginning with "${query}"`,
      family_variant_selection: `Choose the exact variant for "${query}"`,
      equal_distance_ambiguity: `Several medicines have equal spelling evidence for "${query}"`,
      collision_ambiguity: `Compare the possible medicines for "${query}"`,
      possible_matches: `Possible matches for "${query}"`,
      ranked_matches: `Matches for "${query}"`,
    };
    summaryEl.textContent = messages[decision] || `Possible matches for "${query}"`;
  }

  function groupedResults(rows) {
    const groups = new Map();
    for (const row of rows) {
      const key = row.family_group_key || row.base_group_key || row.commercial_name_en;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    return [...groups.entries()].map(([key, items]) => ({ key, items }));
  }

  function renderBadges(row) {
    const warnings = splitPipes(row.warnings).map(w => badge(humanWarning(w), "warn")).join("");
    const clarify = row.needs_clarification ? badge("confirmation required", "ask") : "";
    const route = row.route_family && row.route_family !== "-" ? badge(humanRoute(row.route_family)) : "";
    return `${route}${clarify}${warnings}`;
  }

  function renderSingleResult(row, displayedRank) {
    return `
      <article class="result">
        <div class="rank">${esc(displayedRank)}</div>
        <div>
          <div class="name-row">
            <div class="name" dir="auto">${esc(row.commercial_name_en)}</div>
            <div class="price">${esc(row.price_egp || "-")} EGP</div>
          </div>
          <div class="primary-meta">
            <span dir="auto">${esc(row.commercial_name_ar || "-")}</span>
            <span dir="auto">${esc(row.ingredient_key || "-")}</span>
          </div>
          <div class="secondary-meta">
            <div><b>Family:</b> ${esc(row.base_group_key || "-")}</div>
            <div><b>Manufacturer:</b> ${esc(row.manufacturer || "-")}</div>
            <div><b>Class:</b> ${esc(row.drug_class || "-")}</div>
          </div>
          <div class="badges">${renderBadges(row)}</div>
        </div>
      </article>`;
  }

  function renderFamilyGroup(group, displayedRank) {
    const variantsByBase = new Map();
    for (const row of group.items) {
      if (!variantsByBase.has(row.base_group_key)) variantsByBase.set(row.base_group_key, row);
    }
    const variants = [...variantsByBase.values()];
    if (variants.length <= 1) return renderSingleResult(variants[0], displayedRank);

    const groupId = `family-${displayedRank}-${MedSearch.compactKey(group.key)}`;
    return `
      <article class="result family-result">
        <div class="rank">${esc(displayedRank)}</div>
        <div>
          <div class="name-row">
            <div class="name" dir="auto">${esc(group.key)} family</div>
            ${badge("choose variant", "ask")}
          </div>
          <div class="variant-list">
            ${variants.slice(0, 6).map((row, index) => `
              <label class="variant-option">
                <input type="radio" name="${esc(groupId)}" value="${esc(row.commercial_name_en)}">
                <span class="variant-copy">
                  <span class="variant-name" dir="auto">${esc(row.base_group_key)}</span>
                  <span class="variant-meta" dir="auto">${esc(row.ingredient_key || "-")} · ${esc(humanRoute(row.route_family || "unknown"))}</span>
                  <span class="variant-product" dir="auto">${esc(row.commercial_name_en)}</span>
                </span>
                <span class="variant-price">${esc(row.price_egp || "-")} EGP</span>
              </label>`).join("")}
          </div>
        </div>
      </article>`;
  }

  function renderResults(data) {
    const rows = data.results || [];
    if (!rows.length) {
      resultsEl.innerHTML = `<div class="empty">No matches. Try the brand only, remove the strength, or use the Arabic name.</div>`;
      return;
    }
    resultsEl.innerHTML = groupedResults(rows)
      .map((group, index) => renderFamilyGroup(group, index + 1))
      .join("");

    for (const input of resultsEl.querySelectorAll(".variant-option input")) {
      input.addEventListener("change", () => {
        for (const option of input.closest(".variant-list").querySelectorAll(".variant-option")) {
          option.classList.toggle("selected", option.contains(input) && input.checked);
        }
      });
    }
  }

  function search() {
    const q = queryInput.value.trim();
    showError("");
    if (!q) {
      resultsEl.innerHTML = `<div class="empty">Type a medicine name first.</div>`;
      renderSummary({ results: [] }, "");
      return;
    }
    const data = MedSearch.searchCatalog(catalog, q, 20, {
      unreadableContinuation: Boolean(unreadableContinuationInput?.checked),
    });
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
  unreadableContinuationInput?.addEventListener("change", () => {
    if (queryInput.value.trim()) search();
  });

  searchBtn.disabled = true;
  loadCatalog();
}
