"""Grader unit tests (plain asserts, no pytest needed): python3 test_grader.py"""
from __future__ import annotations

import json

from rubric import PROFILES, ORDER, BANDS, CAP_IDS, CAPS, apply_caps, MAX_TOTAL
import grade as G


def test_profiles_sum():
    for name, p in PROFILES.items():
        assert abs(sum(p.values()) - 5.0) < 1e-9, f"{name} sums to {sum(p.values())}"
        assert set(p) == set(ORDER), name
    assert abs(sum(PROFILES["P1"].values()) - 5.0) < 1e-9
    assert PROFILES["P1"] == {"answer": 1.0, "legal_basis": 1.5, "application": 1.5, "conclusion": 1.0}
    print(f"profiles sum OK ({len(PROFILES)} profiles, all 5.0)")


def test_caps_reachable():
    full = {"answer": 1.0, "legal_basis": 1.5, "application": 1.5, "conclusion": 1.0}
    # R1: wrong polarity
    s, ap, _, _ = apply_caps(dict(full), ["wrong_polarity"])
    assert "R1" in ap and s["application"] <= 0.75 and s["conclusion"] <= 0.50
    # R2: rule dump
    s, ap, f, _ = apply_caps({"answer": 0.5, "legal_basis": 1.0, "application": 0.0, "conclusion": 0.5}, [])
    assert "R2" in ap and "no_application" in f
    # R3: stale authority
    s, ap, _, _ = apply_caps(dict(full), ["stale_authority"])
    assert "R3" in ap and s["legal_basis"] <= 0.50
    # R4: bare assertion
    s, ap, f, _ = apply_caps({"answer": 0.5, "legal_basis": 0.0, "application": 1.5, "conclusion": 0.5}, [])
    assert "R4" in ap and s["application"] <= 0.75 and "no_legal_basis" in f
    # R5: contradiction
    s, ap, _, cap = apply_caps(dict(full), ["inconsistent"])
    assert "R5" in ap and s["conclusion"] == 0.0 and cap == 4.00
    # R6: unverified citation
    s, ap, _, _ = apply_caps(dict(full), ["unverified_citation"])
    assert "R6" in ap and s["legal_basis"] <= 0.50
    # downward-only on random-ish input
    s, _, _, _ = apply_caps({"answer": 0.75, "legal_basis": 1.25, "application": 1.0, "conclusion": 0.75},
                            ["wrong_polarity", "stale_authority", "unverified_citation", "inconsistent"])
    assert s["application"] <= 1.0 and s["legal_basis"] <= 1.25 and s["conclusion"] == 0.0
    assert set(CAP_IDS) == set(CAPS)
    print("caps R1-R6 reachable OK (downward-only)")


def _sample_attempt():
    return ("Lito is not correct. Under the Labor Code, an employee may only be dismissed for just or "
            "authorized cause. Here, Lito was caught sleeping at his post, which is gross negligence, "
            "so the employer had a valid reason to dismiss him. Therefore, the dismissal is valid.")


def _sample_payload():
    a = _sample_attempt()
    return {
        "components": [
            {"id": "answer", "awarded": 1.0, "band": "1.00", "verdict": "Direct.",
             "evidence": [{"quote": "Lito is not correct.", "role": "answer"}], "missing": [], "fix": None},
            {"id": "legal_basis", "awarded": 0.5, "band": "0.50", "verdict": "Code named, no article.",
             "evidence": [{"quote": "Under the Labor Code", "role": "rule"}],
             "missing": ["Art. 297"], "fix": "Name the article, not just the code."},
            {"id": "application", "awarded": 0.5, "band": "0.50", "verdict": "Conclusory.",
             "evidence": [{"quote": "Here, Lito was caught sleeping at his post", "role": "application"}],
             "missing": ["two-notice rule"], "fix": "Use the procedural defect the facts handed you."},
            {"id": "conclusion", "awarded": 0.5, "band": "0.50", "verdict": "Closes one issue.",
             "evidence": [{"quote": "the dismissal is valid.", "role": "conclusion"}],
             "missing": ["nominal damages"], "fix": "Answer both issues."},
        ],
        "flags": [],
        "confidence": "high",
        "suggestions": ["Name the article.", "Use the procedural defect."],
    }


def test_validator():
    a = _sample_attempt()
    comps = G.validate(a, _sample_payload(), "P1")
    assert [c["id"] for c in comps] == ORDER
    assert all("start" in e and "end" in e for c in comps for e in c["evidence"])
    # non-zero requires evidence
    bad = json.loads(json.dumps(_sample_payload()))
    bad["components"][0]["evidence"] = []
    try:
        G.validate(a, bad, "P1")
    except ValueError as e:
        assert "no evidence" in str(e)
    else:
        raise AssertionError("accepted scoreless evidence")
    # fabricated quote rejected
    bad = json.loads(json.dumps(_sample_payload()))
    bad["components"][0]["evidence"][0]["quote"] = "Lito is correct."
    try:
        G.validate(a, bad, "P1")
    except ValueError as e:
        assert "quote not found" in str(e)
    else:
        raise AssertionError("accepted fabricated quote")
    # wrong order rejected
    bad = json.loads(json.dumps(_sample_payload()))
    bad["components"] = bad["components"][::-1]
    try:
        G.validate(a, bad, "P1")
    except ValueError as e:
        assert "ids/order" in str(e)
    else:
        raise AssertionError("accepted wrong order")
    # over-max rejected
    bad = json.loads(json.dumps(_sample_payload()))
    bad["components"][0]["awarded"] = 5.0
    bad["components"][0]["band"] = "5.00"
    try:
        G.validate(a, bad, "P1")
    except ValueError as e:
        assert "outside" in str(e)
    else:
        raise AssertionError("accepted over-max")
    # model aggregate rejected
    bad = json.loads(json.dumps(_sample_payload()))
    bad["total"] = 2.5
    try:
        G.validate(a, bad, "P1")
    except ValueError as e:
        assert "must not produce" in str(e)
    else:
        raise AssertionError("accepted model total")
    print("validator OK (evidence/offsets/order/max/no-model-aggregate)")


def test_prompt_contract():
    msgs = G.buildMessages("Q?", "suggested", ["Auth 1"], "my attempt", "P1")
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    blob = (msgs[0]["content"] + "\n" + msgs[1]["content"]).lower()
    assert "total" not in blob, "prompt must not contain the word 'total'"
    u = msgs[1]["content"]
    assert u.index("QUESTION") < u.index("SUGGESTED ANSWER")
    assert u.index("SUGGESTED ANSWER") < u.index("AUTHORITIES")
    assert u.index("AUTHORITIES") < u.index("<<<EXAMINEE_ANSWER>>>")
    print("prompt contract OK (no 'total', examinee answer last)")


def test_sample_grade_order():
    a = _sample_attempt()
    out = G.grade_offline("fixture-1", a, _sample_payload(), "P1")
    assert out["total"] == 2.5 and out["pct"] == 50.0
    keys = list(out.keys())
    assert keys.index("components") < keys.index("total"), keys
    assert len(out["components"]) == 4
    assert out["components"][0]["evidence"][0]["start"] == 0
    print(f"sample grade OK: total={out['total']} pct={out['pct']} order={keys}")


if __name__ == "__main__":
    test_profiles_sum()
    test_caps_reachable()
    test_validator()
    test_prompt_contract()
    test_sample_grade_order()
    print("ALL GRADER TESTS OK")
