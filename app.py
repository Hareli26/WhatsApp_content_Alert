# -*- coding: utf-8 -*-
"""
WhatsApp Online Monitor — Multi-contact edition
Monitor multiple contacts simultaneously.
Google Contacts autocomplete via vCard import.
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import subprocess
import os
import json
import ctypes
import ctypes.wintypes
import urllib.request
import urllib.parse
import re

# ── Hide console window immediately ───────────────────────────────────────────
try:
    ctypes.windll.user32.ShowWindow(
        ctypes.windll.kernel32.GetConsoleWindow(), 0)
except Exception:
    pass


# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def ensure_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa
        return True
    except ImportError:
        return False


# ── vCard / Google Contacts parser ────────────────────────────────────────────

def parse_vcf(path: str) -> list:
    """Extract FN (full name) fields from a vCard export file."""
    names = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for m in re.finditer(r"^FN[^:]*:(.+)$", content, re.MULTILINE):
            name = m.group(1).strip()
            if name:
                names.append(name)
    except Exception:
        pass
    return sorted(set(names))


# ── Windows helpers ───────────────────────────────────────────────────────────

def _minimize_window_containing(title_fragment: str):
    try:
        user32 = ctypes.windll.user32
        found  = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def cb(hwnd, _):
            n   = user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(n)
            user32.GetWindowTextW(hwnd, buf, n)
            if title_fragment.lower() in buf.value.lower():
                found.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        for hwnd in found:
            user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE
    except Exception:
        pass


# ── Colours / fonts ───────────────────────────────────────────────────────────

BG        = "#0d1117"
BG2       = "#161b22"
BG3       = "#21262d"
GREEN     = "#238636"
GREEN_H   = "#2ea043"
RED       = "#da3633"
RED_H     = "#f85149"
BLUE      = "#1f6feb"
BLUE_H    = "#388bfd"
FG        = "#c9d1d9"
FG_DIM    = "#8b949e"
FG_DIMMER = "#484f58"
TEAL      = "#075e54"
TEAL_L    = "#c8eed8"
YELLOW    = "#d29922"
CYAN      = "#58a6ff"
LIME      = "#3fb950"
LOG_FG    = "#79c0ff"

FONT      = ("Segoe UI", 10)
FONT_B    = ("Segoe UI", 10, "bold")
FONT_LG   = ("Segoe UI", 13)
FONT_H    = ("Segoe UI", 15, "bold")
FONT_MONO = ("Consolas", 9)
FONT_SM   = ("Segoe UI", 9)


# ── Status definitions ────────────────────────────────────────────────────────

STATUS_DOT = {
    "idle":       FG_DIMMER,
    "starting":   YELLOW,
    "monitoring": CYAN,
    "online":     LIME,
    "offline":    FG_DIMMER,
    "error":      RED_H,
    "stopped":    FG_DIMMER,
    "not found":  RED_H,
}
STATUS_TEXT = {
    "idle":       "Idle",
    "starting":   "Starting...",
    "monitoring": "Monitoring",
    "online":     "🟢  Online!",
    "offline":    "Offline",
    "error":      "Error",
    "stopped":    "Stopped",
    "not found":  "Not found",
}


# ── Per-contact data model ────────────────────────────────────────────────────

class ContactEntry:
    def __init__(self, name: str):
        self.name        = name
        self.status      = "idle"
        self.thread      = None
        self.stop_event  = threading.Event()
        self.page        = None   # Playwright page (tab) for this contact
        # UI widget refs
        self.row_frame   = None
        self.dot_lbl     = None
        self.status_lbl  = None
        self._remove_btn = None


# ── Main application ──────────────────────────────────────────────────────────

class WhatsAppMonitor:

    def __init__(self):
        self.contacts: list         = []   # list[ContactEntry]
        self._browser_lock          = threading.Lock()
        self.browser                = None
        self.main_page              = None
        self._pw_ctx                = None
        self._browser_ready         = False

        cfg = load_config()
        self._google_contacts: list = cfg.get("google_contacts", [])

        self.root = tk.Tk()
        self.root.title("WhatsApp Monitor")
        self.root.geometry("500x660")
        self.root.minsize(480, 540)
        self.root.configure(bg=BG)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self.tg_token_var  = tk.StringVar(value=cfg.get("tg_token",  ""))
        self.tg_chatid_var = tk.StringVar(value=cfg.get("tg_chat_id", ""))

        self._build_header()
        self._build_monitor_page()
        self._build_settings_page()
        self._show_page("monitor")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        self.header = tk.Frame(self.root, bg=TEAL, pady=14)
        self.header.pack(fill=tk.X)

        tb = tk.Frame(self.header, bg=TEAL)
        tb.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(16, 0))

        tk.Label(tb, text="📱  WhatsApp Monitor",
                 font=FONT_H, fg="white", bg=TEAL).pack(anchor=tk.W)

        self.header_sub = tk.Label(
            tb, text="Get notified when contacts come online",
            font=FONT_SM, fg=TEAL_L, bg=TEAL)
        self.header_sub.pack(anchor=tk.W, pady=(2, 0))

        self.nav_btn = tk.Button(
            self.header, text="⚙", font=("Segoe UI", 16),
            bg=TEAL, fg=TEAL_L, activebackground=TEAL, activeforeground="white",
            relief=tk.FLAT, cursor="hand2", bd=0,
            command=self._go_settings
        )
        self.nav_btn.pack(side=tk.RIGHT, padx=12)

    # ── Monitor page ──────────────────────────────────────────────────────────

    def _build_monitor_page(self):
        self.page_monitor = tk.Frame(self.root, bg=BG, padx=20, pady=12)

        # Section title
        sec_row = tk.Frame(self.page_monitor, bg=BG)
        sec_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(sec_row, text="Contacts to monitor",
                 font=FONT_B, fg=FG_DIM, bg=BG).pack(side=tk.LEFT)
        self.count_lbl = tk.Label(sec_row, text="", font=FONT_SM, fg=FG_DIMMER, bg=BG)
        self.count_lbl.pack(side=tk.LEFT, padx=(8, 0))

        # Scrollable contact list
        list_card = tk.Frame(self.page_monitor, bg=BG2)
        list_card.pack(fill=tk.X, pady=(0, 8))

        self.contacts_canvas = tk.Canvas(
            list_card, bg=BG2, highlightthickness=0, height=165)
        vsb = tk.Scrollbar(list_card, orient="vertical",
                           command=self.contacts_canvas.yview)
        self.contacts_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.contacts_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.contacts_inner = tk.Frame(self.contacts_canvas, bg=BG2)
        self._cwin = self.contacts_canvas.create_window(
            (0, 0), window=self.contacts_inner, anchor="nw")

        self.contacts_inner.bind(
            "<Configure>",
            lambda e: self.contacts_canvas.configure(
                scrollregion=self.contacts_canvas.bbox("all")))
        self.contacts_canvas.bind(
            "<Configure>",
            lambda e: self.contacts_canvas.itemconfig(self._cwin, width=e.width))
        self.contacts_canvas.bind(
            "<MouseWheel>",
            lambda e: self.contacts_canvas.yview_scroll(-(e.delta // 120), "units"))

        # Empty state placeholder
        self.empty_lbl = tk.Label(
            self.contacts_inner,
            text="No contacts yet — add one below  ↓",
            font=FONT_SM, fg=FG_DIMMER, bg=BG2, pady=22)
        self.empty_lbl.pack()

        # ── Add contact row ───────────────────────────────────────────────────
        add_row = tk.Frame(self.page_monitor, bg=BG)
        add_row.pack(fill=tk.X, pady=(0, 0))

        add_ef = tk.Frame(add_row, bg=BG3, pady=2, padx=2)
        add_ef.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.add_var = tk.StringVar()
        self.add_entry = tk.Entry(
            add_ef, textvariable=self.add_var,
            font=FONT_LG, bg=BG3, fg="white",
            insertbackground="white", relief=tk.FLAT, bd=4)
        self.add_entry.pack(fill=tk.X, ipady=6)
        self.add_entry.bind("<Return>",   lambda _: self._add_contact())
        self.add_entry.bind("<KeyRelease>", self._on_add_key)
        self.add_entry.bind(
            "<FocusOut>", lambda e: self.root.after(200, self._hide_autocomplete))

        tk.Button(
            add_row, text="+ Add",
            font=FONT_B, bg=GREEN, fg="white",
            activebackground=GREEN_H, activeforeground="white",
            relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
            command=self._add_contact
        ).pack(side=tk.LEFT, padx=(6, 0))

        # ── Autocomplete popup (shown dynamically) ────────────────────────────
        self.autocomplete_frame = tk.Frame(self.page_monitor, bg=BG3, bd=0)
        # Not packed by default

        # ── History chips ─────────────────────────────────────────────────────
        self.history_frame = tk.Frame(self.page_monitor, bg=BG)
        self.history_frame.pack(fill=tk.X, pady=(4, 8))

        # ── Telegram badge + quick test ───────────────────────────────────────
        tg_row = tk.Frame(self.page_monitor, bg=BG)
        tg_row.pack(fill=tk.X, pady=(0, 4))

        self.tg_badge = tk.Label(
            tg_row, text="", font=FONT_SM, fg=BLUE_H, bg=BG, anchor=tk.W)
        self.tg_badge.pack(side=tk.LEFT)

        self.tg_quick_test_btn = tk.Button(
            tg_row, text="✈ Test",
            font=("Segoe UI", 8), bg=BG3, fg=BLUE_H,
            activebackground=BLUE, activeforeground="white",
            relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
            command=self._quick_test_telegram)
        self.tg_quick_test_btn.pack(side=tk.RIGHT)

        # ── Activity log ──────────────────────────────────────────────────────
        tk.Label(self.page_monitor, text="Activity log",
                 font=FONT_B, fg=FG_DIM, bg=BG).pack(anchor=tk.W)

        lf = tk.Frame(self.page_monitor, bg=BG2, pady=2, padx=2)
        lf.pack(fill=tk.BOTH, expand=True, pady=(4, 10))

        self.log_widget = tk.Text(
            lf, font=FONT_MONO, bg=BG, fg=LOG_FG,
            relief=tk.FLAT, state=tk.DISABLED, height=5,
            wrap=tk.WORD, padx=6, pady=6)
        self.log_widget.pack(fill=tk.BOTH, expand=True)

        # ── Control buttons ───────────────────────────────────────────────────
        br = tk.Frame(self.page_monitor, bg=BG)
        br.pack(fill=tk.X)

        self.start_all_btn = tk.Button(
            br, text="▶  Start All",
            font=FONT_B, bg=GREEN, fg="white",
            activebackground=GREEN_H, activeforeground="white",
            relief=tk.FLAT, padx=16, pady=10, cursor="hand2",
            command=self._start_all)
        self.start_all_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.stop_all_btn = tk.Button(
            br, text="■  Stop All",
            font=FONT_B, bg=BG3, fg=RED_H,
            activebackground=RED, activeforeground="white",
            relief=tk.FLAT, padx=16, pady=10, cursor="hand2",
            state=tk.DISABLED, command=self._stop_all)
        self.stop_all_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(6, 0))

        # Init
        self._refresh_history_chips()
        self._refresh_tg_badge()

    # ── Contact list ──────────────────────────────────────────────────────────

    def _add_contact(self):
        name = self.add_var.get().strip()
        if not name:
            return
        if any(c.name.lower() == name.lower() for c in self.contacts):
            self._log(f"'{name}' is already in the list")
            self.add_var.set("")
            return
        self.add_var.set("")
        self._hide_autocomplete()
        entry = ContactEntry(name)
        self.contacts.append(entry)
        self._add_to_history(name)
        self._build_contact_row(entry)
        self._update_count_and_buttons()

    def _build_contact_row(self, entry: ContactEntry):
        if self.empty_lbl.winfo_manager():
            self.empty_lbl.pack_forget()

        row = tk.Frame(self.contacts_inner, bg=BG2)
        row.pack(fill=tk.X, side=tk.TOP)

        # Separator for non-first rows
        if len(self.contacts) > 1:
            tk.Frame(row, bg=BG3, height=1).pack(fill=tk.X)

        inner = tk.Frame(row, bg=BG2, padx=12, pady=9)
        inner.pack(fill=tk.X)

        dot = tk.Label(inner, text="●", font=("Segoe UI", 13),
                       fg=FG_DIMMER, bg=BG2)
        dot.pack(side=tk.LEFT)

        tk.Label(inner, text=entry.name,
                 font=FONT_B, fg=FG, bg=BG2, anchor=tk.W
                 ).pack(side=tk.LEFT, padx=(10, 4), fill=tk.X, expand=True)

        status_lbl = tk.Label(inner, text="Idle",
                              font=FONT_SM, fg=FG_DIMMER, bg=BG2)
        status_lbl.pack(side=tk.LEFT, padx=(0, 8))

        remove_btn = tk.Button(
            inner, text="✕",
            font=("Segoe UI", 10), bg=BG2, fg=FG_DIMMER,
            activebackground=BG3, activeforeground=RED_H,
            relief=tk.FLAT, padx=6, pady=0, cursor="hand2",
            command=lambda e=entry: self._remove_contact(e))
        remove_btn.pack(side=tk.RIGHT)

        entry.row_frame  = row
        entry.dot_lbl    = dot
        entry.status_lbl = status_lbl

        self.contacts_canvas.after(50, lambda: self.contacts_canvas.yview_moveto(1.0))

    def _remove_contact(self, entry: ContactEntry):
        entry.stop_event.set()
        entry.row_frame.destroy()
        self.contacts.remove(entry)
        if not self.contacts:
            self.empty_lbl.pack()
        self._update_count_and_buttons()
        self._log(f"Removed: {entry.name}")

    def _update_contact_status(self, entry: ContactEntry, status: str):
        entry.status = status
        c = STATUS_DOT.get(status,  FG_DIMMER)
        t = STATUS_TEXT.get(status, status)
        if entry.dot_lbl:
            entry.dot_lbl.config(fg=c)
        if entry.status_lbl:
            entry.status_lbl.config(
                text=t,
                fg=c if status not in ("idle", "offline", "stopped") else FG_DIMMER)
        self._update_count_and_buttons()

    def _update_count_and_buttons(self):
        n      = len(self.contacts)
        active = sum(1 for c in self.contacts
                     if c.status in ("starting", "monitoring", "online"))
        idle   = sum(1 for c in self.contacts
                     if c.status in ("idle", "stopped", "error", "offline", "not found"))

        if n == 0:
            self.count_lbl.config(text="")
        elif active:
            self.count_lbl.config(text=f"({active}/{n} active)", fg=CYAN)
        else:
            self.count_lbl.config(text=f"({n})", fg=FG_DIMMER)

        self.start_all_btn.config(
            state=tk.NORMAL if (n > 0 and idle > 0) else tk.DISABLED)
        self.stop_all_btn.config(
            state=tk.NORMAL if active > 0 else tk.DISABLED)

    # ── History chips ─────────────────────────────────────────────────────────

    def _get_history(self) -> list:
        return load_config().get("contact_history", [])

    def _add_to_history(self, name: str):
        cfg     = load_config()
        history = cfg.get("contact_history", [])
        history = [n for n in history if n.lower() != name.lower()]
        history.insert(0, name)
        cfg["contact_history"] = history[:8]
        save_config(cfg)
        self.root.after(0, self._refresh_history_chips)

    def _refresh_history_chips(self):
        for w in self.history_frame.winfo_children():
            w.destroy()
        history = self._get_history()
        if not history:
            return
        tk.Label(self.history_frame, text="Recent:",
                 font=("Segoe UI", 8), fg=FG_DIMMER, bg=BG
                 ).pack(side=tk.LEFT, padx=(0, 6))
        for name in history:
            tk.Button(
                self.history_frame, text=name,
                font=("Segoe UI", 8), bg=BG2, fg=FG_DIM,
                activebackground=BG3, activeforeground=FG,
                relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
                command=lambda n=name: self._select_from_history(n)
            ).pack(side=tk.LEFT, padx=(0, 4))

    def _select_from_history(self, name: str):
        self.add_var.set(name)
        self.add_entry.focus_set()
        self.add_entry.icursor(tk.END)

    # ── Autocomplete ──────────────────────────────────────────────────────────

    def _on_add_key(self, event=None):
        query = self.add_var.get().strip().lower()
        if not query or not self._google_contacts:
            self._hide_autocomplete()
            return
        matches = [n for n in self._google_contacts if query in n.lower()][:8]
        if matches:
            self._show_autocomplete(matches)
        else:
            self._hide_autocomplete()

    def _show_autocomplete(self, names: list):
        for w in self.autocomplete_frame.winfo_children():
            w.destroy()
        for name in names:
            tk.Button(
                self.autocomplete_frame, text=name,
                font=FONT_SM, bg=BG3, fg=FG, anchor=tk.W,
                activebackground=BLUE, activeforeground="white",
                relief=tk.FLAT, padx=12, pady=4, cursor="hand2",
                command=lambda n=name: self._pick_autocomplete(n)
            ).pack(fill=tk.X)
        if not self.autocomplete_frame.winfo_manager():
            self.autocomplete_frame.pack(fill=tk.X, before=self.history_frame)

    def _hide_autocomplete(self):
        if self.autocomplete_frame.winfo_manager():
            self.autocomplete_frame.pack_forget()

    def _pick_autocomplete(self, name: str):
        self.add_var.set(name)
        self._hide_autocomplete()
        self._add_contact()

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def _start_all(self):
        if not ensure_playwright():
            messagebox.showerror(
                "Missing dependency",
                "Playwright is not installed.\n\nRun setup.bat first, then restart the app.")
            return
        if not self.contacts:
            messagebox.showwarning("No contacts", "Add at least one contact first.")
            return
        started = 0
        for entry in self.contacts:
            if entry.status in ("idle", "stopped", "error", "offline", "not found"):
                self._start_contact(entry)
                started += 1
        if not started:
            self._log("All contacts are already being monitored")
        self._update_count_and_buttons()

    def _stop_all(self):
        for entry in self.contacts:
            entry.stop_event.set()
            if entry.status in ("starting", "monitoring", "online"):
                self._update_contact_status(entry, "stopped")
        self._update_count_and_buttons()
        self._log("Stopped all monitoring")

    def _start_contact(self, entry: ContactEntry):
        entry.stop_event.clear()
        self._update_contact_status(entry, "starting")
        self._log(f"Starting monitor for: {entry.name}")
        t = threading.Thread(target=self._run_monitor, args=(entry,), daemon=True)
        entry.thread = t
        t.start()

    # ── Browser / Playwright ──────────────────────────────────────────────────

    def _browser_alive(self) -> bool:
        try:
            self.main_page.evaluate("1")
            return True
        except Exception:
            return False

    def _ensure_browser(self, entry: ContactEntry) -> bool:
        """Open browser and wait for WhatsApp Web. Thread-safe via lock."""
        with self._browser_lock:
            if self._browser_ready and self._browser_alive():
                return True

            from playwright.sync_api import sync_playwright

            self._browser_ready = False
            self.root.after(0, lambda: self._log(
                "Launching browser (first time only — scan QR if prompted)..."))

            session_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "wa_session")
            os.makedirs(session_dir, exist_ok=True)

            if self._pw_ctx is None:
                self._pw_ctx = sync_playwright().start()

            try:
                self.browser = self._pw_ctx.chromium.launch_persistent_context(
                    user_data_dir=session_dir,
                    headless=False,
                    args=["--no-sandbox",
                          "--disable-blink-features=AutomationControlled"],
                    no_viewport=True,
                )
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Browser launch error: {e}"))
                return False

            pages          = self.browser.pages
            self.main_page = pages[0] if pages else self.browser.new_page()

            if "web.whatsapp.com" not in self.main_page.url:
                self.main_page.goto(
                    "https://web.whatsapp.com", wait_until="domcontentloaded")

            self.root.after(0, lambda: self._log(
                "Waiting for WhatsApp Web... (scan QR code if asked)"))
            try:
                self.main_page.wait_for_selector(
                    '[data-testid="chat-list"], #pane-side, '
                    '[data-testid="chat-list-search"], '
                    '[aria-label="Chat list"], div[role="grid"]',
                    timeout=120_000)
            except Exception:
                if entry.stop_event.is_set():
                    return False
                self.root.after(0, lambda: self._log(
                    "ERROR: Timed out waiting for WhatsApp Web"))
                return False

            self._browser_ready = True
            self.root.after(0, lambda: self._log(
                "WhatsApp Web ready ✓ (browser minimized)"))
            time.sleep(1)
            _minimize_window_containing("WhatsApp")
            return True

    def _get_page_for(self, entry: ContactEntry):
        """Return the existing browser tab for this contact, or open a new one."""
        if entry.page is not None:
            try:
                entry.page.evaluate("1")
                return entry.page
            except Exception:
                entry.page = None

        try:
            p = self.browser.new_page()
            p.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
            p.wait_for_selector(
                '[data-testid="chat-list"], #pane-side, div[role="grid"]',
                timeout=30_000)
            entry.page = p
            return p
        except Exception as e:
            self.root.after(0, lambda: self._log(
                f"Tab error [{entry.name}]: {e}"))
            return None

    def _run_monitor(self, entry: ContactEntry):
        try:
            if not self._ensure_browser(entry):
                self.root.after(0, lambda: self._update_contact_status(entry, "error"))
                return
            if entry.stop_event.is_set():
                return

            page = self._get_page_for(entry)
            if page is None:
                self.root.after(0, lambda: self._update_contact_status(entry, "error"))
                return

            nm = entry.name
            self.root.after(0, lambda: self._log(f"Searching for {nm}..."))

            if not self._open_chat(page, nm):
                self.root.after(0, lambda: self._log(f"Not found: {nm} — check the name"))
                self.root.after(0, lambda: self._update_contact_status(entry, "not found"))
                return

            self.root.after(0, lambda: self._log(f"Monitoring {nm}"))
            self.root.after(0, lambda: self._update_contact_status(entry, "monitoring"))

            was_online = False
            while not entry.stop_event.is_set():
                try:
                    is_online = self._is_contact_online(page)
                except Exception:
                    is_online = False

                if is_online and not was_online:
                    was_online = True
                    self.root.after(0, lambda: self._update_contact_status(entry, "online"))
                    self.root.after(0, lambda n=nm: self._log(f"🟢 {n} is now online!"))
                    self._notify(nm)

                elif not is_online and was_online:
                    was_online = False
                    self.root.after(0, lambda: self._update_contact_status(entry, "monitoring"))
                    self.root.after(0, lambda n=nm: self._log(f"⚫ {n} went offline"))

                entry.stop_event.wait(timeout=3)

        except Exception as exc:
            msg = str(exc)
            self.root.after(0, lambda: self._log(f"ERROR [{entry.name}]: {msg}"))
            self.root.after(0, lambda: self._update_contact_status(entry, "error"))

    # ── WhatsApp Web helpers ──────────────────────────────────────────────────

    def _dismiss_restore_dialog(self, page):
        try:
            btn = page.query_selector(
                'button:has-text("No thanks"), button:has-text("No"), '
                '.modal button, [aria-label*="close" i]')
            if btn:
                btn.click()
                time.sleep(0.5)
        except Exception:
            pass
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    _JS_CLICK = """(name) => {
        const lower = name.toLowerCase();
        for (const s of document.querySelectorAll('span[title]')) {
            const t = (s.getAttribute('title') || '').trim().toLowerCase();
            if (t === lower || t.includes(lower)) {
                let node = s.parentElement;
                for (let i = 0; i < 10; i++) {
                    if (!node) break;
                    const r = node.getAttribute('role');
                    const d = node.getAttribute('data-testid') || '';
                    if (r === 'listitem' || d.includes('cell') || d.includes('list-item')) {
                        node.click(); return true;
                    }
                    const rect = node.getBoundingClientRect();
                    if (rect.width > 150 && rect.height > 40 && rect.height < 110) {
                        node.click(); return true;
                    }
                    node = node.parentElement;
                }
            }
        }
        return false;
    }"""

    def _open_chat(self, page, name: str) -> bool:
        self._dismiss_restore_dialog(page)

        # Strategy 1: find span[title] matching the name
        try:
            if page.evaluate(self._JS_CLICK, name):
                time.sleep(1.5)
                return True
        except Exception:
            pass

        # Strategy 2: use the search box
        try:
            search = page.wait_for_selector(
                '[data-testid="chat-list-search"], '
                'div[contenteditable="true"][data-tab="3"], '
                'div[contenteditable="true"][aria-label*="Search"], '
                '[title="Search input textbox"]',
                timeout=6_000)
            search.click()
            time.sleep(0.4)
            page.keyboard.press("Control+a")
            page.keyboard.type(name, delay=80)
            time.sleep(3)
            if page.evaluate(self._JS_CLICK, name):
                time.sleep(1.5)
                return True
        except Exception:
            pass

        return False

    def _is_contact_online(self, page) -> bool:
        try:
            return bool(page.evaluate("""() => {
                const main = document.querySelector('#main');
                if (!main) return false;
                const header = main.querySelector('header');
                if (!header) return false;
                for (const s of header.querySelectorAll('span')) {
                    if ((s.textContent || '').trim().toLowerCase() === 'online') return true;
                }
                return false;
            }"""))
        except Exception:
            return False

    # ── Notifications ─────────────────────────────────────────────────────────

    def _notify(self, name: str):
        self.root.after(0, self.root.lift)
        self.root.after(0, self.root.focus_force)

        try:
            import winsound
            winsound.PlaySound("SystemNotification",
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                import winsound
                winsound.Beep(1000, 400)
            except Exception:
                pass

        self._windows_notify("WhatsApp Monitor", f"{name} is now online!")

        token   = self.tg_token_var.get().strip()
        chat_id = self.tg_chatid_var.get().strip()
        if token and chat_id:
            if not chat_id.lstrip('-').isdigit():
                self.root.after(0, lambda: self._log(
                    "✗ Telegram: Chat ID must be a number — open ⚙ Settings → Auto-detect my ID"))
                return
            threading.Thread(
                target=self._send_telegram,
                args=(token, chat_id,
                      f"📱 *WhatsApp Monitor*\n\n🟢 *{name}* is now online!"),
                daemon=True).start()

    def _windows_notify(self, title: str, message: str):
        ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.BalloonTipTitle = '{title}'
$n.BalloonTipText  = '{message}'
$n.BalloonTipIcon  = [System.Windows.Forms.ToolTipIcon]::Info
$n.ShowBalloonTip(8000)
Start-Sleep -Seconds 9
$n.Dispose()
"""
        try:
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden",
                 "-NonInteractive", "-Command", ps],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _send_telegram(self, token: str, chat_id: str, text: str, callback=None):
        try:
            url     = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = urllib.parse.urlencode({
                "chat_id": chat_id, "text": text, "parse_mode": "Markdown"
            }).encode()
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
            ok  = result.get("ok", False)
            msg = ("Telegram message sent" if ok
                   else f"Telegram error: {result.get('description', 'unknown')}")
            if callback:
                self.root.after(0, lambda: callback(ok, msg))
            else:
                self.root.after(0, lambda: self._log(msg))
        except urllib.request.HTTPError as e:
            try:
                desc = json.loads(e.read()).get("description", str(e))
            except Exception:
                desc = str(e)
            msg = f"Telegram error: {desc}"
            if callback:
                self.root.after(0, lambda: callback(False, msg))
            else:
                self.root.after(0, lambda: self._log(msg))
        except Exception as exc:
            msg = f"Telegram error: {exc}"
            if callback:
                self.root.after(0, lambda: callback(False, msg))
            else:
                self.root.after(0, lambda: self._log(msg))

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_widget.see(tk.END)
        self.log_widget.config(state=tk.DISABLED)

    # ── Quick Telegram test ───────────────────────────────────────────────────

    def _quick_test_telegram(self):
        token   = self.tg_token_var.get().strip()
        chat_id = self.tg_chatid_var.get().strip()
        if not token or not chat_id:
            self._log("No Telegram configured — open ⚙ Settings first")
            return
        if not chat_id.lstrip('-').isdigit():
            self._log("✗ Chat ID must be a number — open ⚙ Settings → Auto-detect my ID")
            return
        self.tg_quick_test_btn.config(state=tk.DISABLED, text="Sending...")
        self._log("Sending Telegram test message...")

        def on_done(ok: bool, msg: str):
            self.tg_quick_test_btn.config(state=tk.NORMAL, text="✈ Test")
            self._log(("✓ " if ok else "✗ ") + msg)

        threading.Thread(
            target=self._send_telegram,
            args=(token, chat_id,
                  "✅ *WhatsApp Monitor* - Test message. Notifications are working!"),
            kwargs={"callback": on_done}, daemon=True).start()

    def _refresh_tg_badge(self):
        if self.tg_token_var.get().strip() and self.tg_chatid_var.get().strip():
            self.tg_badge.config(text="✈  Telegram notifications enabled", fg=BLUE_H)
            self.tg_quick_test_btn.config(state=tk.NORMAL)
        else:
            self.tg_badge.config(
                text="⚙  Configure Telegram in Settings (optional)", fg=FG_DIMMER)
            self.tg_quick_test_btn.config(state=tk.DISABLED)

    # ── Settings page ─────────────────────────────────────────────────────────

    def _build_settings_page(self):
        self.page_settings = tk.Frame(self.root, bg=BG, padx=20, pady=14)

        # ── Google Contacts card ──────────────────────────────────────────────
        gc_card = tk.Frame(self.page_settings, bg=BG2, padx=18, pady=14)
        gc_card.pack(fill=tk.X, pady=(0, 12))

        gc_title = tk.Frame(gc_card, bg=BG2)
        gc_title.pack(fill=tk.X, pady=(0, 6))
        tk.Label(gc_title, text="👤  Google Contacts",
                 font=("Segoe UI", 12, "bold"), fg=FG, bg=BG2).pack(side=tk.LEFT)
        self.gc_count_lbl = tk.Label(
            gc_title, text="Not imported", font=FONT_SM, fg=FG_DIM, bg=BG2)
        self.gc_count_lbl.pack(side=tk.RIGHT)

        tk.Label(
            gc_card,
            text="Import your contacts for autocomplete when adding names.\n"
                 "Export from contacts.google.com  →  Export  →  vCard (.vcf)",
            font=FONT_SM, fg=FG_DIM, bg=BG2, wraplength=400, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 10))

        gc_btns = tk.Frame(gc_card, bg=BG2)
        gc_btns.pack(fill=tk.X)
        tk.Button(
            gc_btns, text="📂  Import vCard (.vcf)",
            font=FONT_B, bg=BLUE, fg="white",
            activebackground=BLUE_H, activeforeground="white",
            relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
            command=self._import_vcf
        ).pack(side=tk.LEFT)
        tk.Button(
            gc_btns, text="Clear",
            font=FONT_SM, bg=BG3, fg=FG_DIM,
            activebackground=BG3, activeforeground=RED_H,
            relief=tk.FLAT, padx=10, pady=8, cursor="hand2",
            command=self._clear_google_contacts
        ).pack(side=tk.LEFT, padx=(8, 0))

        # ── Telegram card ─────────────────────────────────────────────────────
        tg_card = tk.Frame(self.page_settings, bg=BG2, padx=18, pady=16)
        tg_card.pack(fill=tk.X, pady=(0, 12))

        tr = tk.Frame(tg_card, bg=BG2)
        tr.pack(fill=tk.X, pady=(0, 10))
        tk.Label(tr, text="✈  Telegram Bot",
                 font=("Segoe UI", 12, "bold"), fg=FG, bg=BG2).pack(side=tk.LEFT)
        self.tg_status_dot = tk.Label(
            tr, text="●", font=("Segoe UI", 12), fg=FG_DIMMER, bg=BG2)
        self.tg_status_dot.pack(side=tk.RIGHT)
        self.tg_status_lbl = tk.Label(
            tr, text="Not configured", font=FONT_SM, fg=FG_DIM, bg=BG2)
        self.tg_status_lbl.pack(side=tk.RIGHT, padx=(0, 6))

        tk.Label(
            tg_card,
            text="Send a Telegram message when any monitored contact comes online.",
            font=FONT_SM, fg=FG_DIM, bg=BG2, wraplength=380, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(0, 12))

        # Token
        tk.Label(tg_card, text="Bot Token",
                 font=FONT_B, fg=FG_DIM, bg=BG2).pack(anchor=tk.W)
        tk.Label(tg_card, text="Create a bot via @BotFather on Telegram",
                 font=("Segoe UI", 8), fg=FG_DIMMER, bg=BG2).pack(anchor=tk.W, pady=(0, 4))

        token_outer = tk.Frame(tg_card, bg=BG3, pady=2, padx=2)
        token_outer.pack(fill=tk.X, pady=(0, 10))
        token_inner = tk.Frame(token_outer, bg=BG3)
        token_inner.pack(fill=tk.X)

        self.tg_token_entry = tk.Entry(
            token_inner, textvariable=self.tg_token_var,
            font=FONT, bg=BG3, fg="white",
            insertbackground="white", relief=tk.FLAT, bd=6, show="*")
        self.tg_token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7)

        self._token_visible = False
        tk.Button(
            token_inner, text="👁", font=("Segoe UI", 11),
            bg=BG3, fg=FG_DIM, activebackground=BG3,
            relief=tk.FLAT, cursor="hand2", bd=0, padx=6,
            command=self._toggle_token_visibility
        ).pack(side=tk.RIGHT, ipady=7)

        # Chat ID row
        chat_row = tk.Frame(tg_card, bg=BG2)
        chat_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(chat_row, text="Chat ID",
                 font=FONT_B, fg=FG_DIM, bg=BG2).pack(side=tk.LEFT)
        self.get_chatid_btn = tk.Button(
            chat_row, text="Auto-detect my ID",
            font=("Segoe UI", 8), bg=BLUE, fg="white",
            activebackground=BLUE_H, activeforeground="white",
            relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
            command=self._auto_detect_chat_id)
        self.get_chatid_btn.pack(side=tk.RIGHT)

        tk.Label(
            tg_card,
            text="Must be a number. First send any message to your bot, then click Auto-detect.",
            font=("Segoe UI", 8), fg=FG_DIMMER, bg=BG2
        ).pack(anchor=tk.W, pady=(0, 4))

        chatid_outer = tk.Frame(tg_card, bg=BG3, pady=2, padx=2)
        chatid_outer.pack(fill=tk.X, pady=(0, 14))
        self.tg_chatid_entry = tk.Entry(
            chatid_outer, textvariable=self.tg_chatid_var,
            font=FONT, bg=BG3, fg="white",
            insertbackground="white", relief=tk.FLAT, bd=6)
        self.tg_chatid_entry.pack(fill=tk.X, ipady=7)

        # Buttons
        btns = tk.Frame(tg_card, bg=BG2)
        btns.pack(fill=tk.X)
        self.tg_test_btn = tk.Button(
            btns, text="Send test message",
            font=FONT_B, bg=BLUE, fg="white",
            activebackground=BLUE_H, activeforeground="white",
            relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
            command=self._test_telegram)
        self.tg_test_btn.pack(side=tk.LEFT)
        tk.Button(
            btns, text="Save",
            font=FONT_B, bg=GREEN, fg="white",
            activebackground=GREEN_H, activeforeground="white",
            relief=tk.FLAT, padx=24, pady=8, cursor="hand2",
            command=self._save_and_back
        ).pack(side=tk.RIGHT)

        self.settings_result = tk.Label(
            self.page_settings, text="", font=FONT_SM,
            fg=LIME, bg=BG, anchor=tk.W, wraplength=440)
        self.settings_result.pack(anchor=tk.W, pady=(6, 0))

        self._refresh_gc_count()

    # ── Google Contacts ───────────────────────────────────────────────────────

    def _import_vcf(self):
        path = filedialog.askopenfilename(
            title="Select vCard export from Google Contacts",
            filetypes=[("vCard files", "*.vcf"), ("All files", "*.*")])
        if not path:
            return
        names = parse_vcf(path)
        if not names:
            self.settings_result.config(
                text="✗ No contacts found. Make sure it's a valid .vcf (vCard) file.",
                fg=RED_H)
            return
        self._google_contacts = names
        cfg = load_config()
        cfg["google_contacts"] = names
        save_config(cfg)
        self._refresh_gc_count()
        self.settings_result.config(
            text=f"✓ Imported {len(names)} contacts — autocomplete is now active",
            fg=LIME)

    def _clear_google_contacts(self):
        self._google_contacts = []
        cfg = load_config()
        cfg["google_contacts"] = []
        save_config(cfg)
        self._refresh_gc_count()
        self.settings_result.config(text="Contacts cleared", fg=FG_DIM)

    def _refresh_gc_count(self):
        n = len(self._google_contacts)
        if n == 0:
            self.gc_count_lbl.config(text="Not imported", fg=FG_DIM)
        else:
            self.gc_count_lbl.config(text=f"{n} contacts ✓", fg=LIME)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _show_page(self, name: str):
        self.page_monitor.pack_forget()
        self.page_settings.pack_forget()
        if name == "monitor":
            self.page_monitor.pack(fill=tk.BOTH, expand=True)
            self.nav_btn.config(text="⚙", font=("Segoe UI", 16),
                                command=self._go_settings)
            self.header_sub.config(
                text="Get notified when contacts come online")
            self._refresh_tg_badge()
            self._refresh_history_chips()
        else:
            self.page_settings.pack(fill=tk.BOTH, expand=True)
            self.nav_btn.config(text="← Back", font=("Segoe UI", 11),
                                command=self._go_monitor)
            self.header_sub.config(text="Settings")
            self._refresh_tg_status_dot()
            self._refresh_gc_count()

    def _go_settings(self): self._show_page("settings")
    def _go_monitor(self):  self._show_page("monitor")

    def _toggle_token_visibility(self):
        self._token_visible = not self._token_visible
        self.tg_token_entry.config(show="" if self._token_visible else "*")

    def _refresh_tg_status_dot(self):
        if self.tg_token_var.get().strip() and self.tg_chatid_var.get().strip():
            self.tg_status_dot.config(fg=LIME)
            self.tg_status_lbl.config(text="Configured", fg=LIME)
        else:
            self.tg_status_dot.config(fg=FG_DIMMER)
            self.tg_status_lbl.config(text="Not configured", fg=FG_DIM)

    # ── Settings actions ──────────────────────────────────────────────────────

    def _save_and_back(self):
        cfg = load_config()
        cfg["tg_token"]   = self.tg_token_var.get().strip()
        cfg["tg_chat_id"] = self.tg_chatid_var.get().strip()
        save_config(cfg)
        self._go_monitor()

    def _test_telegram(self):
        token   = self.tg_token_var.get().strip()
        chat_id = self.tg_chatid_var.get().strip()
        if not token or not chat_id:
            self.settings_result.config(
                text="Fill in both Bot Token and Chat ID first.", fg=RED_H)
            return
        self.tg_test_btn.config(state=tk.DISABLED, text="Sending...")
        self.settings_result.config(text="", fg=LIME)

        def on_done(ok: bool, msg: str):
            self.tg_test_btn.config(state=tk.NORMAL, text="Send test message")
            self.settings_result.config(
                text=("✓ " if ok else "✗ ") + msg,
                fg=LIME if ok else RED_H)
            self._refresh_tg_status_dot()

        threading.Thread(
            target=self._send_telegram,
            args=(token, chat_id,
                  "✅ *WhatsApp Monitor* - Test message. Notifications are working!"),
            kwargs={"callback": on_done}, daemon=True).start()

    def _auto_detect_chat_id(self):
        token = self.tg_token_var.get().strip()
        if not token:
            self.settings_result.config(
                text="Enter your Bot Token first, then send a message to your bot and click Auto-detect.",
                fg=RED_H)
            return
        self.get_chatid_btn.config(state=tk.DISABLED, text="Detecting...")
        self.settings_result.config(
            text="Make sure you sent a message to your bot first...", fg=YELLOW)

        def detect():
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                with urllib.request.urlopen(
                        urllib.request.Request(url), timeout=10) as resp:
                    result = json.loads(resp.read())
                if not result.get("ok"):
                    raise Exception(result.get("description", "API error"))
                updates = result.get("result", [])
                if not updates:
                    raise Exception(
                        "No messages found. Send any message to your bot first, then try again.")
                last    = updates[-1]
                msg     = last.get("message") or last.get("channel_post") or {}
                chat    = msg.get("chat", {})
                chat_id = str(chat.get("id", ""))
                name    = chat.get("first_name") or chat.get("title") or "Unknown"
                if not chat_id:
                    raise Exception("Could not extract chat ID from updates.")

                def apply():
                    self.tg_chatid_var.set(chat_id)
                    self.get_chatid_btn.config(state=tk.NORMAL, text="Auto-detect my ID")
                    self.settings_result.config(
                        text=f"✓ Found Chat ID: {chat_id}  (from: {name})", fg=LIME)
                    self._refresh_tg_status_dot()
                self.root.after(0, apply)

            except Exception as exc:
                def show_err():
                    self.get_chatid_btn.config(state=tk.NORMAL, text="Auto-detect my ID")
                    self.settings_result.config(text=f"✗ {exc}", fg=RED_H)
                self.root.after(0, show_err)

        threading.Thread(target=detect, daemon=True).start()

    # ── On close ──────────────────────────────────────────────────────────────

    def _on_close(self):
        for entry in self.contacts:
            entry.stop_event.set()
        cfg = load_config()
        cfg["tg_token"]   = self.tg_token_var.get().strip()
        cfg["tg_chat_id"] = self.tg_chatid_var.get().strip()
        save_config(cfg)
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self._pw_ctx:
                self._pw_ctx.stop()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = WhatsAppMonitor()
    app.run()
