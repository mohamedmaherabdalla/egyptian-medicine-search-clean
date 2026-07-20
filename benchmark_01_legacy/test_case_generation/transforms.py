"""Pure mutation functions for commercial-name stress cases.

Problem: each test category needs deterministic noisy inputs derived from real
commercial names while keeping generation logic easy to unit test.
Inputs: typed CatalogRecord objects and, for ambiguity cases, CatalogIndex.
Outputs: Mutation objects with input text, error type, notes, and optional risk
overrides.
Edge cases: short names, names without vowels, names without separators, missing
ingredient/manufacturer/class fields, and mutations equal to the source.
Failure modes: invalid generated empty queries raise ValueError in the helper;
category generators catch only expected absence by receiving an empty list.
Algorithm choice: rule-based transforms were chosen over synthetic random noise
because every emitted case must be explainable to pharmacists and searchable in
the category-level score table.
"""

from __future__ import annotations

from collections.abc import Callable

from .catalog_io import CatalogIndex
from .config import (
    ABBREVIATION_EXPANSIONS,
    FORM_WORD_BY_ROUTE,
    GENERIC_PREFIX_SUFFIX_WORDS,
    MIN_SHARED_SUFFIX_FAMILY_SIZE,
    QUALIFIER_SYNONYMS,
    QWERTY_ROWS,
    ROUTE_NOISE_WORDS,
    SOUND_GROUPS,
    STATUS_MARKERS,
    SUFFIX_FAMILIES,
    T9_GROUPS,
    VOWELS,
)
from .models import CatalogRecord, Mutation
from .normalization import latin_tokens, lower_query


def all_position_deletions(record: CatalogRecord) -> list[Mutation]:
    """Generate one-character deletion cases for every name position."""

    base = record.base_group_compact
    if len(base) < 2:
        return []
    out: list[Mutation] = []
    for pos, char in enumerate(base):
        mutated = base[:pos] + base[pos + 1 :]
        note = f"deleted '{char}' at compact position {pos}"
        out.append(_mutation(mutated, f"delete_pos_{pos}", note))
    return out


def keyboard_adjacent_substitutions(record: CatalogRecord) -> list[Mutation]:
    """Generate QWERTY-neighbor substitutions at name positions."""

    neighbors = _qwerty_neighbors()
    return _single_char_substitutions(
        record.base_group_compact,
        neighbors,
        "keyboard_adjacent",
        "QWERTY neighboring key",
    )


def vowel_substitutions(record: CatalogRecord) -> list[Mutation]:
    """Generate vowel-to-vowel spelling substitutions."""

    replacements = {vowel: [v for v in VOWELS if v != vowel] for vowel in VOWELS}
    return _single_char_substitutions(
        record.base_group_compact,
        replacements,
        "vowel_substitution",
        "vowel spelling substitution",
    )


def all_position_transpositions(record: CatalogRecord) -> list[Mutation]:
    """Generate adjacent-character swaps across the compact name."""

    base = record.base_group_compact
    out: list[Mutation] = []
    for pos in range(len(base) - 1):
        if base[pos] == base[pos + 1]:
            continue
        mutated = base[:pos] + base[pos + 1] + base[pos] + base[pos + 2 :]
        note = f"swapped compact positions {pos} and {pos + 1}"
        out.append(_mutation(mutated, f"transpose_pos_{pos}", note))
    return out


def phonetic_substitutions(record: CatalogRecord) -> list[Mutation]:
    """Generate sound-equivalent substitutions for drug-name spelling."""

    out = _single_char_substitutions(
        record.base_group_compact,
        _sound_neighbors(),
        "phonetic_substitution",
        "sound-equivalent letter substitution",
    )
    out.extend(_substring_replacements(record.base_group_compact, (("PH", "F"), ("F", "PH"))))
    return out


def initial_sound_confusions(record: CatalogRecord) -> list[Mutation]:
    """Generate first-letter substitutions within sound groups."""

    base = record.base_group_compact
    if not base:
        return []
    replacements = _sound_neighbors().get(base[0], [])
    out: list[Mutation] = []
    for replacement in replacements:
        mutated = replacement + base[1:]
        note = f"initial sound confusion {base[0]}->{replacement}"
        out.append(_mutation(mutated, f"initial_{base[0]}_to_{replacement}", note))
    return out


