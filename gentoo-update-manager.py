#!/usr/bin/env python3
"""
Gentoo Update Manager - a friendly, mouse-aware terminal app for keeping
Gentoo Linux up to date. Python 3 stdlib only (curses), no pip needed.

  * Click tabs, buttons, checkboxes and rows - or use the keyboard
  * Plain-language dialogs explain what will happen before anything runs
  * Check for updates, pick which to install, hold packages back
  * Browse installed software, remove it safely, or reinstall it
  * Details panel describes the highlighted package

Run:  python3 gentoo-update-manager.py      (as root, or with sudo/doas installed)
Config / hold list: ~/.config/gentoo-update-manager/config.json
"""
import curses
import json
import locale
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from curses.textpad import rectangle
from email.utils import parsedate_to_datetime
from pathlib import Path

APP = "Gentoo Update Manager"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gentoo-update-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_DIR = Path(os.environ.get("GUM_DB", "/var/db/pkg"))
WORLD_FILE = Path(os.environ.get("GUM_WORLD", "/var/lib/portage/world"))
TREE_STAMPS = ["/var/db/repos/gentoo/metadata/timestamp.chk", "/var/db/repos/gentoo/metadata/timestamp"]

DEFAULT_CONFIG = {
    "ignored": [],  # "cat/pn" = hold all versions, "=cat/pn-ver" = hold that version only
    "emerge_opts": ["--ask", "--verbose"],
    "update_args": ["--update", "--deep", "--newuse", "--with-bdeps=y", "@world"],
    "welcomed": False,
}

VER_RE = re.compile(
    r"^(?P<cpn>.+?)-(?P<ver>\d+(?:\.\d+)*[a-z]?(?:_(?:alpha|beta|pre|rc|p)\d*)*(?:-r\d+)?)$"
)
LINE_RE = re.compile(
    r"^\[(?P<kind>ebuild|binary)\s+(?P<flags>[^\]]*?)\s*\]\s+(?P<atom>\S+)(?:\s+\[(?P<old>[^\]]+)\])?"
)

LEFT = curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED
WHEEL_UP = getattr(curses, "BUTTON4_PRESSED", 0x10000)
WHEEL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0x200000)

TIPS = [
    "Tip: click a [ ] box or press Space to tick an update, then press I to install.",
    "Tip: not ready for an update? Press H to hold that package back.",
    "Tip: type / to search. Esc clears the search.",
    "Tip: nothing changes on your system until you approve it in Portage's own prompt.",
    "Tip: press F1 for help, or click Menu (top left) for more tools.",
]

HELP = """\
GETTING STARTED

  1. Click "Check for updates" (or press C) to see what's available.
  2. Tick the updates you want. Space or a click on the [ ] box ticks one,
     A ticks everything that isn't held back.
  3. Click "Install selected" (or press I). You'll get a short explanation,
     then Portage (Gentoo's package manager) shows its plan and asks you to
     confirm. Type Y and Enter to go ahead, or N to cancel.
  4. Press Enter afterwards to come back here. The list refreshes itself.

THE THREE TABS

  Updates            what can be upgraded, and what each change means
  Installed software everything on your system. "Yours" = you asked for it,
                     "Auto" = installed to support something else.
                     Remove or reinstall packages here.
  Held back          packages this tool will skip when installing updates

HOLDING PACKAGES BACK

  Press H on an update. Choose "All versions" to ignore the package, or
  "Only this version" to skip just that release (newer ones show up again).
  Press H again on a held package to release it.
  Note: holds only apply inside this tool. For a permanent block outside it,
  add the package to /etc/portage/package.mask.

REMOVING AND REINSTALLING

  Remove (R)   "Remove safely" refuses if other software still needs the
               package. "Force remove" ignores that and can break things.
  Reinstall (I) rebuilds the same version. Handy for a broken program.

MOUSE

  Click tabs, buttons, rows and [ ] boxes. Scroll wheel moves the list.
  Click the search box (or press /) to filter.

KEYBOARD

  1 2 3 / Tab   switch tabs        Up/Down, PgUp/PgDn, Home/End   move
  Space         tick / untick      /  search      Esc  clear search
  A / N         select all / none  M or F10  menu    F1 or ?  this help
  Q             quit

MENU EXTRAS

  Download the latest package list (sync), clean up unused software,
  fix programs broken by updates, review config file changes,
  and show the raw technical output of the last update check.
"""


# ----------------------------------------------------------------- data ----
class Pkg:
    def __init__(self, cpn, ver, slot="", repo="", flags="", old=""):
        self.cpn, self.ver, self.slot, self.repo = cpn, ver, slot, repo
        self.flags, self.old = flags, old
        self.in_world = False

    @property
    def cpv(self):
        return f"{self.cpn}-{self.ver}"

    @property
    def key(self):
        return f"{self.cpv}:{self.slot}"

    @property
    def atom(self):
        return f"={self.cpv}" + (f":{self.slot}" if self.slot else "")

    @property
    def kind(self):
        f = self.flags
        if "D" in f:
            return "Downgrade"
        if "N" in f and "S" in f:
            return "New slot"
        if "N" in f:
            return "New"
        if "U" in f:
            return "Upgrade"
        if "R" in f:
            return "Rebuild"
        if "r" in f:
            return "Reinstall"
        return "Change"


def split_atom(atom):
    atom, _, repo = atom.partition("::")
    atom, _, slot = atom.partition(":")
    m = VER_RE.match(atom)
    if not m:
        return atom, "", slot, repo
    return m.group("cpn"), m.group("ver"), slot, repo


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
        return True
    except OSError:
        return False


def read_world():
    world = set()
    try:
        for line in WORLD_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("@"):
                world.add(re.sub(r"^[<>=~!]+", "", line).split(":")[0])
    except OSError:
        pass
    return world


