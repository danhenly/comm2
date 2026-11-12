"""Stateless AI grader (MVP). No database, no history, no persistence.

POST /grade -> sync model call, one repair retry, validate -> caps -> return.
Attempt text lives only in the request/response. Nothing is written anywhere.
"""
from __future__ import annotations

import json
import os
import traceback
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

GO_DEFAULT_BASE_URL = "https://opencode.ai/inference/go/openai/v1"
FALLBACK_BASE_URL = "https://api.deepseek.com"

BASE_URL = os.environ.get("GRADER_BASE_URL") or GO_DEFAULT_BASE_URL
FALLBACK_URL = os.environ.get("GRADER_FALLBACK_BASE_URL") or FALLBACK_BASE_URL
API_KEY = (
    os.environ.get("GRADER_API_KEY")
    or os.environ.get("OPENCODE_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or ""
)
# Exact inference id: deepseek-v4.1-flash (verified against the live catalog;
# do NOT switch to deepseek-v4-flash — Go inference 400s "Model is unavailable"
# for it). Earlier 400/404 confusion was root-caused to key scope, not the id:
# Go completions 401s "api key invalid" on workspace-scoped/log-scraped keys
# even when /models returns 200. Use a console-minted personal key. If Go
# still 401s, switch GRADER_BASE_URL to https://api.deepseek.com with a
# DeepSeek direct key (~P0.05/grade).
# Env overrides; never empty.
MODEL = os.environ.get("GRADER_MODEL") or "deepseek-v4.1-flash"
CUTOFF = os.environ.get("GRADER_CUTOFF") or grader.CUTOFF_DEFAULT

USER_AGENT = "comm2-reviewer/0.1"


def _host(url: str) -> str:
    try:
        from urllib.parse import urlsplit

        return urlsplit(url).hostname or url
    except Exception:
        return url


# NOTE on env staleness: BASE_URL/API_KEY/MODEL/CUTOFF are read ONCE at
# import. uvicorn runs WITHOUT --reload here (see Dockerfile CMD), so each
# container process imports fresh — no in-process caching across deploys.
# Stale values can only mean Coolify is still running an OLD container/image
# (redeploy never triggered). The startup line below proves which values are
# live: compare its timestamp against the deploy. Smoking gun for a stale
# prod: a 502 whose detail LACKS the "provider {status}:" prefix (that prefix
# only exists in images >= the provider-body commit).
print(
    f"[grader] config loaded_at={datetime.now(timezone.utc).isoformat()} "
    f"pid={os.getpid()} model={MODEL} base={_host(BASE_URL)} "
    f"fallback={_host(FALLBACK_URL)} key=...{(API_KEY[-4:] if API_KEY else 'NONE')} "
    f"fallback_armed={BASE_URL != FALLBACK_URL} cutoff={CUTOFF}",
    flush=True,
)

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


def _redact(text: str) -> str:
    """Strip any key material before it leaves the server in an error body."""
    if API_KEY and API_KEY in text:
        text = text.replace(API_KEY, "[redacted]")
    return text[:2000]


def _describe_error(exc: Exception, model_sent: str, base_url: str) -> dict:
    """Full provider error detail for logs: status, message, request id,
    model actually sent, and host actually hit. Key material redacted."""
    status = getattr(exc, "status_code", None)
    body: object = getattr(exc, "body", None)
    message = getattr(exc, "message", None) or str(exc)
    if isinstance(body, dict):
        err = body.get("error", body) if isinstance(body, dict) else body
        if isinstance(err, dict):
            message = err.get("message", message)
    request_id = getattr(exc, "request_id", None)
    if request_id is None:
        try:
            resp_obj = getattr(exc, "response", None)
            headers = getattr(resp_obj, "headers", {}) or {}
            request_id = headers.get("x-request-id") or headers.get("request-id")
        except Exception:
            request_id = None
    try:
        raw_body = json.dumps(body) if isinstance(body, dict) else str(body or message)
    except Exception:
        raw_body = str(message)
    return {
        "status": status,
        "message": _redact(str(message)),
        "request_id": request_id,
        "model_sent": model_sent,
        "host": _host(base_url),
        "body": _redact(raw_body)[:1000],
    }


def _call_model(messages, session_id):
    """Sync OpenAI-compatible call. Tries primary base URL, then one fallback host."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"openai package not installed: {exc}")
    if not API_KEY:
        raise HTTPException(status_code=503, detail="grader API key not configured (GRADER_API_KEY)")
    headers = {"User-Agent": USER_AGENT, "x-opencode-session": session_id}
    targets = [BASE_URL] if BASE_URL == FALLBACK_URL else [BASE_URL, FALLBACK_URL]
    last_err: Exception | None = None
    for n, base_url in enumerate(targets, start=1):
        print(f"[grader] attempt {n}/{len(targets)} model={MODEL} host={_host(base_url)}", flush=True)
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
        except Exception as exc:  # noqa: BLE001 - 4xx surfaces provider body, else fallback then 502
            info = _describe_error(exc, MODEL, base_url)
            print(f"[grader] attempt {n}/{len(targets)} FAILED {json.dumps(info)}", flush=True)
            traceback.print_exc()
            status = info["status"]
            if status is not None and 400 <= status < 500:
                print(f"[grader] not falling back (client {status} would repeat on fallback host)", flush=True)
                raise HTTPException(status_code=502, detail=f"provider {status}: {info['message']} (request_id={info['request_id']})")
            print(f"[grader] falling back (transport/server error)", flush=True)
            last_err = exc
    raise HTTPException(status_code=502, detail=f"model call failed: {_redact(str(last_err))}")


def _models_url(base_url: str) -> str:
    # Accept both shapes: ".../v1" and legacy ".../v1/chat/completions".
    root = base_url
    if root.rstrip("/").endswith("/chat/completions"):
        root = root.rsplit("/chat/completions", 1)[0]
    return root.rstrip("/") + "/models"


@app.get("/debug-net")
def debug_net():
    """Connectivity diagnostics: config presence + catalog reachability.

    Sends the models request WITH Authorization + User-Agent (key never
    leaves the server; only booleans/counts are returned). A 401 from
    /models means bad key scope — reported as auth_ok:false, NOT as
    "unreachable" or "not in catalog" (model_in_catalog:null in that case).
    """
    import urllib.error
    import urllib.request

    models_url = _models_url(BASE_URL)
    base = {
        "base_url": BASE_URL,
        "models_url": models_url,
        "model": MODEL,
        "key_configured": bool(API_KEY),
        "cutoff": CUTOFF,
    }
    if not API_KEY:
        return {**base, "ok": False, "auth_ok": False,
                "models_reachable": None, "model_in_catalog": None,
                "models_error": "no key configured"}
    try:
        req = urllib.request.Request(
            models_url,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "User-Agent": USER_AGENT,
                "x-opencode-session": "debug-net",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            catalog = json.loads(r.read().decode("utf-8"))
        ids = [m.get("id") for m in catalog.get("data", [])] if isinstance(catalog, dict) else []
        return {
            **base, "ok": True, "auth_ok": True,
            "models_reachable": True,
            "catalog_count": len(ids),
            "model_in_catalog": MODEL in ids,
        }
    except urllib.error.HTTPError as exc:
        traceback.print_exc()
        if exc.code == 401:
            return {
                **base, "ok": False, "auth_ok": False,
                "models_reachable": True,
                "model_in_catalog": None,
                "models_error": f"401: key rejected by {models_url} (wrong scope, not a connectivity issue)",
            }
        return {
            **base, "ok": False, "auth_ok": None,
            "models_reachable": True,
            "model_in_catalog": None,
            "models_error": f"{exc.code}: {_redact(str(exc))}",
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must never 500
        traceback.print_exc()
        return {
            **base, "ok": False, "auth_ok": None,
            "models_reachable": False,
            "model_in_catalog": None,
            "models_error": f"{type(exc).__name__}: {_redact(str(exc))}",
        }


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
    print(json.dumps({"ev": "grade", "id": req.id, "total": total, "caps": caps_applied, "model": MODEL}), flush=True)
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
