#!/usr/bin/env python3
"""
prober.py — فحص حالة النماذج والمزودين.

يفحص كل نموذج برسالة صغيرة ويصنّف الحالة:
  OK / QUOTA / RATE_LIMIT / BAD_KEY / MODEL_NOT_FOUND / BLOCKED / BAD_REQUEST / ERROR
ويقرأ Retry-After، ويجلب معلومات الرصيد والحصص حيثما توفر
(مثل /usage في xKiro و /balance في بعض البوابات).
"""

import json
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

STATUS_LABELS = {
    "OK": ("ok", "Working"),
    "QUOTA": ("quota", "Quota exhausted"),
    "RATE_LIMIT": ("rate", "Rate limited"),
    "BAD_KEY": ("badkey", "Invalid key"),
    "MODEL_NOT_FOUND": ("notfound", "Not found"),
    "BLOCKED": ("blocked", "Blocked"),
    "BAD_REQUEST": ("badreq", "Bad request"),
    "ERROR": ("error", "Error"),
}
STATUS_ICONS = {
    "OK": "✅",
    "QUOTA": "💀",
    "RATE_LIMIT": "⏳",
    "BAD_KEY": "🔑",
    "MODEL_NOT_FOUND": "🚫",
    "BLOCKED": "🛡️",
    "BAD_REQUEST": "⚠️",
    "ERROR": "❌",
}


def _headers(provider, extra=None):
    h = {
        "Accept": "application/json",
        "User-Agent": UA,
    }
    if provider.get("key"):
        h["Authorization"] = "Bearer " + provider["key"]
    if extra:
        h.update(extra)
    return h


def fetch_models(provider, timeout=25):
    """جلب قائمة نماذج المزود."""
    req = urllib.request.Request(
        provider["base_url"].rstrip("/") + "/models",
        headers=_headers(provider),
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return data.get("data", []) if isinstance(data, dict) else []


def is_free(model_id, pricing):
    mid = str(model_id).lower()
    if ":free" in mid or "free" in mid:
        return True
    if isinstance(pricing, dict):
        i = pricing.get("input")
        o = pricing.get("output")
        if i == 0 and o == 0:
            return True
    return False


def test_model(provider, model_id, timeout=45):
    """اختبار نموذج واحد وتصنيف حالته."""
    t0 = time.time()
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    headers = _headers(provider, {"Content-Type": "application/json"})
    req = urllib.request.Request(
        provider["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    retry_after = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8", "replace"))
            content = ""
            try:
                content = body["choices"][0]["message"]["content"][:40]
            except Exception:
                pass
            return {
                "model": model_id,
                "status": "OK",
                "code": 200,
                "latency": round(time.time() - t0, 1),
                "reply": content or "✓",
                "retry_after": None,
                "detail": "",
            }
    except urllib.error.HTTPError as e:
        retry_after = e.headers.get("Retry-After") if e.headers else None
        raw = ""
        try:
            raw = e.read(400).decode("utf-8", "replace")
        except Exception:
            pass
        low = raw.lower()
        code = e.code
        if code == 429:
            if any(w in low for w in ("quota", "exhausted", "insufficient")):
                state = "QUOTA"
            else:
                state = "RATE_LIMIT"
        elif code == 401:
            state = "BAD_KEY"
        elif code == 404:
            state = "MODEL_NOT_FOUND"
        elif code in (403, 1010):
            state = "BLOCKED"
        elif code in (400, 405):
            state = "BAD_REQUEST"
        else:
            state = f"HTTP_{code}"
        return {
            "model": model_id,
            "status": state,
            "code": code,
            "latency": round(time.time() - t0, 1),
            "reply": "",
            "retry_after": retry_after,
            "detail": raw[:200].replace("\n", " "),
        }
    except Exception as ex:
        return {
            "model": model_id,
            "status": "ERROR",
            "code": 0,
            "latency": round(time.time() - t0, 1),
            "reply": "",
            "retry_after": None,
            "detail": str(ex)[:120],
        }


def fetch_balance(provider, timeout=20):
    """محاولة جلب الرصيد/الحصص من نقاط نهاية شائعة."""
    base = provider["base_url"].rstrip("/")
    endpoints = ["/usage", "/balance", "/credits", "/v1/usage"]
    for ep in endpoints:
        try:
            req = urllib.request.Request(base + ep, headers=_headers(provider))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            if isinstance(data, dict):
                # نمط xKiro: free_tokens + wallet
                if "free_tokens" in data:
                    ft = data["free_tokens"]
                    remaining = ft.get("remaining", 0)
                    limit = ft.get("limit_per_day", 0)
                    used = ft.get("used_today", 0)
                    plan = data.get("plan") or "free"
                    wallet = (data.get("wallet") or {}).get("balance_usd", 0)
                    return {
                        "kind": "xkiro",
                        "remaining_tokens": remaining,
                        "limit_per_day": limit,
                        "used_today": used,
                        "plan": plan,
                        "wallet_usd": wallet,
                    }
                # نمط عام: balance/credits
                if "balance" in data:
                    return {"kind": "generic", "balance": data["balance"]}
        except Exception:
            continue
    return None


def check_many(provider, models, workers=8, progress=None):
    """فحص عدة نماذج لمزود واحد بالتوازي."""
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(test_model, provider, m): m for m in models}
        done = 0
        for fut in as_completed(futs):
            m = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"model": m, "status": "ERROR", "code": 0, "latency": 0,
                     "reply": "", "retry_after": None, "detail": str(e)[:100]}
            r["provider"] = provider["display"]
            r["provider_key"] = provider["name"]
            results.append(r)
            done += 1
            if progress:
                progress(done, len(models), m, r)
    return results


def check_many_limited(jobs, workers=8, max_seconds=30, progress=None):
    """فحص قائمة (provider, model) مع حد زمني أقصى.

    jobs: قائمة من tuples (provider_dict, model_id)
    يعيد النتائج المكتملة فقط خلال max_seconds.
    """
    results = []
    deadline = time.time() + max_seconds
    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        futs = {}
        idx = 0
        for p, m in jobs:
            if time.time() > deadline:
                break
            futs[ex.submit(test_model, p, m)] = (p, m, idx)
            idx += 1
        for fut in as_completed(futs):
            if time.time() > deadline:
                break
            p, m, _ = futs[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"model": m, "status": "ERROR", "code": 0, "latency": 0,
                     "reply": "", "retry_after": None, "detail": str(e)[:100]}
            r["provider"] = p["display"]
            r["provider_key"] = p["name"]
            results.append(r)
            if progress:
                progress(len(results), len(jobs), m, r)
    finally:
        # إلغاء المهام العالقة وإنهاء المنفذ
        for fut in list(futs):
            if not fut.done():
                fut.cancel()
        ex.shutdown(wait=False, cancel_futures=True)
    return results
