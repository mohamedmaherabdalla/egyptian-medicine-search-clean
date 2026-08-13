#!/usr/bin/env python3
"""Black-box acceptance checks for the deployed Algorithm 6 API hardening."""

from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def family_names(response: dict[str, Any]) -> list[str]:
    return [str(item.get("base_group_key") or item.get("name") or "") for item in response["results"]]


def product_names(response: dict[str, Any]) -> list[str]:
    return [str(item.get("commercial_name_en") or item.get("commercial_name") or "") for item in response["results"]]


def assert_confirmation(response: dict[str, Any]) -> None:
    assert all(item.get("confirmation_required") is True for item in response["results"]), response
    assert all(item.get("needs_clarification") is True for item in response["results"]), response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8013")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    runtime = get_json(f"{base}/api/runtime")
    assert runtime["ready"] is True
    assert runtime["algorithm"] == "algorithm_6"
    assert runtime["evaluation_version"] == "algorithm_6_consensus_v1"
    assert runtime["medicine_count"] == 25_066
    assert runtime["family_count"] == 17_476
    assert set(runtime["capabilities"]) >= {
        "ordinary_search",
        "visual_gaps",
        "product_context_reranking",
    }
    assert get_json(f"{base}/health") == {"status": "ok", "algorithm": "algorithm_6"}

    def search(query: str, context: str = "", limit: int = 20) -> dict[str, Any]:
        output = post_json(
            f"{base}/api/search",
            {"query": query, "product_context": context, "limit": limit},
        )
        assert output["algorithm"] == "algorithm_6", output
        assert_confirmation(output)
        return output

    javaki = search("javaki", "5mg")
    assert family_names(javaki)[0] == "JAKAVI", family_names(javaki)
    assert product_names(javaki)[0] == "JAKAVI 5 MG 56 TABS."
    assert javaki["context_family_reranked"] is True
    assert javaki["results"][0]["name_match_rank"] == 2

    brufen_bare = search("brufen", "600")
    assert set(product_names(brufen_bare)) == {
        "BRUFEN 600 MG 10 EFF. GR. IN SACHETS",
        "BRUFEN 600 MG 20 EFF. GR. IN SACHETS",
        "BRUFEN 600 MG 30 TABS.",
    }
    assert all(item["context_tie_count"] == 3 for item in brufen_bare["results"])

    brufen_tablet = search("brufen", "600 tab")
    assert product_names(brufen_tablet) == ["BRUFEN 600 MG 30 TABS."]
    assert "unitless_strength_match" in brufen_tablet["results"][0]["matched_context"]

    brufen_comma_tablet = search("brufen", "600, tab")
    assert product_names(brufen_comma_tablet) == ["BRUFEN 600 MG 30 TABS."]

    brufen_pack = search("brufen", "30 tab")
    assert set(product_names(brufen_pack)) == {
        "BRUFEN 200 MG 30 TABS.",
        "BRUFEN 400 MG 30 TABS.",
        "BRUFEN 600 MG 30 TABS.",
    }

    short = search("x", "500 tab")
    assert short["decision_type"] == "context_assisted_prefix_candidates"
    assert short["status"] == "ambiguous"
    assert short["candidate_count"] == 4
    assert set(family_names(short)) == {"XELODA", "XEREXOMAIR", "XEROVIRINC", "XITHRONE"}

    short_miss = search("x", "600 tab")
    assert short_miss["decision_type"] == "context_assisted_prefix_no_match"
    assert not short_miss["results"]

    xanax = search("xanax", "500 mg tab")
    assert xanax["decision_type"] == "product_context_no_compatible_product"
    assert family_names(xanax)[0] == "XANAX"
    assert product_names(xanax)[0] == "XANAX"
    assert xanax["results"][0]["strength"] == "-"
    assert xanax["results"][0]["context_match_status"] == "no_compatible_product"

    vial = search("augmentin", "1.2 g vial")
    assert product_names(vial)[0] == "AUGMENTIN 1.2G VIAL FOR I.V. INJ./INF."

    denominator_conflict = search("augmentin", "156 mg/10 ml suspension")
    assert denominator_conflict["decision_type"] == "product_context_no_compatible_product"

    leil_presentation = search("leal", "100 g cream")
    assert family_names(leil_presentation)[0] == "LEIL"
    assert leil_presentation["context_family_reranked"] is True
    assert "qualified_presentation_exact" in leil_presentation["results"][0]["matched_context"]

    argotex_presentation = search("argatex", "50 g cream")
    assert family_names(argotex_presentation)[0] == "ARGOTEX"
    assert argotex_presentation["context_family_reranked"] is True
    assert "qualified_presentation_exact" in argotex_presentation["results"][0]["matched_context"]

    weak_presentation = search("argatex", "50")
    assert family_names(weak_presentation)[0] == "ARGITEX"
    assert weak_presentation["context_family_reranked"] is False

    numbered_brand = search("D3")
    assert family_names(numbered_brand)[0] == "D3"

    numeric_word_brand = search("3 FLY")
    assert family_names(numeric_word_brand)[0] == "FLY"
    assert numeric_word_brand["decision_type"] != "product_context_no_compatible_product"

    numeric_only_brand = search("1 2 3")
    assert numeric_only_brand["decision_type"] == "numeric_commercial_alias_matches"
    assert numeric_only_brand["status"] == "ambiguous"
    assert numeric_only_brand["candidate_count"] == 2
    assert set(family_names(numeric_only_brand)) == {
        "ONE TWO THREE",
        "ONE TWO THREE EXTRA",
    }

    numeric_only_brand_with_details = search("1 2 3 20 tab")
    assert (
        numeric_only_brand_with_details["decision_type"]
        == "numeric_commercial_alias_product_context_selection"
    )
    assert set(family_names(numeric_only_brand_with_details)) == {
        "ONE TWO THREE",
        "ONE TWO THREE EXTRA",
    }
    assert set(product_names(numeric_only_brand_with_details)) == {
        "1 2 3 (ONE TWO THREE) 20 F.C.TABS.",
        "1 2 3 (ONE TWO THREE) EXTRA 20 F.C.TABS.",
    }

    numeric_brand_with_details = search("3 FLY 600 tab")
    assert family_names(numeric_brand_with_details)[0] == "FLY"
    assert product_names(numeric_brand_with_details)[0] == "3 FLY 600 MG 20 TABS."
    assert "unitless_strength_match" in numeric_brand_with_details["results"][0]["matched_context"]

    longer_numbered_brand = search("1 2 3 ONE TWO THREE 20 tab")
    assert family_names(longer_numbered_brand) == ["ONE TWO THREE"]
    assert product_names(longer_numbered_brand) == [
        "1 2 3 (ONE TWO THREE) 20 F.C.TABS."
    ]

    unknown_numeric_suffix = search("1 2 3 junk 20 tab")
    assert not str(unknown_numeric_suffix["decision_type"]).startswith(
        "numeric_commercial_alias"
    )

    for query, expected in (
        ("OMGPRAZOLG", "OMEPRAZOLE SPLENDID PHARMA"),
        ("OMIPRAZOLI", "OMEPRAZOLE SPLENDID PHARMA"),
        ("ACLCLOH", "ADDO H"),
        ("DKDINE", "ALKALINE"),
    ):
        response = search(query)
        assert expected in family_names(response), (query, family_names(response))

    for query, expected in (
        ("...CLICY...", "DICYNONE"),
        ("...BACTID...", "BACTICLOR"),
        ("...ALEPI...", "DEPIDERM"),
    ):
        response = search(query)
        assert response["decision_type"] == "visual_gap_matches"
        assert expected not in family_names(response), (query, family_names(response))

    for query, expected in (
        ("CLICY...", "DICYNONE"),
        ("BACTID...", "BACTICLOR"),
        ("ALEPI...", "DEPIDERM"),
    ):
        response = search(query)
        assert response["decision_type"] == "visual_gap_matches"
        assert expected in family_names(response), (query, family_names(response))

    strict_edge = search("...PANADOL")
    assert "PANADOL" not in family_names(strict_edge), family_names(strict_edge)

    visual_product = search("BRU...", "600 mg tab")
    assert visual_product["name_decision_type"] == "visual_gap_matches"
    assert product_names(visual_product) == ["BRUFEN 600 MG 30 TABS."]

    short_visual = search("BR...", "10 mg tab")
    assert short_visual["name_decision_type"] == "visual_gap_matches"
    assert short_visual["decision_type"] != "context_assisted_prefix_candidates"
    assert "BRINTELLIX" not in family_names(short_visual)

    numeric_visual = search("3__FLY")
    assert numeric_visual["decision_type"] == "visual_gap_matches"
    assert not str(numeric_visual["decision_type"]).startswith(
        "numeric_commercial_alias"
    )

    visual_number = search("VIT__3")
    assert visual_number["decision_type"] == "visual_gap_matches"
    assert "VIT D3" in family_names(visual_number)
    assert "product_context" not in visual_number

    duplicate_product_names = search("citicoline", "500 mg cap")
    assert len(duplicate_product_names["results"]) == 2
    assert {item["selected_product_id"] for item in duplicate_product_names["results"]} == {
        "D2-04517",
        "D2-04518",
    }
    assert {
        (item["price_egp"], item["manufacturer"])
        for item in duplicate_product_names["results"]
    } == {
        (22.0, "ORGANIX"),
        (298.0, "LIFE SAVER -INTERNATIONAL"),
    }

    attached_percent = search("econazole", "1% spray")
    assert attached_percent["decision_type"] == "product_context_selection"
    assert attached_percent["results"][0]["selected_product_id"] == "D2-06821"
    assert "strength_exact" in attached_percent["results"][0]["matched_context"]

    print("Algorithm 6 API hardening acceptance passed (38 endpoint scenarios).")


if __name__ == "__main__":
    main()
