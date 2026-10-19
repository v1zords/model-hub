#!/usr/bin/env python3
"""
Model Widget — شريط عائم صغير فوق الشاشة (tkinter نقي).

• شريط رفيع 660×44 في أعلى منتصف الشاشة، دائماً في المقدمة، بلا حواف.
• ضغطة يسار = فتح/إغلاق اللوحة المنبثقة.
• سحب بالزر الأيسر = تحريك الشريط.
• لايف: يفحص النماذج في الخلفية، الشغالة ترتفع والمتوقفة تنزل، مؤشرات تتحدث.
"""

import json
import os
import queue
import sys
import threading
import time
import datetime
import tkinter as tk
from tkinter import ttk

# الاستيراد المحلي (الملفات في نفس المجلد)
import discovery
import prober

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(APP_DIR, ".state.json")

BG = "#10151d"
BG2 = "#161d27"
BG3 = "#1c2532"
FG = "#d8dee9"
MUTED = "#6b7a8c"
BORDER = "#232d3d"
GREEN = "#2ecc71"
RED = "#e74c3c"
YELLOW = "#f39c12"

STATUS_SHORT = {
    "OK": "OK", "QUOTA": "OUT", "RATE_LIMIT": "LIM", "BAD_KEY": "KEY",
    "MODEL_NOT_FOUND": "404", "BLOCKED": "BLK", "BAD_REQUEST": "400",
    "ERROR": "ERR",
}
STATUS_COLOR = {
    "OK": GREEN, "QUOTA": RED, "RATE_LIMIT": YELLOW, "BAD_KEY": RED,
    "MODEL_NOT_FOUND": "#8a9bb0", "BLOCKED": "#e67e22", "BAD_REQUEST": "#f1c40f",
    "ERROR": RED,
}
RANK = {"OK": 0, "RATE_LIMIT": 1, "BLOCKED": 2, "BAD_REQUEST": 3,
        "QUOTA": 4, "MODEL_NOT_FOUND": 5, "BAD_KEY": 6, "ERROR": 7}

W, H = 560, 44