def scan_installed():
    pkgs, world = [], read_world()
    if not DB_DIR.is_dir():
        return pkgs
    for cat in sorted(DB_DIR.iterdir()):
        if not cat.is_dir():
            continue
        for pdir in sorted(cat.iterdir()):
            if not pdir.is_dir():
                continue
            cpn, ver, _, _ = split_atom(f"{cat.name}/{pdir.name}")

            def rd(name):
                try:
                    return (pdir / name).read_text().strip()
                except OSError:
                    return ""

            p = Pkg(cpn, ver, rd("SLOT").split("/")[0], rd("repository"))
            p.in_world = cpn in world
            pkgs.append(p)
    return pkgs


def parse_pretend(output):
    pkgs = []
    for line in output.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        cpn, ver, slot, repo = split_atom(m.group("atom"))
        if not ver:
            continue
        old = ", ".join(re.sub(r"::\S+", "", o.strip()) for o in (m.group("old") or "").split(","))
        pkgs.append(Pkg(cpn, ver, slot, repo, m.group("flags").strip(), old.strip(", ")))
    return pkgs


def sync_age():
    for path in TREE_STAMPS:
        try:
            ts = os.stat(path).st_mtime
        except OSError:
            continue
        try:
            ts = parsedate_to_datetime(Path(path).read_text().splitlines()[0]).timestamp()
        except Exception:
            pass
        days = int((time.time() - ts) // 86400)
        if days <= 0:
            return "Package list synced today", 0
        if days == 1:
            return "Package list synced yesterday", 1
        return f"Package list synced {days} days ago", days
    return "Package list sync date unknown", None


# ------------------------------------------------------------------ app ----
class App:
    def __init__(self, scr):
        self.scr = scr
        self.cfg = load_config()
        self.tab = 0
        self.updates, self.installed, self.inst_idx = [], [], {}
        self.checked = False
        self.raw = ""
        self.search, self.searching = "", False
        self.hide_held = False
        self.yours_only = False
        self.cursor, self.top = [0, 0, 0], [0, 0, 0]
        self.sel = [set(), set(), set()]
        self.msg = ""
        self.hits = []
        self.info_cache = {}
        self.want_quit = False
        self.tip = 0
        self.sync_text, self.sync_days = sync_age()
        self.reload_installed()
        self.init_ui()

    # ---------------------------------------------------------- setup ----
    def init_ui(self):
        curses.curs_set(0)
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        P = curses.color_pair
        W, B, K = curses.COLOR_WHITE, curses.COLOR_BLUE, curses.COLOR_BLACK
        pairs = [
            (1, curses.COLOR_GREEN, bg), (2, curses.COLOR_YELLOW, bg), (3, curses.COLOR_RED, bg),
            (4, curses.COLOR_CYAN, bg), (5, W, B), (6, K, W), (7, K, curses.COLOR_CYAN),
            (8, K, curses.COLOR_GREEN), (9, W, curses.COLOR_RED),
        ]
        for i, f, b in pairs:
            curses.init_pair(i, f, b)
        self.A = {
            "green": P(1), "yellow": P(2), "red": P(3), "cyan": P(4),
            "title": P(5), "tab_on": P(6) | curses.A_BOLD, "tab_off": P(5),
            "btn": P(7), "btn_ok": P(8), "btn_bad": P(9), "field": P(6),
            "dim": curses.A_DIM, "warn": P(2) | curses.A_BOLD,
        }
        curses.mousemask(curses.ALL_MOUSE_EVENTS)
        curses.mouseinterval(0)

    def put(self, y, x, s, attr=0):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w - 1:
            return
        try:
            self.scr.addstr(y, x, s[: w - x - 1], attr)
        except curses.error:
            pass

    def mouse(self):
        try:
            _, x, y, _, b = curses.getmouse()
            return b, x, y
        except curses.error:
            return None

    # ------------------------------------------------------- data ops ----
    def reload_installed(self):
        self.installed = scan_installed()
        self.inst_idx = {}
        for p in self.installed:
            self.inst_idx.setdefault(p.cpn, []).append(p)
        self.sel[1].clear()

    def is_held(self, p):
        return p.cpn in self.cfg["ignored"] or f"={p.cpv}" in self.cfg["ignored"]

    def pkg_info(self, cpn, slot=""):
        cands = self.inst_idx.get(cpn, [])
        pick = next((p for p in cands if p.slot == slot), None) or (cands[0] if cands else None)
        if not pick:
            return None
        d = DB_DIR / pick.cpv
        if str(d) not in self.info_cache:
            def rd(n):
                try:
                    return (d / n).read_text().strip().replace("\n", " ")[:400]
                except OSError:
                    return ""
            self.info_cache[str(d)] = {"desc": rd("DESCRIPTION"), "home": rd("HOMEPAGE")}
        return self.info_cache[str(d)]

    def rows(self):
        s = self.search.lower()
        if self.tab == 0:
            out = [p for p in self.updates if s in p.cpv.lower()]
            return [p for p in out if not self.is_held(p)] if self.hide_held else out
        if self.tab == 1:
            out = [p for p in self.installed if s in p.cpn.lower()]
            return [p for p in out if p.in_world] if self.yours_only else out
        return [e for e in self.cfg["ignored"] if s in e.lower()]

    def current(self):
        r = self.rows()
        c = self.cursor[self.tab]
        return r[c] if 0 <= c < len(r) else None

    # ------------------------------------------------------- drawing -----
    def buttons(self):
        t = self.tab
        if t == 0:
            return [
                ("&Check for updates", "c", self.check_updates, "n"),
                ("Select &all", "a", self.select_all, "n"),
                ("Select &none", "n", self.select_none, "n"),
                ("&Install selected", "i", self.install_updates, "p"),
                ("&Hold back / release", "h", self.hold_dialog, "n"),
                ("&Menu", "m", self.main_menu, "n"),
            ]
        if t == 1:
            return [
                ("&Remove", "r", self.remove_dialog, "d"),
                ("Re&install", "i", self.reinstall_dialog, "n"),
                ("Only &yours: " + ("on" if self.yours_only else "off"), "y", self.toggle_yours, "n"),
                ("Select &none", "n", self.select_none, "n"),
                ("&Menu", "m", self.main_menu, "n"),
            ]
        return [
            ("&Add rule", "a", self.add_rule, "n"),
            ("&Release", "r", self.release_rule, "p"),
            ("&Menu", "m", self.main_menu, "n"),
        ]

    def draw(self):
        scr, A = self.scr, self.A
        scr.erase()
        h, w = scr.getmaxyx()
        self.hits = []
        if h < 16 or w < 64:
            self.put(0, 0, "Please make this window bigger (at least 64x16).", A["warn"])
            return
        # title bar
        self.put(0, 0, " " * (w - 1), A["title"])
        self.put(0, 1, " Menu ", A["btn"] | curses.A_BOLD)
        self.hits.append((0, 1, 6, "menu", None))
        self.put(0, 9, APP, A["title"] | curses.A_BOLD)
        st = f" {self.sync_text} "
        if w - len(st) - 2 > 32:
            stale = self.sync_days is not None and self.sync_days >= 7
            self.put(0, w - len(st) - 2, st, A["title"] | (curses.A_BOLD if stale else 0))
        # tabs
        labels = [
            f" 1 Updates{f' ({len(self.updates)})' if self.checked else ''} ",
            f" 2 Installed software ({len(self.installed)}) ",
            f" 3 Held back ({len(self.cfg['ignored'])}) ",
        ]
        x = 1
        for i, lab in enumerate(labels):
            self.put(1, x, lab, A["tab_on"] if i == self.tab else A["tab_off"])
            self.hits.append((1, x, len(lab), "tab", i))
            x += len(lab) + 1
        # summary + search box
        rows = self.rows()
        self.put(2, 1, self.summary(rows), A["cyan"])
        sw = max(14, min(26, w // 3))
        sx = w - sw - 11
        self.put(2, sx, "Search: ", curses.A_BOLD)
        txt = self.search + ("_" if self.searching else "")
        shown = txt if txt else "click or press /"
        fa = A["field"] if (txt or self.searching) else A["field"] | curses.A_DIM
        self.put(2, sx + 8, shown[-sw:].ljust(sw), fa)
        self.hits.append((2, sx, sw + 8, "search", None))

        det = h >= 24
        list_top = 4
        list_bot = h - 9 if det else h - 4
        list_h = max(1, list_bot - list_top + 1)
        namew = max(18, min(40, w - 52))
        self.put(3, 0, self.header(namew).ljust(w - 1), curses.A_BOLD | curses.A_UNDERLINE)

        t = self.tab
        self.cursor[t] = max(0, min(self.cursor[t], len(rows) - 1))
        if self.cursor[t] < self.top[t]:
            self.top[t] = self.cursor[t]
        if self.cursor[t] >= self.top[t] + list_h:
            self.top[t] = self.cursor[t] - list_h + 1
        for i in range(list_h):
            idx = self.top[t] + i
            if idx >= len(rows):
                break
            y = list_top + i
            segs = self.row_segments(rows[idx], namew)
            cur = idx == self.cursor[t]
            x = 0
            for text, attr in segs:
                self.put(y, x, text, attr | (curses.A_REVERSE if cur else 0))
                x += len(text)
            if cur and x < w - 1:
                self.put(y, x, " " * (w - 1 - x), curses.A_REVERSE)
            self.hits.append((y, 0, w - 1, "row", idx))
        if not rows:
            self.empty_state(list_top, list_h, w)
        # scrollbar hint
        if len(rows) > list_h:
            self.put(list_top, w - 2, "^", A["dim"])
            self.put(list_bot, w - 2, "v", A["dim"])

        if det:
            self.put(h - 8, 0, ("-- Details " + "-" * w)[: w - 1], A["dim"])
            for i, (text, attr) in enumerate(self.detail_lines(w - 4)):
                self.put(h - 7 + i, 2, text, attr)
        self.draw_buttons(h - 3, w)
        status = self.msg or TIPS[self.tip % len(TIPS)]
        self.put(h - 1, 1, status, A["warn"] if self.msg else A["dim"])
        hint = "F1 Help  Q Quit"
        if w - len(hint) - 2 > len(status) + 3:
            self.put(h - 1, w - len(hint) - 2, hint, A["dim"])

    def summary(self, rows):
        if self.tab == 0:
            if not self.checked:
                return "Not checked yet"
            k = {}
            for p in self.updates:
                k[p.kind] = k.get(p.kind, 0) + 1
            parts = [f"{n} {name.lower()}{'s' if n > 1 and name in ('Upgrade', 'Rebuild', 'Reinstall', 'Downgrade') else ''}"
                     for name, n in k.items()]
            held = sum(self.is_held(p) for p in self.updates)
            s = ", ".join(parts) or "Everything is up to date"
            return f"{s}  |  {len(self.sel[0])} selected" + (f", {held} held back" if held else "")
        if self.tab == 1:
            return f"Showing {len(rows)} of {len(self.installed)} packages  |  {len(self.sel[1])} selected"
        return "This tool skips these packages when installing updates"

    def header(self, namew):
        if self.tab == 0:
            return f"    {'Change':<11}{'Package':<{namew + 1}}{'New version':<15}Installed"
        if self.tab == 1:
            return f"    {'Origin':<8}{'Package':<{namew + 1}}{'Version':<15}Slot / source"
        return "  Rule"

    def row_segments(self, item, namew):
        A = self.A
        if isinstance(item, str):
            scope = "only this version" if item.startswith("=") else "all versions"
            return [("  ", 0), (f"{item:<50.50}", 0), (f"({scope})", A["dim"])]
        if self.tab == 0:
            held = self.is_held(item)
            mark = "[-] " if held else ("[x] " if item.key in self.sel[0] else "[ ] ")
            col = {"Upgrade": A["yellow"], "New": A["green"], "New slot": A["green"],
                   "Rebuild": A["cyan"], "Reinstall": A["cyan"], "Downgrade": A["red"]}.get(item.kind, 0)
            dim = A["dim"] if held else 0
            return [(mark, dim), (f"{item.kind:<11}", dim or col), (f"{item.cpn:<{namew + 1}.{namew}}", dim),
                    (f"{item.ver:<15.15}", dim), (f"was {item.old}" if item.old else "", A["dim"])]
        mark = "[x] " if item.key in self.sel[1] else "[ ] "
        origin = "Yours" if item.in_world else "Auto"
        return [(mark, 0), (f"{origin:<8}", A["green"] if item.in_world else A["dim"]),
                (f"{item.cpn:<{namew + 1}.{namew}}", 0), (f"{item.ver:<15.15}", 0),
                (f":{item.slot} {item.repo}", A["dim"])]

    def empty_state(self, top, height, w):
        if self.tab == 0 and not self.checked:
            lines = ["Nothing checked yet.", "", "Click  [ Check for updates ]  below, or press C."]
        elif self.search:
            lines = [f"No matches for '{self.search}'.", "", "Press Esc to clear the search."]
        elif self.tab == 0:
            lines = ["Your system is up to date.", "", "Nothing to install right now."]
        elif self.tab == 2:
            lines = ["Nothing is held back.", "", "On the Updates tab, press H to hold a package back."]
        else:
            lines = ["No packages found."]
        y = top + max(0, (height - len(lines)) // 2)
        for i, ln in enumerate(lines):
            self.put(y + i, max(1, (w - len(ln)) // 2), ln, self.A["cyan"] if i == 0 else 0)

    def detail_lines(self, width):
        cur, A = self.current(), self.A
        out = []
        if isinstance(cur, str):
            if cur.startswith("="):
                out = [(f"Rule: {cur}", curses.A_BOLD),
                       ("Skips only this exact version. Newer versions will show up in Updates again.", 0)]
            else:
                out = [(f"Rule: {cur}", curses.A_BOLD),
                       ("Skips every version of this package until you release the rule.", 0)]
            out.append(("Release it with the Release button (or R).", A["dim"]))
        elif isinstance(cur, Pkg) and self.tab == 0:
            info = self.pkg_info(cur.cpn, cur.slot)
            head = f"{cur.cpn}  {cur.old + ' -> ' if cur.old else ''}{cur.ver}"
            expl = {
                "Upgrade": "A newer version is available.",
                "New": "New package. Portage adds it because an update or your settings need it.",
                "New slot": "A parallel version is installed next to the existing one.",
                "Rebuild": "Same version, rebuilt because a dependency or your USE flags changed.",
                "Reinstall": "Same version, reinstalled.",
                "Downgrade": "Older than what you have. Check why before installing this.",
            }.get(cur.kind, "Portage wants to change this package.")
            if self.is_held(cur):
                expl = "HELD BACK: skipped by this tool. Press H to release it."
            out = [(head, curses.A_BOLD), (expl, A["yellow"] if self.is_held(cur) else 0)]
            if info and info["desc"]:
                out.append((info["desc"], 0))
            if info and info["home"]:
                out.append((info["home"], A["cyan"]))
            elif not info:
                out.append(("(Description appears here for packages you already have installed.)", A["dim"]))
        elif isinstance(cur, Pkg):
            info = self.pkg_info(cur.cpn, cur.slot) or {"desc": "", "home": ""}
            why = ("You asked for this one (it's in your world file)." if cur.in_world
                   else "Installed automatically to support other software.")
            out = [(f"{cur.cpn}  {cur.ver}", curses.A_BOLD), (why, A["green"] if cur.in_world else A["dim"])]
            if info["desc"]:
                out.append((info["desc"], 0))
            if info["home"]:
                out.append((info["home"], A["cyan"]))
        flat = []
        for text, attr in out:
            for part in textwrap.wrap(text, max(20, width)) or [""]:
                flat.append((part, attr))
        return flat[:4]

    def draw_buttons(self, y0, w):
        A, x, y = self.A, 1, y0
        for lab, _, fn, style in self.buttons():
            text = lab.replace("&", "")
            bw = len(text) + 2
            if x + bw > w - 1:
                x, y = 1, y + 1
            if y > y0 + 1:
                break
            attr = {"n": A["btn"], "p": A["btn_ok"], "d": A["btn_bad"]}[style]
            self.put(y, x, f" {text} ", attr)
            if "&" in lab:
                hk = lab.index("&")
                self.put(y, x + 1 + hk, text[hk], attr | curses.A_UNDERLINE | curses.A_BOLD)
            self.hits.append((y, x, bw, "btn", fn))
            x += bw + 1

    # ------------------------------------------------------- dialogs -----
    def box(self, title, lines, width=68, style="info", buttons=None, sel=0):
        h, w = self.scr.getmaxyx()
        bw = max(30, min(w - 4, width))
        wrapped = []
        for ln in lines:
            attr = 0
            if isinstance(ln, tuple):
                ln, attr = ln
            for part in (textwrap.wrap(ln, bw - 4) if ln else [""]):
                wrapped.append((part, attr))
        bh = min(len(wrapped) + (5 if buttons else 4), h - 2)
        y0, x0 = (h - bh) // 2, (w - bw) // 2
        for y in range(y0, y0 + bh):
            self.put(y, x0, " " * bw)
        border = {"danger": self.A["red"], "warn": self.A["yellow"]}.get(style, self.A["cyan"])
        self.scr.attron(border)
        try:
            rectangle(self.scr, y0, x0, y0 + bh - 1, x0 + bw - 1)
        except curses.error:
            pass
        self.scr.attroff(border)
        self.put(y0, x0 + 2, f" {title} ", curses.A_BOLD | border)
        limit = y0 + bh - (3 if buttons else 2)
        for i, (text, attr) in enumerate(wrapped):
            if y0 + 2 + i >= limit:
                break
            self.put(y0 + 2 + i, x0 + 2, text, attr)
        hits = []
        if buttons:
            labels = [f" {b} " for b in buttons]
            total = sum(len(s) for s in labels) + 2 * (len(labels) - 1)
            x = x0 + max(1, (bw - total) // 2)
            for i, s in enumerate(labels):
                attr = self.A["tab_on"] if i == sel else self.A["btn"]
                self.put(y0 + bh - 2, x, s, attr)
                hits.append((y0 + bh - 2, x, len(s), i))
                x += len(s) + 2
        return hits

    def dialog(self, title, lines, buttons=("OK",), style="info", default=0, width=68):
        sel, n = default, len(buttons)
        while True:
            self.draw()
            hits = self.box(title, lines, width, style, buttons, sel)
            self.scr.refresh()
            k = self.scr.getch()
            if k == curses.KEY_MOUSE:
                m = self.mouse()
                if m and m[0] & LEFT:
                    for (y, x, wd, i) in hits:
                        if y == m[2] and x <= m[1] < x + wd:
                            return i
            elif k in (10, 13, curses.KEY_ENTER):
                return sel
            elif k in (curses.KEY_RIGHT, 9):
                sel = (sel + 1) % n
            elif k in (curses.KEY_LEFT, curses.KEY_BTAB):
                sel = (sel - 1) % n
            elif k == 27:
                return -1
            elif 32 <= k < 127:
                for i, b in enumerate(buttons):
                    if b[:1].lower() == chr(k).lower():
                        return i

    def menu(self, title, items):
        sel = 0
        while True:
            self.draw()
            h, w = self.scr.getmaxyx()
            bw = min(w - 4, max(len(t) for t, _ in items) + 6)
            bh = len(items) + 2
            y0, x0 = max(1, (h - bh) // 2), (w - bw) // 2
            for y in range(y0, y0 + bh):
                self.put(y, x0, " " * bw)
            self.scr.attron(self.A["cyan"])
            try:
                rectangle(self.scr, y0, x0, y0 + bh - 1, x0 + bw - 1)
            except curses.error:
                pass
            self.scr.attroff(self.A["cyan"])
            self.put(y0, x0 + 2, f" {title} ", curses.A_BOLD)
            hits = []
            for i, (label, _) in enumerate(items):
                attr = self.A["tab_on"] if i == sel else 0
                self.put(y0 + 1 + i, x0 + 1, f" {label:<{bw - 4}} ", attr)
                hits.append((y0 + 1 + i, x0 + 1, bw - 2, i))
            self.scr.refresh()
            k = self.scr.getch()
            if k == curses.KEY_MOUSE:
                m = self.mouse()
                if m and m[0] & LEFT:
                    for (y, x, wd, i) in hits:
                        if y == m[2] and x <= m[1] < x + wd:
                            return i
                    return -1
                if m and m[0] & WHEEL_UP:
                    sel = max(0, sel - 1)
                if m and m[0] & WHEEL_DOWN:
                    sel = min(len(items) - 1, sel + 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                sel = (sel + 1) % len(items)
            elif k in (curses.KEY_UP, ord("k")):
                sel = (sel - 1) % len(items)
            elif k in (10, 13, curses.KEY_ENTER):
                return sel
            elif k in (27, ord("q"), curses.KEY_F10, ord("m")):
                return -1

    def ask_text(self, title, lines):
        text = ""
        while True:
            self.draw()
            self.box(title, lines + ["", (f"> {text}_", curses.A_BOLD), "", ("Enter = OK    Esc = cancel", self.A["dim"])])
            self.scr.refresh()
            k = self.scr.getch()
            if k in (10, 13, curses.KEY_ENTER):
                return text.strip()
            if k == 27:
                return None
            if k in (curses.KEY_BACKSPACE, 127, 8):
                text = text[:-1]
            elif 32 <= k < 127:
                text += chr(k)

    def view_text(self, title, text):
        lines, top = text.splitlines() or ["(empty)"], 0
        while True:
            h, w = self.scr.getmaxyx()
            self.scr.erase()
            self.put(0, 0, f" {title} ".ljust(w - 1), self.A["title"] | curses.A_BOLD)
            for i in range(h - 2):
                if top + i < len(lines):
                    self.put(1 + i, 1, lines[top + i])
            self.put(h - 1, 1, "Up/Down, PgUp/PgDn or mouse wheel to scroll  -  Q or Esc to close", self.A["dim"])
            self.scr.refresh()
            k = self.scr.getch()
            if k in (ord("q"), 27, 10, 13):
                return
            if k == curses.KEY_MOUSE:
                m = self.mouse()
                if m and m[0] & WHEEL_UP:
                    top = max(0, top - 3)
                elif m and m[0] & WHEEL_DOWN:
                    top = min(max(0, len(lines) - 1), top + 3)
            elif k in (curses.KEY_DOWN, ord("j")):
                top = min(top + 1, max(0, len(lines) - 1))
            elif k in (curses.KEY_UP, ord("k")):
                top = max(top - 1, 0)
            elif k == curses.KEY_NPAGE:
                top = min(top + h - 3, max(0, len(lines) - 1))
            elif k == curses.KEY_PPAGE:
                top = max(top - h + 3, 0)
            elif k in (curses.KEY_HOME, ord("g")):
                top = 0
            elif k in (curses.KEY_END, ord("G")):
                top = max(0, len(lines) - h + 2)

    def run_busy(self, cmd, title, text, env=None):
        """Run cmd while showing a spinner. Esc cancels. Returns (rc, out, err) or None."""
        out, err = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        try:
            proc = subprocess.Popen(cmd, stdout=out, stderr=err, env=env, stdin=subprocess.DEVNULL)
        except OSError as e:
            self.msg = f"Couldn't start {cmd[0]}: {e}"
            return None
        t0, i, cancelled = time.time(), 0, False
        self.scr.timeout(120)
        while proc.poll() is None:
            self.draw()
            self.box(title, [text, "", f"  {'|/-\\'[i % 4]}  working... {int(time.time() - t0)}s", "",
                             ("Esc = cancel", self.A["dim"])], width=60)
            self.scr.refresh()
            k = self.scr.getch()
            i += 1
            if k == curses.KEY_MOUSE:
                self.mouse()
            elif k == 27:
                proc.terminate()
                cancelled = True
                break
        self.scr.timeout(-1)
        proc.wait()
        out.seek(0)
        err.seek(0)
        o, e = out.read().decode(errors="replace"), err.read().decode(errors="replace")
        return None if cancelled else (proc.returncode, o, e)

    def privileged(self, cmd):
        if os.geteuid() == 0:
            return cmd
        pre = shutil.which("sudo") or shutil.which("doas")
        if not pre:
            self.dialog("Administrator access needed", [
                "Installing or removing software needs root privileges.",
                "Run this tool as root (for example with 'su -'), or install sudo or doas."], ["OK"], "warn")
            return None
        return [pre] + cmd

    def run_external(self, cmd, title):
        cmd = self.privileged(cmd)
        if cmd is None:
            return None
        curses.def_prog_mode()
        curses.endwin()
        bar = "=" * 64
        print(f"\n{bar}\n {APP}: {title}\n{bar}")
        print(" Portage (Gentoo's package manager) is about to run.")
        print(" It will show what it plans to do and wait for you:")
        print("   type  Y  and press Enter to go ahead,  N  to cancel.\n")
        print("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n")
        try:
            rc = subprocess.call(cmd)
        except OSError as e:
            print(e)
            rc = 127
        if rc == 0:
            print("\nFinished successfully.")
        else:
            print(f"\nPortage stopped (exit code {rc}). If you answered N that's normal;")
            print("otherwise scroll up to read the messages.")
        try:
            input(f"\nPress Enter to return to {APP}...")
        except (EOFError, KeyboardInterrupt):
            pass
        curses.reset_prog_mode()
        self.scr.clear()
        self.scr.refresh()
        return rc

    # --------------------------------------------------------- actions ----
    def check_updates(self):
        env = dict(os.environ, EMERGE_DEFAULT_OPTS="", LC_ALL="C")
        cmd = ["emerge", "--pretend", "--verbose", "--color=n", "--nospinner"] + self.cfg["update_args"]
        res = self.run_busy(cmd, "Checking for updates", "Asking Portage what's out of date. This can take a minute.", env)
        if res is None:
            self.msg = self.msg or "Check cancelled."
            return
        rc, out, err = res
        self.raw = f"$ {' '.join(cmd)}\n\n{out}\n{err}"
        self.updates = parse_pretend(out)
        self.sel[0].clear()
        self.cursor[0] = self.top[0] = 0
        self.checked = True
        self.tab = 0
        if rc != 0 and not self.updates:
            tail = [ln for ln in (err or out).splitlines() if ln.strip()][-6:]
            r = self.dialog("Portage reported a problem",
                            ["Couldn't work out the update list."] + [""] + tail,
                            ["View full details", "Close"], "warn")
            if r == 0:
                self.view_text("Technical output", self.raw)
        elif rc != 0:
            self.msg = "Portage raised warnings (conflicts?). Menu > Show technical details has the full text."
        else:
            n_held = sum(self.is_held(p) for p in self.updates)
            self.msg = (f"{len(self.updates)} change(s) found" + (f", {n_held} held back." if n_held else ".")
                        if self.updates else "Your system is up to date.")

    def sync(self):
        r = self.dialog("Download the latest package list", [
            "This contacts Gentoo's servers so Portage knows about the newest software.",
            "It doesn't install anything. You need an internet connection."], ["Continue", "Cancel"])
        if r != 0:
            return
        cmd = ["emaint", "sync", "-a"] if shutil.which("emaint") else ["emerge", "--sync"]
        if self.run_external(cmd, "Syncing the package list") is not None:
            self.sync_text, self.sync_days = sync_age()
            self.check_updates()

    def select_all(self):
        if self.tab == 0:
            self.sel[0] = {p.key for p in self.rows() if not self.is_held(p)}
        elif self.tab == 1:
            self.sel[1] = {p.key for p in self.rows()}

    def select_none(self):
        self.sel[min(self.tab, 2)].clear()

    def toggle_yours(self):
        self.yours_only = not self.yours_only
        self.cursor[1] = self.top[1] = 0

    def toggle_hide(self):
        self.hide_held = not self.hide_held
        self.msg = "Held-back packages are " + ("hidden." if self.hide_held else "shown.")

    def toggle(self, advance=True):
        cur, t = self.current(), self.tab
        if not isinstance(cur, Pkg) or t == 2:
            return
        if t == 0 and self.is_held(cur):
            self.msg = "That package is held back. Press H to release it first."
            return
        self.sel[t].symmetric_difference_update({cur.key})
        if advance:
            self.move(1)

    def move(self, n):
        self.cursor[self.tab] = max(0, min(self.cursor[self.tab] + n, len(self.rows()) - 1))

    def install_updates(self):
        if self.tab != 0:
            self.tab = 0
        if not self.checked:
            if self.dialog("Check first", ["You haven't checked for updates yet."], ["Check now", "Cancel"]) == 0:
                self.check_updates()
            return
        chosen = [p for p in self.updates if p.key in self.sel[0] and not self.is_held(p)]
        if not chosen:
            r = self.dialog("Nothing selected", [
                "Tick the updates you want first: click the [ ] box or press Space.",
                "Or select everything that isn't held back."], ["Select all", "OK"])
            if r == 0:
                self.select_all()
            return
        names = [f"  {p.cpn} {p.ver}" for p in chosen[:6]]
        if len(chosen) > 6:
            names.append(f"  ...and {len(chosen) - 6} more")
        r = self.dialog(f"Install {len(chosen)} update(s)?", [
            "You're about to install:", *names, "",
            "What happens next:",
            "1. The screen switches to a terminal where Portage shows its plan.",
            "2. Type Y then Enter there to approve it (N cancels).",
            "3. Press Enter afterwards to return here."], ["Continue", "Cancel"])
        if r != 0:
            return
        cmd = ["emerge"] + self.cfg["emerge_opts"] + ["--oneshot"] + [p.atom for p in chosen]
        if self.run_external(cmd, f"Installing {len(chosen)} update(s)") is not None:
            self.reload_installed()
            self.check_updates()

    def targets_installed(self):
        t = [p for p in self.installed if p.key in self.sel[1]]
        if not t and isinstance(self.current(), Pkg) and self.tab == 1:
            t = [self.current()]
        return t

    def name_list(self, pkgs):
        names = [f"  {p.cpn} {p.ver}" for p in pkgs[:6]]
        return names + ([f"  ...and {len(pkgs) - 6} more"] if len(pkgs) > 6 else [])

    def remove_dialog(self):
        if self.tab != 1:
            self.msg = "Go to the Installed software tab to remove packages."
            return
        targets = self.targets_installed()
        if not targets:
            return
        r = self.dialog(f"Remove {len(targets)} package(s)?", [
            *self.name_list(targets), "",
            "Remove safely only deletes a package if nothing else needs it. Portage lists exactly "
            "what will go and asks you again before removing anything.", "",
            "Force remove ignores dependencies and can break other programs."],
            ["Remove safely", "Force remove...", "Cancel"])
        atoms = [f"{p.cpn}:{p.slot}" if p.slot else p.cpn for p in targets]
        if r == 0:
            cmd = ["emerge", "--ask", "--verbose", "--depclean"] + atoms
        elif r == 1:
            if self.dialog("Force remove - are you sure?", [
                ("This skips the dependency check. Other software may stop working.", self.A["red"]),
                "", *self.name_list(targets)],
                    ["Cancel", "I understand, force remove"], "danger") != 1:
                return
            cmd = ["emerge", "--ask", "--verbose", "--unmerge"] + atoms
        else:
            return
        if self.run_external(cmd, "Removing software") is not None:
            self.reload_installed()

    def reinstall_dialog(self):
        if self.tab != 1:
            self.msg = "Go to the Installed software tab to reinstall packages."
            return
        targets = self.targets_installed()
        if not targets:
            return
        r = self.dialog(f"Reinstall {len(targets)} package(s)?", [
            *self.name_list(targets), "",
            "This rebuilds the same version from source, which can take a while. "
            "Useful when a program is broken or after changing USE flags.",
            "Portage will show its plan and ask before building."], ["Reinstall", "Cancel"])
        if r != 0:
            return
        cmd = ["emerge"] + self.cfg["emerge_opts"] + ["--oneshot"] + [p.atom for p in targets]
        if self.run_external(cmd, "Reinstalling software") is not None:
            self.reload_installed()

    def hold_dialog(self):
        if self.tab != 0:
            self.msg = "Hold-back works on the Updates tab. Press 1 to go there."
            return
        p = self.current()
        if not isinstance(p, Pkg):
            return
        ign = self.cfg["ignored"]
        if self.is_held(p):
            for e in (p.cpn, f"={p.cpv}"):
                if e in ign:
                    ign.remove(e)
            self.msg = f"Released {p.cpn}. It can be installed again."
        else:
            r = self.dialog("Hold this package back?", [
                (f"{p.cpn} {p.ver}", curses.A_BOLD), "",
                "Held packages are greyed out and skipped when you install updates from this tool.", "",
                "All versions: never offer updates for this package.",
                f"Only {p.ver}: skip this release, but offer newer ones later."],
                ["All versions", f"Only {p.ver}", "Cancel"])
            if r not in (0, 1):
                return
            ign.append(p.cpn if r == 0 else f"={p.cpv}")
            self.sel[0].discard(p.key)
            self.msg = f"Holding back {ign[-1]}."
        if not save_config(self.cfg):
            self.msg += " (Couldn't save the list.)"

    def add_rule(self):
        e = self.ask_text("Add a hold-back rule", [
            "Type a package name to hold back every version:", "  sys-devel/gcc", "",
            "or add = and a version to hold back just that release:", "  =sys-devel/gcc-14.2.1"])
        if e and e not in self.cfg["ignored"]:
            self.cfg["ignored"].append(e)
            save_config(self.cfg)
            self.msg = f"Added rule {e}."

    def release_rule(self):
        cur = self.current()
        if self.tab != 2 or not isinstance(cur, str):
            self.msg = "Select a rule in the Held back tab first."
            return
        self.cfg["ignored"].remove(cur)
        save_config(self.cfg)
        self.msg = f"Released {cur}."

    def do_depclean(self):
        if self.dialog("Clean up unused software", [
            "Removes packages that nothing needs any more, such as leftovers after updates or removals.",
            "Portage lists exactly what would go and asks before removing anything."],
                       ["Continue", "Cancel"]) == 0:
            if self.run_external(["emerge", "--ask", "--verbose", "--depclean"], "Cleaning up unused software") is not None:
                self.reload_installed()

    def do_preserved(self):
        if self.dialog("Fix programs broken by updates", [
            "After some updates, programs can lose a library they relied on. "
            "This rebuilds them so they work again (@preserved-rebuild).",
            "If Portage says there's nothing to do, you're fine."], ["Continue", "Cancel"]) == 0:
            self.run_external(["emerge", "--ask", "--verbose", "@preserved-rebuild"], "Fixing broken programs")

    def do_etc(self):
        tool = "dispatch-conf" if shutil.which("dispatch-conf") else "etc-update"
        if self.dialog("Review config file changes", [
            "Updates sometimes ship new versions of configuration files. "
            "This tool lets you review and merge them one at a time.",
            f"It will run {tool}. Nothing changes unless you choose to apply it."], ["Continue", "Cancel"]) == 0:
            self.run_external([tool], "Reviewing config file changes")

    def show_raw(self):
        self.view_text("Technical output of the last update check", self.raw or "Nothing yet. Check for updates first.")

    def help(self):
        self.view_text("Help", HELP)

    def welcome(self):
        r = self.dialog(f"Welcome to {APP}", [
            "This tool helps you keep Gentoo up to date without memorising emerge commands.", "",
            "1. Check for updates to see what's available.",
            "2. Tick the ones you want. Hold back any you're not ready for.",
            "3. Install. Portage shows its plan and asks before it changes anything.", "",
            "Use the mouse or keyboard. Press F1 any time for help."],
            ["Check for updates now", "Look around first"])
        self.cfg["welcomed"] = True
        save_config(self.cfg)
        if r == 0:
            self.check_updates()

    def quit_app(self):
        self.want_quit = True

    def main_menu(self):
        items = [
            ("Check for updates", self.check_updates),
            ("Download latest package list (sync)", self.sync),
            ("Clean up unused software", self.do_depclean),
            ("Fix programs broken by updates", self.do_preserved),
            ("Review config file changes", self.do_etc),
            ("Show technical details of last check", self.show_raw),
            (("Show" if self.hide_held else "Hide") + " held-back packages in the list", self.toggle_hide),
            ("Welcome guide", self.welcome),
            ("Help and keyboard shortcuts", self.help),
            ("Quit", self.quit_app),
        ]
        i = self.menu("Menu", items)
        if i >= 0:
            items[i][1]()

    # ----------------------------------------------------------- input ----
    def switch(self, i):
        self.tab, self.search, self.searching = i, "", False

    def on_mouse(self):
        m = self.mouse()
        if not m:
            return
        b, x, y = m
        if b & WHEEL_UP:
            self.move(-3)
        elif b & WHEEL_DOWN:
            self.move(3)
        elif b & LEFT:
            for (hy, hx, hw, kind, arg) in reversed(self.hits):
                if hy == y and hx <= x < hx + hw:
                    if kind == "menu":
                        self.main_menu()
                    elif kind == "tab":
                        self.switch(arg)
                    elif kind == "search":
                        self.searching = True
                    elif kind == "btn":
                        arg()
                    elif kind == "row":
                        self.cursor[self.tab] = arg
                        if x < 4 and self.tab < 2:
                            self.toggle(advance=False)
                    return

    def search_key(self, k):
        if k in (10, 13, curses.KEY_ENTER):
            self.searching = False
        elif k == 27:
            self.searching, self.search = False, ""
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            self.search = self.search[:-1]
        elif k == curses.KEY_MOUSE:
            self.searching = False
            self.on_mouse()
            return
        elif 32 <= k < 127:
            self.search += chr(k)
        self.cursor[self.tab] = self.top[self.tab] = 0

    def handle(self, k):
        t = self.tab
        h, _ = self.scr.getmaxyx()
        if k in (curses.KEY_RESIZE, -1):
            return
        if k == curses.KEY_MOUSE:
            return self.on_mouse()
        if self.searching:
            return self.search_key(k)
        if k in (ord("q"), ord("Q")):
            self.want_quit = True
        elif k in (curses.KEY_F1, ord("?")):
            self.help()
        elif k == curses.KEY_F10:
            self.main_menu()
        elif k in (ord("1"), ord("2"), ord("3")):
            self.switch(k - ord("1"))
        elif k == 9:
            self.switch((t + 1) % 3)
        elif k == curses.KEY_BTAB:
            self.switch((t - 1) % 3)
        elif k == ord("/"):
            self.searching = True
        elif k == 27:
            self.search = ""
        elif k in (curses.KEY_DOWN, ord("j")):
            self.move(1)
        elif k in (curses.KEY_UP, ord("k")):
            self.move(-1)
        elif k == curses.KEY_NPAGE:
            self.move(h - 12)
        elif k == curses.KEY_PPAGE:
            self.move(-(h - 12))
        elif k in (curses.KEY_HOME, ord("g")):
            self.cursor[t] = 0
        elif k in (curses.KEY_END, ord("G")):
            self.cursor[t] = max(0, len(self.rows()) - 1)
        elif k == ord(" "):
            self.toggle()
        elif k in (10, 13, curses.KEY_ENTER) and t == 0:
            self.install_updates()
        elif 32 <= k < 127:
            ch = chr(k).lower()
            for _, key, fn, _ in self.buttons():
                if key == ch:
                    fn()
                    break

    def run(self):
        if not self.cfg.get("welcomed"):
            self.welcome()
        while not self.want_quit:
            self.draw()
            self.scr.refresh()
            k = self.scr.getch()
            self.msg = ""
            self.tip += 1 if k != -1 else 0
            self.handle(k)


def main():
    if not shutil.which("emerge"):
        sys.exit(f"{APP}: 'emerge' not found - this tool is for Gentoo Linux.")
    if not sys.stdout.isatty():
        sys.exit(f"{APP}: needs an interactive terminal.")
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: App(scr).run())


if __name__ == "__main__":
    main()