def single_vowel_deletions(record: CatalogRecord) -> list[Mutation]:
    """Generate deletion of one vowel at a time."""

    base = record.base_group_compact
    out: list[Mutation] = []
    for pos, char in enumerate(base):
        if char not in VOWELS:
            continue
        mutated = base[:pos] + base[pos + 1 :]
        note = f"deleted vowel '{char}' at compact position {pos}"
        out.append(_mutation(mutated, f"delete_vowel_{char}_pos_{pos}", note))
    return out


def consonant_skeleton(record: CatalogRecord) -> list[Mutation]:
    """Generate vowel-stripped commercial-name skeletons."""

    skeleton = "".join(ch for ch in record.base_group_compact if ch not in VOWELS)
    if skeleton == record.base_group_compact or len(skeleton) < 3:
        return []
    return [_mutation(skeleton, "consonant_skeleton", "removed all vowels")]


def mobile_keypad_confusions(record: CatalogRecord) -> list[Mutation]:
    """Generate T9/mobile-keypad same-key letter substitutions."""

    replacements: dict[str, list[str]] = {}
    for group in T9_GROUPS:
        for char in group:
            replacements[char] = [candidate for candidate in group if candidate != char]
    return _single_char_substitutions(
        record.base_group_compact,
        replacements,
        "mobile_keypad",
        "same mobile keypad group",
    )


def separator_removals(record: CatalogRecord) -> list[Mutation]:
    """Generate separator-removal cases for spaced or punctuated names."""

    tokens = latin_tokens(record.base_group_key)
    if len(tokens) < 2:
        return []
    compact = "".join(tokens)
    note = "removed spaces and separators from base group"
    return [_mutation(compact, "separator_removal", note)]


def token_order_transpositions(record: CatalogRecord) -> list[Mutation]:
    """Generate reversed and first-token-swapped multi-token cases."""

    tokens = latin_tokens(record.base_group_key)
    if len(tokens) < 2:
        return []
    reversed_query = " ".join(reversed(tokens))
    out = [_mutation(reversed_query, "token_order_reversed", "reversed token order")]
    if len(tokens) > 2:
        swapped = [tokens[1], tokens[0], *tokens[2:]]
        out.append(_mutation(" ".join(swapped), "token_order_swap_first_two", "swapped first two tokens"))
    return out


def ocr_digit_letter_substitutions(record: CatalogRecord) -> list[Mutation]:
    """Generate OCR-style digit/letter confusions."""

    replacements = {
        "O": ["0"], "I": ["1"], "L": ["1"], "S": ["5"], "B": ["8"],
        "Z": ["2"], "G": ["6"], "A": ["4"], "E": ["3"],
    }
    return _single_char_substitutions(
        record.base_group_compact,
        replacements,
        "ocr_digit_letter",
        "OCR digit-letter substitution",
    )


