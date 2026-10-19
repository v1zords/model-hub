#!/usr/bin/env python3
"""
discovery.py — كشف تلقائي لكل مزودي ومفاتيح API على الجهاز.

يمسح مصادر متعددة:
  • إعدادات Hermes (config.yaml + .env)
  • WorkBuddy (models.json)
  • Claude Code (~/.claude/settings.json + env داخل ~/.claude.json)
  • OpenCode (~/.config/opencode/opencode.json)
  • Gemini CLI (~/.gemini/settings.json)
  • متغيرات البيئة لنظام التشغيل (OPENAI_API_KEY, ANTHROPIC_API_KEY, ...)
  • ملفات .env المنتشرة في المجلد الرئيسي

الناتج: قائمة مزودين من النوع:
  {name, display, base_url, key, key_env, extra_headers, source}
"""

import os
import re
import json
import glob
import sys

HOME = os.path.expanduser("~")
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.join(HOME, "AppData", "Local", "hermes"))
if not os.path.isdir(HERMES_HOME):
    HERMES_HOME = os.path.join(HOME, ".hermes")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# خريطة متغيرات البيئة المعروفة -> (اسم العرض، رابط API الافتراضي)
KNOWN_ENV = {
    "OPENROUTER_API_KEY": ("OpenRouter", "https://openrouter.ai/api/v1"),
    "ANTHROPIC_API_KEY": ("Anthropic Claude", "https://api.anthropic.com/v1"),
    "OPENAI_API_KEY": ("OpenAI", "https://api.openai.com/v1"),
    "GOOGLE_API_KEY": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta"),
    "GEMINI_API_KEY": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta"),
    "DEEPSEEK_API_KEY": ("DeepSeek", "https://api.deepseek.com/v1"),
    "GLM_API_KEY": ("Zhipu GLM", "https://open.bigmodel.cn/api/paas/v4"),
    "ZAI_API_KEY": ("Zhipu GLM", "https://open.bigmodel.cn/api/paas/v4"),
    "MINIMAX_API_KEY": ("MiniMax", "https://api.minimaxi.com/v1"),
    "KIMI_API_KEY": ("Moonshot Kimi", "https://api.moonshot.cn/v1"),
    "DASHSCOPE_API_KEY": ("Alibaba Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "XIAOMI_API_KEY": ("Xiaomi MiMo", "https://api.xiaomi.com/v1"),
    "XAI_API_KEY": ("xAI Grok", "https://api.x.ai/v1"),
    "HF_TOKEN": ("HuggingFace", "https://router.huggingface.co/v1"),
    "NVIDIA_API_KEY": ("NVIDIA NIM", "https://integrate.api.nvidia.com/v1"),
    "TOGETHER_API_KEY": ("Together AI", "https://api.together.xyz/v1"),
    "GROQ_API_KEY": ("Groq", "https://api.groq.com/openai/v1"),
    "FIREWORKS_API_KEY": ("Fireworks AI", "https://api.fireworks.ai/inference/v1"),
    "MISTRAL_API_KEY": ("Mistral", "https://api.mistral.ai/v1"),
    "COHERE_API_KEY": ("Cohere", "https://api.cohere.ai/v1"),
    "PERPLEXITY_API_KEY": ("Perplexity", "https://api.perplexity.ai/v1"),
    "GITHUB_TOKEN": ("GitHub Models", "https://models.github.ai/inference/v1"),
    "AZURE_OPENAI_API_KEY": ("Azure OpenAI", "https://<resource>.openai.azure.com/v1"),
}

# أسماء عادية لمزودين معروفين من WorkBuddy/مصادر أخرى
KNOWN_NAMES = {
    "antseed": ("Antseed (P2P VPN)", "http://127.0.0.1:8377/v1"),
    "xkiro": ("xKiro", "https://api.xkiro.com/v1"),
    "intern-inkstone": ("Intern InkStone", "https://discovery-api.intern-ai.org.cn/v1"),
    "tokenharbor": ("TokenHarbor", "https://tokenharbor.ai/v1"),
    "nararouter": ("NaraRouter", "https://bynara.id/v1"),
    "zenmux": ("ZenMux", "https://zenmux.ai/api/v1"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1"),
    "anthropic": ("Anthropic Claude", "https://api.anthropic.com/v1"),
    "openai": ("OpenAI", "https://api.openai.com/v1"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1"),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta"),
    "google": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta"),
    "groq": ("Groq", "https://api.groq.com/openai/v1"),
    "mistral": ("Mistral", "https://api.mistral.ai/v1"),
    "nvidia": ("NVIDIA NIM", "https://integrate.api.nvidia.com/v1"),
    "openrouter-free": ("OpenRouter", "https://openrouter.ai/api/v1"),
    "huggingface": ("HuggingFace", "https://router.huggingface.co/v1"),
    "copilot": ("GitHub Copilot", ""),
}


def mask_key(key):
    """إخفاء المفتاح في العروض."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "…" + key[-4:]


# ------------------------------------------------------------------
# قراءة الملفات
# ------------------------------------------------------------------

def read_json(path, encoding="utf-8"):
    try:
        with open(path, "r", encoding=encoding) as f:
            return json.load(f)
    except Exception:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return None


def read_env_file(path):
    """قراءة ملف .env -> dict."""
    keys = {}
    if not os.path.exists(path):
        return keys
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip().strip('"\'')
    except Exception:
        pass
    return keys


# ------------------------------------------------------------------
# مصادر الاكتشاف
# ------------------------------------------------------------------

def from_hermes_config():
    """المزودون من config.yaml (قسم providers)."""
    cfg_path = os.path.join(HERMES_HOME, "config.yaml")
    env = read_env_file(os.path.join(HERMES_HOME, ".env"))
    providers = []
    if not os.path.exists(cfg_path):
        return providers
    cur = None
    in_providers = False
    base_url = ""
    key_env = ""
    api_key = ""
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not in_providers:
                    if re.match(r"^providers:\s*$", line):
                        in_providers = True
                    continue
                if line and not line.startswith(" "):
                    break
                m = re.match(r"^  (\w[\w-]*):\s*$", line)
                if m:
                    # حفظ المزود السابق
                    if cur and base_url:
                        key = env.get(key_env, "") if key_env else api_key
                        providers.append({
                            "name": cur,
                            "display": KNOWN_NAMES.get(cur, (cur, ""))[0],
                            "base_url": base_url.rstrip("/"),
                            "key_env": key_env,
                            "key": key or "",
                            "source": "Hermes config",
                        })
                    cur = m.group(1)
                    base_url = ""
                    key_env = ""
                    api_key = ""
                    continue
                if cur:
                    m2 = re.match(r"^    (\w+):\s*(.*?)\s*$", line)
                    if m2:
                        k, v = m2.group(1), m2.group(2).strip().strip('"\'')
                        if k == "base_url":
                            base_url = v
                        elif k == "key_env":
                            key_env = v
                        elif k == "api_key":
                            api_key = v
        # المزود الأخير
        if cur and base_url:
            key = env.get(key_env, "") if key_env else api_key
            providers.append({
                "name": cur,
                "display": KNOWN_NAMES.get(cur, (cur, ""))[0],
                "base_url": base_url.rstrip("/"),
                "key_env": key_env,
                "key": key or "",
                "source": "Hermes config",
            })
    except Exception:
        pass
    return providers


def from_hermes_env():
    """مفاتيح Hermes من .env حسب الأسماء المعروفة."""
    env = read_env_file(os.path.join(HERMES_HOME, ".env"))
    found = []
    for var, (display, base) in KNOWN_ENV.items():
        if var in env and env[var]:
            found.append({
                "name": var.replace("_API_KEY", "").replace("_TOKEN", "").lower(),
                "display": display,
                "base_url": base,
                "key_env": var,
                "key": env[var],
                "source": "Hermes .env",
            })
    return found


def from_workbuddy():
    """المزودون من WorkBuddy models.json."""
    path = os.path.join(HOME, ".workbuddy-ai", "models.json")
    providers = []
    if not os.path.exists(path):
        return providers
    data = read_json(path)
    if not isinstance(data, list):
        return providers
    for m in data:
        if not isinstance(m, dict):
            continue
        vendor = (m.get("vendor") or "").strip()
        url = (m.get("url") or "").strip().rstrip("/")
        if url.endswith("/chat/completions"):
            url = url[: -len("/chat/completions")]
        if not vendor or not url:
            continue
        norm = vendor.lower().replace(" ", "-").replace(":", "-")
        if norm == "antseed-p2p":
            norm = "antseed"
        entry = {
            "name": norm,
            "display": vendor,
            "base_url": url,
            "key_env": "",
            "key": m.get("apiKey", ""),
            "source": "WorkBuddy",
            "models": [m.get("id", "")],
        }
        # دمج إن وجد
        for existing in providers:
            if existing["name"] == norm:
                if existing.get("models"):
                    existing["models"].append(m.get("id", ""))
                break
        else:
            providers.append(entry)
    return providers


def from_claude():
    """مفاتيح من إعدادات Claude Code."""
    providers = []
    # ~/.claude/settings.json — env
    s = read_json(os.path.join(HOME, ".claude", "settings.json"))
    if isinstance(s, dict):
        env = s.get("env", {}) or {}
        for var, val in env.items():
            if var in KNOWN_ENV and val:
                display, base = KNOWN_ENV[var]
                providers.append({
                    "name": var.lower().replace("_api_key", ""),
                    "display": display,
                    "base_url": base,
                    "key_env": var,
                    "key": val,
                    "source": "Claude settings",
                })
    return providers


def from_opencode():
    """مفاتيح من إعدادات OpenCode."""
    providers = []
    for path in [
        os.path.join(HOME, ".config", "opencode", "opencode.json"),
        os.path.join(HOME, ".config", "opencode", "auth.json"),
        os.path.join(HOME, ".opencode.json"),
    ]:
        d = read_json(path)
        if isinstance(d, dict):
            # providers أو credentials
            creds = d.get("credentials", {}) or {}
            for prov, cfg in creds.items():
                if isinstance(cfg, dict):
                    key = cfg.get("key") or cfg.get("api_key") or cfg.get("token")
                    if key:
                        display, base = KNOWN_NAMES.get(prov.lower(), (prov, ""))
                        providers.append({
                            "name": prov.lower(),
                            "display": display,
                            "base_url": base,
                            "key_env": "",
                            "key": key,
                            "source": "OpenCode",
                        })
            provs = d.get("providers", {}) or {}
            for prov, cfg in provs.items():
                if isinstance(cfg, dict):
                    key = cfg.get("key") or cfg.get("api_key")
                    base = cfg.get("base_url") or cfg.get("url") or ""
                    if key:
                        display = KNOWN_NAMES.get(prov.lower(), (prov, ""))[0]
                        providers.append({
                            "name": prov.lower(),
                            "display": display,
                            "base_url": base.rstrip("/"),
                            "key_env": "",
                            "key": key,
                            "source": "OpenCode",
                        })
    return providers


def from_gemini_cli():
    """مفاتيح من Gemini CLI."""
    providers = []
    d = read_json(os.path.join(HOME, ".gemini", "settings.json"))
    if isinstance(d, dict):
        auth = d.get("security", {}).get("auth", {}) or {}
        if auth.get("selectedType") == "gemini-api-key":
            providers.append({
                "name": "gemini",
                "display": "Google Gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "key_env": "GEMINI_API_KEY",
                "key": "",
                "source": "Gemini CLI",
            })
    return providers


def from_system_env():
    """مفاتيح من متغيرات بيئة نظام التشغيل."""
    providers = []
    for var, (display, base) in KNOWN_ENV.items():
        val = os.environ.get(var, "")
        if val:
            providers.append({
                "name": var.lower().replace("_api_key", "").replace("_token", ""),
                "display": display,
                "base_url": base,
                "key_env": var,
                "key": val,
                "source": "Environment",
            })
    return providers


def from_home_env_files():
    """ملفات .env المنتشرة في المجلد الرئيسي وأسطح العمل."""
    providers = []
    patterns = [
        os.path.join(HOME, "*.env"),
        os.path.join(HOME, ".env*"),
        os.path.join(HOME, "Desktop", "*.env"),
        os.path.join(HOME, "Documents", "*.env"),
        os.path.join(HOME, "AppData", "Roaming", "*", ".env"),
    ]
    seen = set()
    for pat in patterns:
        for path in glob.glob(pat):
            try:
                if os.path.getsize(path) > 200_000:
                    continue
                key = os.path.normcase(path)
                if key in seen:
                    continue
                seen.add(key)
                env = read_env_file(path)
                for var, val in env.items():
                    if var in KNOWN_ENV and val:
                        display, base = KNOWN_ENV[var]
                        providers.append({
                            "name": var.lower().replace("_api_key", "").replace("_token", ""),
                            "display": display,
                            "base_url": base,
                            "key_env": var,
                            "key": val,
                            "source": os.path.basename(path),
                        })
            except Exception:
                continue
    return providers


# ------------------------------------------------------------------
# الدمج
# ------------------------------------------------------------------

def discover(include_home_env=True):
    """جمع كل المزودين من كل المصادر ودمج المتكرر."""
    all_providers = []
    all_providers += from_hermes_config()
    all_providers += from_hermes_env()
    all_providers += from_workbuddy()
    all_providers += from_claude()
    all_providers += from_opencode()
    all_providers += from_gemini_cli()
    all_providers += from_system_env()
    if include_home_env:
        all_providers += from_home_env_files()

    # دمج حسب الاسم
    merged = {}
    for p in all_providers:
        name = p["name"]
        if name not in merged:
            merged[name] = {
                "name": name,
                "display": p["display"],
                "base_url": p.get("base_url", ""),
                "key": p.get("key", ""),
                "key_env": p.get("key_env", ""),
                "source": p.get("source", ""),
                "models": list(p.get("models", []) or []),
            }
        else:
            m = merged[name]
            if p.get("key") and not m["key"]:
                m["key"] = p["key"]
            if p.get("base_url") and not m["base_url"]:
                m["base_url"] = p["base_url"]
            if p.get("models"):
                m["models"].extend(p["models"])
            if p.get("source") and p["source"] not in str(m["source"]):
                m["source"] = str(m["source"]) + " + " + p["source"]

    # حذف المزودين بلا رابط ولا مفتاح
    result = []
    for p in merged.values():
        if not p["base_url"]:
            continue
        # تخطي مزود بلا مفتاح إلا إذا كان محلياً (Antseed) أو المعروف أنه بلا مفتاح
        if not p["key"] and not p["name"] in ("antseed",):
            continue
        result.append(p)
    result.sort(key=lambda x: x["display"].lower())
    return result


def discover_with_models(providers, fetch_func):
    """توسيع كل مزود بقائمة نماذجه من دالة الجلب المعطاة."""
    for p in providers:
        try:
            models = fetch_func(p) or []
            p["fetched_models"] = models
            p["model_count"] = len(models)
            p["fetch_error"] = None
        except Exception as e:
            p["fetched_models"] = []
            p["model_count"] = 0
            p["fetch_error"] = str(e)[:120]
    return providers


if __name__ == "__main__":
    provs = discover()
    print(f"تم اكتشاف {len(provs)} مزود:")
    for p in provs:
        key = mask_key(p.get("key", "")) or "—"
        print(f"  {p['display']:<22} | {p['base_url']:<45} | مفتاح: {key} | {p['source']}")
