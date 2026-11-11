"""Rubric: profiles, bands, caps R1-R6 (pure, downward-only)."""
from __future__ import annotations

MAX_TOTAL = 5.0

PROFILES = {
    "P1": {"answer": 1.0, "legal_basis": 1.5, "application": 1.5, "conclusion": 1.0},
    "P3": {"answer": 1.5, "legal_basis": 1.5, "application": 1.0, "conclusion": 1.0},
    "P4": {"answer": 1.0, "legal_basis": 1.0, "application": 2.0, "conclusion": 1.0},
    "P5": {"answer": 1.0, "legal_basis": 1.5, "application": 1.5, "conclusion": 1.0},
}

ORDER = ["answer", "legal_basis", "application", "conclusion"]

# Band whitelist per component (quarter steps up to the max seen across profiles).
BANDS = {
    "answer": [0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5],
    "legal_basis": [0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5],
    "application": [0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0],
    "conclusion": [0, 0.25, 0.5, 0.75, 1.0],
}

CAP_IDS = ["R1", "R2", "R3", "R4", "R5", "R6"]


def _copy_scores(scores):
    return {k: float(scores[k]) for k in ORDER}


def cap_r1(scores, flags):
    """R1 wrong polarity: flagged wrong_polarity -> Ap <= 0.75, C <= 0.50."""
    s = _copy_scores(scores)
    if "wrong_polarity" in (flags or []):
        s["application"] = min(s["application"], 0.75)
        s["conclusion"] = min(s["conclusion"], 0.50)
        return s, True
    return s, False


def cap_r2(scores, flags):
    """R2 rule-dump: L > 0 and Ap == 0 -> flag no_application, no score change."""
    s = _copy_scores(scores)
    if s["legal_basis"] > 0 and s["application"] == 0:
        return s, True
    return s, False


def cap_r3(scores, flags):
    """R3 superseded authority: flagged stale_authority -> L <= 0.50."""
    s = _copy_scores(scores)
    if "stale_authority" in (flags or []):
        s["legal_basis"] = min(s["legal_basis"], 0.50)
        return s, True
    return s, False


def cap_r4(scores, flags):
    """R4 bare assertion: L == 0 and Ap > 0 -> Ap <= 0.75."""
    s = _copy_scores(scores)
    if s["legal_basis"] == 0 and s["application"] > 0:
        s["application"] = min(s["application"], 0.75)
        return s, True
    return s, False


def cap_r5(scores, flags):
    """R5 internal contradiction: flagged inconsistent -> C = 0 (aggregate caps sum at 4.00)."""
    s = _copy_scores(scores)
    if "inconsistent" in (flags or []):
        s["conclusion"] = 0.0
        return s, True
    return s, False


def cap_r6(scores, flags):
    """R6 unverified citation: flagged unverified_citation -> L <= 0.50."""
    s = _copy_scores(scores)
    if "unverified_citation" in (flags or []):
        s["legal_basis"] = min(s["legal_basis"], 0.50)
        return s, True
    return s, False


CAPS = {
    "R1": cap_r1,
    "R2": cap_r2,
    "R3": cap_r3,
    "R4": cap_r4,
    "R5": cap_r5,
    "R6": cap_r6,
}

R2_FLAG = "no_application"
R4_FLAG = "no_legal_basis"
R5_TOTAL_CAP = 4.00


def apply_caps(scores, flags):
    """Apply R1->R6 in order. Pure: never mutates inputs, only lowers scores.

    Returns (scores_out, caps_applied, flags_out, total_cap).
    """
    s = _copy_scores(scores)
    f = list(flags or [])
    applied = []
    for cid in CAP_IDS:
        fn = CAPS[cid]
        before = dict(s)
        s, hit = fn(s, f)
        # downward-only guard
        for k in ORDER:
            assert s[k] <= before[k] + 1e-9, f"{cid} raised {k}"
        if hit:
            applied.append(cid)
    if "R2" in applied and R2_FLAG not in f:
        f = f + [R2_FLAG]
    if "R4" in applied and R4_FLAG not in f:
        f = f + [R4_FLAG]
    if "R5" in applied and "inconsistent" not in f:
        f = f + ["inconsistent"]
    total_cap = R5_TOTAL_CAP if "R5" in applied else None
    return s, applied, f, total_cap