class ModelWidget:
    def __init__(self):
        self._ui_queue = queue.Queue()
        self._busy = False
        self._monitor_on = False
        self._monitor_interval = 60
        self._providers = []
        self._results = {}
        self._model_to_key = {}
        self._lang = "en"
        self._drag = None
        self._panel_open = False
        self._pending = 0
        # عدادات تراكمية (بدون إعادة حساب كل مرة)
        self._counts = {k: 0 for k in STATUS_COLOR}
        self._counts["UNKNOWN"] = 0

        self._load_state()

        # === الشريط (tkinter نقي — frameless + حجم ثابت) ===
        self.win = tk.Tk()
        self.win.title("Model Widget")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BG)
        self.win.geometry(self._widget_geometry())
        self.win.resizable(False, False)

        self.canvas = tk.Canvas(self.win, width=W, height=H, bg=BG,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_line(0, H - 1, W, H - 1, fill=BORDER)

        self.dot_id = self.canvas.create_text(20, 18, text="●", fill=GREEN,
                                              font=("Segoe UI", 14))
        self.lbl_model_id = self.canvas.create_text(40, 15, text="Model Hub", anchor="w",
                                                    fill=FG, font=("Segoe UI", 12, "bold"))
        self.lbl_status_id = self.canvas.create_text(40, 34, text="scanning…", anchor="w",
                                                     fill=MUTED, font=("Segoe UI", 9))
        self.chip_ok_id = self.canvas.create_text(240, 22, text="OK 0", anchor="w",
                                                  fill=GREEN, font=("Segoe UI", 10, "bold"))
        self.chip_out_id = self.canvas.create_text(310, 22, text="OUT 0", anchor="w",
                                                   fill=RED, font=("Segoe UI", 10, "bold"))
        self.chip_lim_id = self.canvas.create_text(380, 22, text="LIM 0", anchor="w",
                                                   fill=YELLOW, font=("Segoe UI", 10, "bold"))
        self.btn_lang_id = self.canvas.create_rectangle(494, 9, 540, 35,
                                                        fill=BG2, outline=BORDER)
        self.btn_lang_txt = self.canvas.create_text(517, 22, text="عربي", fill=FG,
                                                    font=("Segoe UI", 10))
        self.canvas.tag_bind(self.btn_lang_id, "<Button-1>", lambda e: self._toggle_lang())
        self.canvas.tag_bind(self.btn_lang_txt, "<Button-1>", lambda e: self._toggle_lang())

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # === اللوحة المنبثقة ===
        self.panel = tk.Toplevel(self.win)
        self.panel.overrideredirect(True)
        self.panel.attributes("-topmost", True)
        self.panel.configure(bg=BG)
        self.panel.withdraw()
        self._build_panel()

        self.win.after(120, self._poll_queue)
        self.win.after(400, self._startup)

    # ------------------------------------------------------------------
    def _widget_geometry(self):
        sw = self.win.winfo_screenwidth()
        x = (sw - W) // 2
        return f"{W}x{H}+{x}+0"

    def _panel_geometry(self):
        pw, ph = 560, 520
        wx = self.win.winfo_x()
        wy = self.win.winfo_y() + H + 2
        sw = self.win.winfo_screenwidth()
        if wx + pw > sw:
            wx = sw - pw - 6
        return f"{pw}x{ph}+{max(wx, 0)}+{wy}"

    # ------------------------------------------------------------------
    def _build_panel(self):
        bar = tk.Frame(self.panel, bg=BG2)
        bar.pack(fill="x")
        self.btn_scan = tk.Button(bar, text="Scan", bg=BG3, fg=FG, bd=0, relief="flat",
                                  activebackground="#2c3a4e", activeforeground=FG,
                                  font=("Segoe UI", 9), padx=10, command=self._start_scan)
        self.btn_scan.pack(side="left", padx=(10, 4), pady=6)
        self.btn_check = tk.Button(bar, text="Check All", bg="#1c5c2c", fg=FG, bd=0,
                                   relief="flat", activebackground="#227a38",
                                   activeforeground=FG, font=("Segoe UI", 9), padx=10,
                                   command=self._start_check_all)
        self.btn_check.pack(side="left", padx=4, pady=6)
        self.btn_monitor = tk.Button(bar, text="Monitor: OFF", bg=BG3, fg=FG, bd=0,
                                     relief="flat", activebackground="#2c3a4e",
                                     activeforeground=FG, font=("Segoe UI", 9), padx=10,
                                     command=self._toggle_monitor)
        self.btn_monitor.pack(side="left", padx=4, pady=6)
        self.btn_export = tk.Button(bar, text="Export", bg=BG3, fg=FG, bd=0,
                                    relief="flat", activebackground="#2c3a4e",
                                    activeforeground=FG, font=("Segoe UI", 9), padx=10,
                                    command=self._export)
        self.btn_export.pack(side="right", padx=(4, 10), pady=6)
        self.lbl_foot = tk.Label(bar, text="", bg=BG2, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_foot.pack(side="right", padx=8)

        frame = tk.Frame(self.panel, bg=BG)
        frame.pack(fill="both", expand=True)
        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure("Treeview", background=BG2, foreground=FG, fieldbackground=BG2,
                            rowheight=24, borderwidth=0, font=("Segoe UI", 10))
            style.configure("Treeview.Heading", background=BG3, foreground="#a8b3c2",
                            font=("Segoe UI", 9, "bold"), borderwidth=0)
            style.map("Treeview", background=[("selected", "#2e4a63")],
                      foreground=[("selected", "#ffffff")])
        except Exception:
            pass

        self.tree = ttk.Treeview(frame, columns=("st", "model", "price", "lat"),
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="")
        self.tree.heading("st", text="St")
        self.tree.heading("model", text="Model")
        self.tree.heading("price", text="Price")
        self.tree.heading("lat", text="ms")
        self.tree.column("#0", width=28, stretch=False)
        self.tree.column("st", width=52, anchor="w")
        self.tree.column("model", width=380, anchor="w")
        self.tree.column("price", width=60, anchor="center")
        self.tree.column("lat", width=60, anchor="center")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double)

        foot = tk.Frame(self.panel, bg=BG2)
        foot.pack(fill="x", side="bottom")
        self.lbl_hint = tk.Label(foot, text="dbl-click = check · click bar = hide",
                                 bg=BG2, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_hint.pack(side="left", padx=10, pady=4)

    # ------------------------------------------------------------------
    def _on_press(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _on_drag(self, e):
        if self._drag:
            x = e.x_root - self._drag[0]
            y = e.y_root - self._drag[1]
            self.win.geometry(f"+{x}+{y}")
            if self._panel_open:
                self.panel.geometry(self._panel_geometry())

    def _on_release(self, e):
        if self._drag is not None:
            self._drag = None
            self._toggle_panel()

    def _toggle_panel(self):
        if self._panel_open:
            self.panel.withdraw()
            self._panel_open = False
        else:
            self.panel.geometry(self._panel_geometry())
            self.panel.deiconify()
            self._panel_open = True
            # إعادة بناء الجدول بالنتائج المخزنة (النتائج أثناء الإغلاق لم تُطبق)
            self._populate_tree()
            self._sort_by_status()
            self.win.lift()
            self.panel.lift()

    # ------------------------------------------------------------------
    def _toggle_lang(self):
        self._lang = "ar" if self._lang == "en" else "en"
        self.canvas.itemconfigure(self.btn_lang_txt,
                                  text="EN" if self._lang == "ar" else "عربي")
        self._apply_lang()

    def _apply_lang(self):
        self.btn_scan.configure(text={"en": "Scan", "ar": "مسح"}[self._lang])
        self.btn_check.configure(text={"en": "Check All", "ar": "فحص الكل"}[self._lang])
        self.btn_monitor.configure(text="Monitor: " + ("ON" if self._monitor_on else "OFF"))
        self.btn_export.configure(text={"en": "Export", "ar": "تصدير"}[self._lang])
        self.lbl_hint.configure(text={
            "en": "dbl-click = check · click bar = hide",
            "ar": "نقرتان = فحص · نقر على الشريط = إخفاء"}[self._lang])
        self.canvas.itemconfigure(self.lbl_model_id, text=self._lang_title())
        self._apply_lang_to_headings()

    def _lang_title(self):
        return "Model Hub" if self._lang == "en" else "مركز النماذج"

    # ------------------------------------------------------------------
    def _poll_queue(self):
        # معالجة محدودة لكل نبضة — يمنع تجميد الواجهة عند فيض النتائج
        processed = 0
        try:
            while processed < 40:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as e:
                    print("UI:", e)
                processed += 1
        except queue.Empty:
            pass
        self.win.after(80, self._poll_queue)

    def _post(self, fn):
        self._ui_queue.put(fn)

    # ------------------------------------------------------------------
    def _startup(self):
        self._set_status("scanning…")
        self._start_scan()

    def _set_status(self, txt):
        self.canvas.itemconfigure(self.lbl_status_id, text=txt)

    def _start_scan(self):
        if self._busy:
            return
        self._busy = True
        self.btn_scan.configure(state="disabled")

        def worker():
            try:
                provs = discovery.discover()
                total = max(len(provs), 1)
                for i, p in enumerate(provs):
                    try:
                        p["fetched_models"] = prober.fetch_models(p)
                        p["model_count"] = len(p["fetched_models"])
                        p["fetch_error"] = None
                    except Exception as e:
                        p["fetched_models"] = []
                        p["model_count"] = 0
                        p["fetch_error"] = str(e)[:100]
                    self._post(lambda n=i + 1: self._set_status(f"fetched {n}/{total}…"))
                self._post(lambda: self._on_scan_done(provs))
            except Exception:
                self._post(lambda: self._set_status("error"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_done(self, provs):
        self._busy = False
        self.btn_scan.configure(state="normal")
        self._providers = provs
        self._refresh_all()
        self._quick_background_check()

    # ------------------------------------------------------------------
    def _refresh_all(self):
        self._populate_tree()
        self._recount_all()
        self._update_widget_status()

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._model_to_key.clear()
        for p in self._providers:
            models = p.get("fetched_models") or []

            def sort_key(m):
                mid = m.get("id", "")
                key = f"{p['name']}::{mid}"
                st = self._results.get(key, {}).get("status", "")
                free = 0 if prober.is_free(mid, m.get("pricing")) else 1
                return (free, RANK.get(st, 8), mid.lower())

            models_sorted = sorted(models, key=sort_key)
            parent = self.tree.insert("", "end", text="",
                                      values=("", p["display"], f"{len(models)}", ""))
            self.tree.item(parent, open=True)
            if p.get("fetch_error"):
                self.tree.insert(parent, "end", text="",
                                 values=("ERR", "⚠ " + p["fetch_error"][:50], "", ""))
                continue
            for m in models_sorted:
                mid = m.get("id", "")
                key = f"{p['name']}::{mid}"
                price = "F" if prober.is_free(mid, m.get("pricing")) else "$"
                iid = self.tree.insert(parent, "end", text="",
                                       values=("?", mid, price, ""))
                self._model_to_key[iid] = key
                if key in self._results:
                    self._apply_result(iid, self._results[key])
        self._apply_lang_to_headings()

    def _apply_lang_to_headings(self):
        heads = {"en": {"st": "St", "model": "Model", "price": "Price", "lat": "ms"},
                 "ar": {"st": "ح", "model": "النموذج", "price": "السعر", "lat": "مللي"}}
        for col, txt in heads[self._lang].items():
            try:
                self.tree.heading(col, text=txt)
            except Exception:
                pass

    def _apply_result(self, iid, r):
        st = r.get("status", "UNKNOWN")
        icon = "✓" if st == "OK" else ("✕" if st in ("QUOTA", "BAD_KEY", "ERROR") else "~")
        short = STATUS_SHORT.get(st, st)
        lat = r.get("latency", 0)
        lat_txt = f"{int(lat * 1000)}" if lat else ""
        vals = list(self.tree.item(iid, "values"))
        vals[0] = f"{icon} {short}"
        vals[3] = lat_txt
        self.tree.item(iid, values=tuple(vals))
        color = STATUS_COLOR.get(st, "#8a9bb0")
        try:
            self.tree.tag_configure("tag_" + st, foreground=color)
            self.tree.item(iid, tags=("tag_" + st,))
        except Exception:
            pass

    def _sort_by_status(self):
        for parent in self.tree.get_children():
            children = list(self.tree.get_children(parent))

            def rank(iid):
                key = self._model_to_key.get(iid, "")
                st = self._results.get(key, {}).get("status", "")
                return RANK.get(st, 8)

            ordered = sorted(children, key=rank)
            for pos, iid in enumerate(ordered):
                self.tree.move(iid, parent, pos)

    def _update_counts(self):
        # عدادات تراكمية — بدون إعادة حساب كل النتائج
        self.canvas.itemconfigure(self.chip_ok_id, text=f"OK {self._counts.get('OK', 0)}")
        self.canvas.itemconfigure(self.chip_out_id, text=f"OUT {self._counts.get('QUOTA', 0)}")
        self.canvas.itemconfigure(self.chip_lim_id, text=f"LIM {self._counts.get('RATE_LIMIT', 0)}")

    def _recount_all(self):
        # إعادة بناء العدادات من النتائج (عند البداية فقط)
        self._counts = {k: 0 for k in STATUS_COLOR}
        for r in self._results.values():
            st = r.get("status", "UNKNOWN")
            self._counts[st] = self._counts.get(st, 0) + 1
        self._update_counts()

    def _update_widget_status(self):
        total = sum(p.get("model_count", 0) for p in self._providers)
        prov_n = len(self._providers)
        n_ok = sum(1 for r in self._results.values() if r["status"] == "OK")
        color = GREEN if n_ok > 0 else (RED if any(
            r["status"] in ("QUOTA",) for r in self._results.values()) else YELLOW)
        self.canvas.itemconfigure(self.dot_id, fill=color)
        self._set_status(f"{prov_n}p · {total}m · {len(self._results)}chk")

    # ------------------------------------------------------------------
    def _quick_background_check(self):
        def worker():
            jobs = []
            for p in self._providers:
                models = p.get("fetched_models") or []
                free_ids = [m["id"] for m in models
                            if m.get("id") and prober.is_free(m["id"], m.get("pricing"))]
                jobs.extend((p, mid) for mid in free_ids[:60])
            if not jobs:
                return
            results = prober.check_many_limited(jobs, workers=8, max_seconds=20)
            for r in results:
                self._post(lambda rr=r: self._on_result(rr))
            self._post(self._on_check_done)

        threading.Thread(target=worker, daemon=True).start()

    def _start_check_all(self):
        if self._busy or not self._providers:
            return
        self._busy = True
        self.btn_check.configure(state="disabled")

        def worker():
            jobs = []
            for p in self._providers:
                for m in p.get("fetched_models") or []:
                    if m.get("id"):
                        jobs.append((p, m["id"]))
            results = prober.check_many_limited(jobs, workers=12, max_seconds=90)
            for r in results:
                self._post(lambda rr=r: self._on_result(rr))
            self._post(self._on_check_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_result(self, r):
        pkey = r.get("provider_key", "")
        st = r.get("status", "UNKNOWN")
        # تحديث تراكمي للعدادات: أنقص الحالة القديمة، زد الجديدة
        for iid, k in self._model_to_key.items():
            if k.endswith("::" + r["model"]) and k.startswith(pkey):
                old = self._results.get(k, {}).get("status")
                if old in self._counts:
                    self._counts[old] = max(0, self._counts[old] - 1)
                self._counts[st] = self._counts.get(st, 0) + 1
                self._results[k] = r
                # تحديث الجدول فقط عندما اللوحة مفتوحة (حتى لا نجمّد الخلفية)
                if self._panel_open:
                    self._apply_result(iid, r)
                break
        self._update_counts()
        self._update_widget_status()
        # لا نعيد الترتيب أثناء التدفق — يتم عند انتهاء الدفعة (خفيف)

    def _on_check_done(self):
        self._busy = False
        self.btn_check.configure(state="normal")
        if self._panel_open:
            self._sort_by_status()
        self._recount_all()
        self._update_widget_status()
        self._save_state()

    def _on_double(self, e):
        iid = self.tree.focus()
        if iid not in self._model_to_key:
            return
        key = self._model_to_key[iid]
        pname, mid = key.split("::", 1)
        p = next((x for x in self._providers if x["name"] == pname), None)
        if not p:
            return

        def worker():
            r = prober.test_model(p, mid)
            r["provider_key"] = p["name"]
            self._post(lambda rr=r: self._on_result(rr))
            self._save_state()

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    def _toggle_monitor(self):
        self._monitor_on = not self._monitor_on
        self.btn_monitor.configure(
            text="Monitor: ON" if self._monitor_on else "Monitor: OFF",
            bg="#1c5c2c" if self._monitor_on else BG3)
        if self._monitor_on:
            self._monitor_loop()

    def _monitor_loop(self):
        if not self._monitor_on:
            return
        self.lbl_foot.configure(
            text=datetime.datetime.now().strftime("monitor %H:%M:%S"))

        def worker():
            jobs = []
            for p in self._providers:
                models = p.get("fetched_models") or []
                free_ids = [m["id"] for m in models
                            if m.get("id") and prober.is_free(m["id"], m.get("pricing"))]
                jobs.extend((p, mid) for mid in free_ids[:30])
            if jobs:
                results = prober.check_many_limited(jobs, workers=8, max_seconds=20)
                for r in results:
                    self._post(lambda rr=r: self._on_result(rr))
                self._post(self._update_widget_status)
            self.win.after(self._monitor_interval * 1000, self._monitor_loop)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    st = json.load(f)
                if st.get("lang") in ("en", "ar"):
                    self._lang = st["lang"]
                self._results = st.get("results", {})
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"lang": self._lang, "results": self._results}, f,
                          ensure_ascii=False, indent=1)
        except Exception:
            pass

    def _export(self):
        try:
            path = os.path.join(APP_DIR, "models_report.json")
            report = {"exported": datetime.datetime.now().isoformat(), "providers": []}
            for p in self._providers:
                models = []
                for m in p.get("fetched_models") or []:
                    mid = m.get("id", "")
                    key = f"{p['name']}::{mid}"
                    models.append({
                        "model": mid,
                        "pricing": m.get("pricing"),
                        "status": self._results.get(key, {}).get("status", "untested"),
                    })
                report["providers"].append({
                    "name": p["name"], "display": p["display"],
                    "base_url": p["base_url"], "source": p.get("source", ""),
                    "model_count": len(models), "models": models,
                })
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.lbl_foot.configure(text=f"saved: {os.path.basename(path)}")
        except Exception as e:
            self.lbl_foot.configure(text="export err: " + str(e)[:40])

    # ------------------------------------------------------------------
    def run(self):
        try:
            self.win.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self._save_state()
