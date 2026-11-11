"""Stateless AI grader (MVP). No database, no history, no persistence.

POST /grade -> sync model call, one repair retry, validate -> caps -> return.
Attempt text lives only in the request/response. Nothing is written anywhere.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from . import grade as grader
    from . import rubric
    from .rubric import PROFILES, apply_caps
except ImportError:  # run as script inside grader/
    import grade as grader
    import rubric
    from rubric import PROFILES, apply_caps

GO_DEFAULT_BASE_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
FALLBACK_BASE_URL = "https://api.deepseek.com"

BASE_URL = os.environ.get("GRADER_BASE_URL") or GO_DEFAULT_BASE_URL
FALLBACK_URL = os.environ.get("GRADER_FALLBACK_BASE_URL") or FALLBACK_BASE_URL
API_KEY = (
    os.environ.get("GRADER_API_KEY")
    or os.environ.get("OPENCODE_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or ""
)
MODEL = os.environ.get("GRADER_MODEL") or ""
CUTOFF = os.environ.get("GRADER_CUTOFF") or grader.CUTOFF_DEFAULT

USER_AGENT = "comm2-reviewer/0.1"

# Read-only lookup of suggested answers by item id (no writes, ever).
DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "data" / "exams"
ID_TO_ANSWER: dict[str, str] = {}
try:
    _all = json.loads((DATA_DIR / "all.json").read_text(encoding="utf-8"))
    for _it in _all:
        if isinstance(_it, dict) and _it.get("id") and _it.get("answer"):
            ID_TO_ANSWER[str(_it["id"])] = str(_it["answer"])
except Exception:
    ID_TO_ANSWER = {}

app = FastAPI(title="comm2-grader", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


class GradeRequest(BaseModel):
    id: str = Field(min_length=1)
    stem: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    profile: str = "P1"
    authorities: object = None


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _call_model(messages, session_id):
    """Sync OpenAI-compatible call. Tries primary base URL, then one fallback host."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"openai package not installed: {exc}")
    if not API_KEY:
        raise HTTPException(status_code=503, detail="grader API key not configured (GRADER_API_KEY)")
    if not MODEL:
        raise HTTPException(status_code=503, detail="grader model not configured (GRADER_MODEL)")
    headers = {"User-Agent": USER_AGENT, "x-opencode-session": session_id}
    last_err: Exception | None = None
    for base_url in ([BASE_URL] if BASE_URL == FALLBACK_URL else [BASE_URL, FALLBACK_URL]):
        try:
            client = OpenAI(api_key=API_KEY, base_url=base_url, timeout=60.0, max_retries=0)
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=1600,
                extra_headers=headers,
                extra_body={"thinking": {"type": "disabled"}},
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - fallback then 502
            last_err = exc
    raise HTTPException(status_code=502, detail=f"model call failed: {last_err}")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/grade")
def grade(req: GradeRequest):
    if req.profile not in PROFILES:
        raise HTTPException(status_code=422, detail=f"unknown profile {req.profile!r}")
    attempt = req.answer
    authorities = req.authorities
    if isinstance(authorities, str):
        auth_list = [authorities] if authorities.strip() else []
    elif isinstance(authorities, list):
        auth_list = [str(a) for a in authorities]
    elif authorities is None:
        auth_list = []
    else:
        auth_list = [str(authorities)]
    suggested = ID_TO_ANSWER.get(req.id, "")
    messages = grader.buildMessages(req.stem, suggested, auth_list, attempt, req.profile, CUTOFF)

    raw = _call_model(messages, req.id)
    payload = None
    components = None
    last_error = ""
    for attempt_no in range(2):
        try:
            payload = json.loads(raw)
            components = grader.validate(attempt, payload, req.profile)
            break
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            last_error = str(exc)
            if attempt_no == 1:
                raise HTTPException(status_code=422, detail=f"validator rejected model output: {exc}")
            messages = messages + [
                {"role": "assistant", "content": (raw or "")[:2000]},
                {"role": "user", "content": f"That failed validation ({exc}). Return corrected JSON only."},
            ]
            raw = _call_model(messages, req.id)

    assert payload is not None and components is not None
    scores = {c["id"]: c["awarded"] for c in components}
    flags = list(payload.get("flags") or [])
    capped, caps_applied, flags_out, total_cap = apply_caps(scores, flags)
    for c in components:
        c["awarded"] = round(float(capped[c["id"]]), 2)
        c["band"] = f"{c['awarded']:.2f}"
    total, pct = grader.aggregate_scored(components, req.profile, total_cap)
    confidence = payload.get("confidence") or "low"
    if confidence not in grader.CONFIDENCES:
        confidence = "low"
    suggestions = payload.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = []
    suggestions = [str(s) for s in suggestions if str(s).strip()]
    if not suggestions:
        suggestions = [c["fix"] for c in components if c.get("fix")]
    # Insertion order: components first, aggregate last.
    return {
        "components": components,
        "flags": flags_out,
        "confidence": confidence,
        "suggestions": suggestions,
        "model": MODEL,
        "model_date": _today(),
        "caps_applied": caps_applied,
        "total": total,
        "pct": pct,
    }
