# Model Hub — AI Providers & Models Monitor

**شريط عائم صغير فوق شاشتك يكتشف ويراقب كل نماذج الذكاء الاصطناعي على جهازك.**

A tiny floating desktop widget that auto-discovers every AI provider & model on your machine, checks their live status (working / quota exhausted / rate limited), and tells you when your free quota comes back.

---

## ✨ Features

- 🧭 **Auto-discovery** — scans your whole machine for API keys: Hermes config, WorkBuddy, Claude Code, OpenCode, Gemini CLI, environment variables, and `.env` files. No manual setup.
- 📊 **Live monitoring** — checks every model with a real ping. Working models rise, exhausted models sink. Live counters: ✅ OK / 💀 OUT / ⏳ LIM.
- ⏰ **Quota tracking** — detects `429 Quota exceeded` and `Rate limit` (reads `Retry-After`), so you always know *when* your free quota returns.
- 🖱️ **Widget UX** — a 560×44 frameless bar pinned at the top-center of your screen. **Left-click** toggles the details panel; **drag** to move it.
- 🏷️ **Platform names** — every model is shown with its company/platform name automatically.
- 🌐 **Bilingual** — English / العربية with one click.
- 🔒 **Privacy** — API keys are detected locally and always shown **masked**. Nothing leaves your machine.
- 📤 **Export** — one-click JSON report of all providers, models & statuses.

## 🖥️ Supported Platforms / Providers

Works with any **OpenAI-compatible** or **Anthropic-compatible** API:

Antseed (P2P) · OpenRouter · xKiro · Intern InkStone · TokenHarbor · ZenMux · NVIDIA NIM · NaraRouter · DeepSeek · OpenAI · Anthropic · Google Gemini · Mistral · Groq · Together · Fireworks · HuggingFace · Cohere … and any key found on your machine.

## 🚀 Quick Start

### Option A — Download the release (Windows)

1. Download `ModelHub.zip` from [Releases](https://github.com/v1zords/model-hub/releases)
2. Extract and run `ModelHub.exe` — no Python needed.
3. The widget appears at the top-center of your screen.

### Option B — Run from source

```bash
git clone https://github.com/v1zords/model-hub.git
cd model-hub
python main.py
```

Requires Python 3.10+ (tkinter built-in).

## 🎮 Usage

| Action | Result |
|---|---|
| **Left-click** the bar | Open / close the details panel |
| **Drag** the bar | Move it anywhere |
| **Double-click** a model | Check that model instantly |
| **Check All** button | Test every model in parallel |
| **Monitor** button | Auto re-check every 60s — get notified when a quota returns |
| **عربي / EN** | Switch language |

## 📷 Screenshot

```
┌──────────────────────────────────────────────┐
│ ● Model Hub   8p · 1535m · 82chk  OK 6 OUT 58 LIM 18  [عربي] │
└──────────────────────────────────────────────┘
  ▼ Antseed (P2P VPN)  — 579 models
     ✓ OK   deepseek-v4-flash            F
     ✕ OUT  qwen3.8-27b                  F
     ~ LIM  glm-5.3-flash               $
```

## 🤝 Support / Donate

If Model Hub saves you time, consider supporting the project:

[!["GitHub Sponsors"](https://img.shields.io/badge/GitHub%20Sponsors-Support-ff69b4)](https://github.com/sponsors/v1zords)
[![BuyMeACoffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-FFDD00)](https://www.buymeacoffee.com/v1zords)

- **GitHub Sponsors**: https://github.com/sponsors/v1zords
- **Buy Me a Coffee**: https://www.buymeacoffee.com/v1zords
- **PayPal**: https://paypal.me/v1zords

Every contribution helps keep development going. Thank you! 🙏

## 🛠️ Development

```bash
# Build the standalone exe
pip install pyinstaller
pyinstaller --onedir --windowed --name ModelHub main.py
```

## 📄 License

MIT License — free to use, modify, and distribute. See [LICENSE](LICENSE).