def space_insertions_inside_brand(record: CatalogRecord) -> list[Mutation]:
    """Generate cases with spaces inserted inside compact brand text."""

    base = record.base_group_compact
    positions = sorted({2, len(base) // 2, max(len(base) - 2, 1)})
    out: list[Mutation] = []
    for pos in positions:
        if 0 < pos < len(base):
            mutated = f"{base[:pos]} {base[pos:]}"
            out.append(_mutation(mutated, f"space_insert_pos_{pos}", f"inserted space at {pos}"))
    return out


def visual_ligature_confusions(record: CatalogRecord) -> list[Mutation]:
    """Generate multi-character visual confusions such as RN/M and CL/D."""

    pairs = (
        ("RN", "M"), ("M", "RN"), ("CL", "D"), ("D", "CL"), ("RI", "N"),
        ("N", "RI"), ("LI", "H"), ("H", "LI"), ("AL", "D"), ("W", "UU"),
        ("NN", "M"), ("IU", "W"),
    )
    return _substring_replacements(record.base_group_compact, pairs)


def keyboard_shift_whole_word(record: CatalogRecord) -> list[Mutation]:
    """Generate whole-name left and right keyboard-shift cases."""

    left_map, right_map = _keyboard_shift_maps()
    out: list[Mutation] = []
    for direction, mapping in (("left", left_map), ("right", right_map)):
        shifted = "".join(mapping.get(char, char) for char in record.base_group_compact)
        if shifted != record.base_group_compact:
            out.append(_mutation(shifted, f"keyboard_shift_{direction}", f"whole word shifted {direction}"))
    return out


def suffix_family_confusions(record: CatalogRecord, index: CatalogIndex) -> list[Mutation]:
    """Generate degraded-prefix cases where a shared suffix stays visible."""

    base = record.base_group_compact
    out: list[Mutation] = []
    for suffix in _shared_suffixes_for(record, index):
        if len(base) <= len(suffix) + 1:
            continue
        prefix = _degrade_prefix(base[: -len(suffix)])
        collisions = index.suffix_collisions_for(suffix, record.base_group_key)
        note = f"suffix -{suffix} shared by catalog families; prefix degraded"
        out.append(_mutation(prefix + suffix, f"suffix_family_{suffix}", note, collisions, "CAUTION", "EXTREME"))
    return out


def duplicate_syllables(record: CatalogRecord) -> list[Mutation]:
    """Generate repeated-prefix/syllable typing cases."""

    base = record.base_group_compact
    out: list[Mutation] = []
    for size in (2, 3):
        if len(base) > size * 2:
            duplicated = base[:size] + base
            out.append(_mutation(duplicated, f"duplicate_prefix_{size}", f"duplicated first {size} chars"))
    return out


def digraph_soundalikes(record: CatalogRecord) -> list[Mutation]:
    """Generate English digraph soundalike substitutions."""

    pairs = (
        ("CH", "SH"), ("SH", "CH"), ("TH", "T"), ("PH", "F"), ("CK", "K"),
        ("QU", "KW"), ("KW", "QU"), ("KS", "X"), ("X", "KS"), ("TION", "SHUN"),
    )
    return _substring_replacements(record.base_group_compact, pairs)


def token_drops(record: CatalogRecord) -> list[Mutation]:
    """Generate dropped-token cases for multi-token commercial families."""

    tokens = latin_tokens(record.base_group_key)
    if len(tokens) < 2:
        return []
    out = [_mutation(" ".join(tokens[:-1]), "drop_last_token", "dropped last brand token")]
    if len(tokens) > 2:
        out.append(_mutation(" ".join(tokens[1:]), "drop_first_token", "dropped first brand token"))
    return out


def form_word_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate commercial name plus dosage-form words."""

    words = FORM_WORD_BY_ROUTE.get(record.route_family, ("tablet", "capsule", "injection"))
    return [_mutation(f"{record.base_group_key} {word}", f"form_word_{word}", "added dosage-form word") for word in words]


def ingredient_name_queries(record: CatalogRecord) -> list[Mutation]:
    """Generate ingredient-only query cases."""

    if not record.scientific_name:
        return []
    note = "query uses ingredient/composition instead of commercial family"
    return [_mutation(record.scientific_name, "ingredient_name_query", note)]


def manufacturer_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate manufacturer text before and after the commercial family."""

    if not record.manufacturer_primary:
        return []
    name = record.base_group_key
    manufacturer = record.manufacturer_primary
    return [
        _mutation(f"{name} {manufacturer}", "manufacturer_suffix", "manufacturer after brand"),
        _mutation(f"{manufacturer} {name}", "manufacturer_prefix", "manufacturer before brand"),
    ]


def therapeutic_class_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate therapeutic class context around the brand."""

    if not record.drug_class_top:
        return []
    note = "added therapeutic class context"
    return [_mutation(f"{record.base_group_key} {record.drug_class_top}", "therapeutic_class_noise", note)]


def route_word_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate route/body-site context around the brand."""

    route_word = ROUTE_NOISE_WORDS.get(record.route_family, "")
    if not route_word:
        return []
    return [_mutation(f"{record.base_group_key} {route_word}", "route_word_noise", "added route words")]


def status_marker_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate catalog status/warning marker context."""

    out = [_mutation(f"{record.base_group_key} {marker}", f"status_marker_{i}", "added status marker") for i, marker in enumerate(STATUS_MARKERS)]
    if record.review_reasons:
        out.append(_mutation(f"{record.base_group_key} review warning", "status_review_warning", "added review warning"))
    return out


def prefix_suffix_extra_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate generic search words around the commercial family."""

    out: list[Mutation] = []
    for word in GENERIC_PREFIX_SUFFIX_WORDS:
        out.append(_mutation(f"{word} {record.base_group_key}", f"generic_prefix_{word}", "generic prefix noise"))
        out.append(_mutation(f"{record.base_group_key} {word}", f"generic_suffix_{word}", "generic suffix noise"))
    return out


def strength_unit_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate strength/unit rewrite cases from product names."""

    source = record.commercial_name_norm or record.base_group_key
    if not any(unit in source.split() for unit in ("MG", "MCG", "G", "GM", "ML", "IU", "I U")):
        return [_mutation(f"{record.base_group_key} 500 mg", "synthetic_strength_mg", "added synthetic strength")]
    rewritten = source.replace("MG", "milligram").replace("MCG", "microgram")
    rewritten = rewritten.replace("ML", "milliliter").replace("IU", "international unit")
    return [_mutation(rewritten, "strength_unit_rewrite", "rewrote strength/unit tokens")]


def decimal_slash_strength_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate decimal and slash strength perturbations."""

    source = record.commercial_name_norm or record.base_group_key
    out: list[Mutation] = []
    if "." in source:
        out.append(_mutation(source.replace(".", ""), "decimal_removed", "removed decimal point"))
        out.append(_mutation(source.replace(".", ","), "decimal_comma", "used comma decimal mark"))
    if "/" in record.commercial_name_en:
        out.append(_mutation(record.commercial_name_en.replace("/", " per "), "slash_to_per", "rewrote slash"))
    if not out:
        out.append(_mutation(f"{record.base_group_key} 0.5 mg per ml", "synthetic_decimal_strength", "added decimal strength"))
    return out


def symbol_synonyms(record: CatalogRecord) -> list[Mutation]:
    """Generate symbol-to-word cases for plus, percent, ampersand, and slash."""

    source = record.commercial_name_en
    replacements = (("&", " and "), ("+", " plus "), ("%", " percent "), ("/", " per "), ("*", " star "))
    out: list[Mutation] = []
    for src, dst in replacements:
        if src in source:
            out.append(_mutation(source.replace(src, dst), f"symbol_{src}_to_word", "rewrote symbol as word"))
    return out


def qualifier_synonym_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate qualifier synonym cases such as PLUS/+ and XR/extended."""

    source = record.base_group_key
    out: list[Mutation] = []
    for src, dst in QUALIFIER_SYNONYMS:
        if src in source.split():
            out.append(_mutation(source.replace(src, dst), f"qualifier_{src}_to_synonym", "rewrote qualifier"))
    out.append(_mutation(f"{source} plus", "qualifier_added_plus", "added common qualifier"))
    return out


def brand_ingredient_mixed_queries(record: CatalogRecord) -> list[Mutation]:
    """Generate mixed brand plus ingredient queries."""

    if not record.scientific_name:
        return []
    ingredient = " ".join(latin_tokens(record.scientific_name)[:4])
    if not ingredient:
        return []
    note = "mixed commercial family and ingredient text"
    return [_mutation(f"{record.base_group_key} {ingredient}", "brand_ingredient_mixed", note)]


def parenthetical_noise(record: CatalogRecord) -> list[Mutation]:
    """Generate parenthetical company/package noise around the brand."""

    detail = record.manufacturer_primary or record.route_family or "package"
    return [_mutation(f"{record.base_group_key} ({detail})", "parenthetical_added", "added parenthetical text")]


def abbreviation_expansions(record: CatalogRecord) -> list[Mutation]:
    """Generate expanded medical/catalog abbreviation cases."""

    source = record.commercial_name_norm
    out: list[Mutation] = []
    for abbreviation, expansion in ABBREVIATION_EXPANSIONS.items():
        if abbreviation in source.split() or abbreviation in source:
            mutated = source.replace(abbreviation, expansion)
            out.append(_mutation(mutated, f"abbrev_{abbreviation.replace(' ', '_')}", "expanded abbreviation"))
    return out


def partial_prefix_ambiguities(record: CatalogRecord, index: CatalogIndex) -> list[Mutation]:
    """Generate ambiguous short-prefix queries."""

    out: list[Mutation] = []
    base = record.base_group_compact
    for length in range(2, 5):
        if len(base) < length:
            continue
        prefix = base[:length]
        collisions = index.prefix_collisions_for(prefix, record.base_group_key)
        if not collisions:
            continue
        danger = "DANGEROUS" if index.has_ingredient_collision(record.base_group_key, collisions) else "CAUTION"
        note = "short prefix can match multiple families; UI should ask for more input"
        out.append(_mutation(prefix, f"partial_prefix_len_{length}", note, collisions, danger, "EXTREME"))
    return out


def truncation_collisions(record: CatalogRecord, index: CatalogIndex) -> list[Mutation]:
    """Generate cases where another real short family is a prefix."""

    out: list[Mutation] = []
    base = record.base_group_compact
    for compact, candidates in index.base_by_compact.items():
        if compact == base or len(compact) < 3 or not base.startswith(compact):
            continue
        collision_names = "; ".join(candidate.base_group_key for candidate in candidates[:4])
        note = "short real family is prefix of longer expected family"
        out.append(_mutation(compact, "truncation_collision_prefix", note, collision_names, "DANGEROUS", "EXTREME"))
    return out


RecordTransform = Callable[[CatalogRecord], list[Mutation]]
IndexTransform = Callable[[CatalogRecord, CatalogIndex], list[Mutation]]


RECORD_TRANSFORMS: dict[str, RecordTransform] = {
    "all_position_deletion_full_catalog": all_position_deletions,
    "keyboard_adjacent_expanded_catalog": keyboard_adjacent_substitutions,
    "vowel_substitution_full_catalog": vowel_substitutions,
    "all_position_transposition_full_catalog": all_position_transpositions,
    "phonetic_substitution_full_catalog": phonetic_substitutions,
    "initial_sound_confusion_full_catalog": initial_sound_confusions,
    "single_vowel_deletion_full_catalog": single_vowel_deletions,
    "consonant_skeleton_expanded_catalog": consonant_skeleton,
    "form_word_noise_catalog": form_word_noise,
    "mobile_keypad_confusion_catalog": mobile_keypad_confusions,
    "separator_removal_full_catalog": separator_removals,
    "token_order_transposition_catalog": token_order_transpositions,
    "ingredient_name_query_catalog": ingredient_name_queries,
    "ocr_digit_letter_full_catalog": ocr_digit_letter_substitutions,
    "manufacturer_noise_catalog": manufacturer_noise,
    "space_insertion_inside_brand_catalog": space_insertions_inside_brand,
    "decimal_slash_strength_noise_catalog": decimal_slash_strength_noise,
    "visual_ligature_full_catalog": visual_ligature_confusions,
    "therapeutic_class_noise_catalog": therapeutic_class_noise,
    "route_word_noise_catalog": route_word_noise,
    "status_marker_noise_catalog": status_marker_noise,
    "prefix_suffix_extra_noise_catalog": prefix_suffix_extra_noise,
    "keyboard_shift_whole_word_catalog": keyboard_shift_whole_word,
    "symbol_synonym_catalog": symbol_synonyms,
    "qualifier_synonym_noise_catalog": qualifier_synonym_noise,
    "strength_unit_noise_catalog": strength_unit_noise,
    "brand_ingredient_mixed_query_catalog": brand_ingredient_mixed_queries,
    "parenthetical_noise_catalog": parenthetical_noise,
    "duplicate_syllable_catalog": duplicate_syllables,
    "digraph_soundalike_catalog": digraph_soundalikes,
    "abbreviation_expansion_catalog": abbreviation_expansions,
    "token_drop_expanded_catalog": token_drops,
}

INDEX_TRANSFORMS: dict[str, IndexTransform] = {
    "partial_prefix_ambiguity_catalog": partial_prefix_ambiguities,
    "truncation_collision_expanded_catalog": truncation_collisions,
    "suffix_family_confusion_expanded_catalog": suffix_family_confusions,
}


def _mutation(
    value: object,
    error_type: str,
    notes: str,
    collision_hint: str = "",
    danger_override: str | None = None,
    difficulty_override: str | None = None,
) -> Mutation:
    input_value = lower_query(value)
    return Mutation(
        input_value=input_value,
        error_type=error_type,
        notes=notes,
        collision_hint=collision_hint,
        danger_override=danger_override,  # type: ignore[arg-type]
        difficulty_override=difficulty_override,  # type: ignore[arg-type]
    )


def _single_char_substitutions(
    base: str,
    replacements: dict[str, list[str]],
    error_prefix: str,
    note_prefix: str,
) -> list[Mutation]:
    out: list[Mutation] = []
    for pos, char in enumerate(base):
        for replacement in replacements.get(char, []):
            mutated = base[:pos] + replacement + base[pos + 1 :]
            note = f"{note_prefix} {char}->{replacement} at compact position {pos}"
            out.append(_mutation(mutated, f"{error_prefix}_{char}_to_{replacement}_pos_{pos}", note))
    return out


def _substring_replacements(base: str, pairs: tuple[tuple[str, str], ...]) -> list[Mutation]:
    out: list[Mutation] = []
    for source, replacement in pairs:
        if source not in base:
            continue
        mutated = base.replace(source, replacement, 1)
        note = f"{source}->{replacement} in compact commercial name"
        out.append(_mutation(mutated, f"{source.lower()}_to_{replacement.lower()}", note))
    return out


def _qwerty_neighbors() -> dict[str, list[str]]:
    horizontal: dict[str, set[str]] = {}
    for row in QWERTY_ROWS:
        for index, char in enumerate(row):
            values = horizontal.setdefault(char, set())
            if index > 0:
                values.add(row[index - 1])
            if index < len(row) - 1:
                values.add(row[index + 1])
    vertical = {"A": "QWZ", "S": "QWEXZ", "D": "WERFCX", "F": "ERTGVC", "G": "RTYHBV", "H": "TYUJNB"}
    for key, values in vertical.items():
        horizontal.setdefault(key, set()).update(values)
    return {key: sorted(values - {key}) for key, values in horizontal.items()}


def _sound_neighbors() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for group in SOUND_GROUPS:
        for char in group:
            out[char] = [candidate for candidate in group if candidate != char]
    return out


def _keyboard_shift_maps() -> tuple[dict[str, str], dict[str, str]]:
    left: dict[str, str] = {}
    right: dict[str, str] = {}
    for row in QWERTY_ROWS:
        for index, char in enumerate(row):
            if index > 0:
                left[char] = row[index - 1]
            if index < len(row) - 1:
                right[char] = row[index + 1]
    return left, right


def _degrade_prefix(prefix: str) -> str:
    if not prefix:
        return prefix
    first = prefix[0]
    sound = _sound_neighbors().get(first)
    if sound:
        return sound[0] + prefix[1:]
    if first in VOWELS:
        return "E" + prefix[1:] if first != "E" else "A" + prefix[1:]
    return "A" + prefix[1:]


def _shared_suffixes_for(record: CatalogRecord, index: CatalogIndex) -> list[str]:
    base = record.base_group_compact
    suffixes: list[str] = []
    for suffix in SUFFIX_FAMILIES:
        if base.endswith(suffix):
            suffixes.append(suffix)
    for length in range(4, 9):
        if len(base) <= length:
            continue
        suffix = base[-length:]
        if len(index.suffix_to_bases.get(suffix, [])) >= MIN_SHARED_SUFFIX_FAMILY_SIZE:
            suffixes.append(suffix)
    return list(dict.fromkeys(suffixes))
