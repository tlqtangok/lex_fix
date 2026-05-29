#!/usr/bin/env python3
"""
Microsoft Wubi .lex file reader / search / editor
Supports both mschxudp (user.lex) and imscwubi (ChsWubiNew.lex) formats.
Reference: https://github.com/nopdan/rose
"""

_VERSION = "v20260529-162c10e"

import argparse
import json
import struct
import os
import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Apple-inspired colour palette ────────────────────────────────────────────
_C = {
    "win":     "#F5F5F7",   # window chrome background
    "bar":     "#F2F2F7",   # toolbar / statusbar strip
    "panel":   "#FFFFFF",   # main content area
    "sep":     "#D1D1D6",   # separators and thin borders
    "accent":  "#007AFF",   # macOS / iOS blue
    "acc_hov": "#005EC4",   # accent hover shade
    "acc_fg":  "#FFFFFF",   # text on accent background
    "text":    "#1D1D1F",   # primary text
    "text2":   "#6E6E73",   # secondary / caption text
    "row_alt": "#F5F5F7",   # alternating table row tint
    "danger":  "#FF3B30",   # destructive action
    "dan_hov": "#CC2A22",
    "btn_hov": "#E5EDFF",   # button hover tint
    "entry":   "#FFFFFF",   # entry field background
    "ebdr":    "#C7C7CC",   # entry / control border
}
_FN      = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
_FONT    = (_FN, 13)
_FONT_SM = (_FN, 11)
_FONT_LG = (_FN, 15, "bold")
_FONT_MO = ("SF Mono", 12) if sys.platform == "darwin" else ("Consolas", 10)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class LexEntry:
    word: str
    code: str
    priority: int = 60000

    def __repr__(self):
        return f"LexEntry(code={self.code!r}, word={self.word!r}, pri={self.priority})"


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _decode_utf16le(b: bytes) -> str:
    try:
        return b.decode("utf-16-le")
    except Exception:
        return ""


def _encode_utf16le(s: str) -> bytes:
    return s.encode("utf-16-le")


# ---------------------------------------------------------------------------
# mschxudp reader / writer  (user.lex format)
# ---------------------------------------------------------------------------

class MschxudpFile:
    """
    Binary layout:
      0x00  magic  "mschxudp" (8)
      0x08  unk1   (4)
      0x0c  unk2   (4) usually 0x00000001
      0x10  idx_start   uint32 (usually 0x40)
      0x14  entry_start uint32
      0x18  file_size   uint32
      0x1c  entry_count uint32
      0x20  rest of header...
      idx_start   : sorted offsets[] relative to entry_start (uint32 each)
      entry_start : entries
    
    Each entry:
      +00  marker  10 00 10 00  (4)
      +04  const   1a 00        (2)
      +06  flags   01/02 06     (2)
      +08  zeros   00 00 00 00  (4)
      +12  stamp   XX XX XX XX  (4)  — stays same for all entries in file
      +16  code    UTF-16LE padded to 8 bytes
      +24  null    00 00
      +26  word    UTF-16LE, variable length
      +??  null    00 00
    """

    MAGIC = b"mschxudp"
    ENTRY_MARKER = bytes([0x10, 0x00, 0x10, 0x00])
    ENTRY_CONST = bytes([0x1A, 0x00])
    DEFAULT_FLAGS = bytes([0x01, 0x06])
    DEFAULT_ZEROS = bytes([0x00, 0x00, 0x00, 0x00])
    DEFAULT_STAMP = bytes([0x58, 0xA7, 0xAA, 0x31])
    HEADER_FIXED_SIZE = 0x20  # first 32 bytes are not idx

    def __init__(self):
        self.filepath: Optional[str] = None
        self.entries: List[LexEntry] = []
        self._raw_head: bytes = b""  # bytes 0x00..0x3f
        self.idx_start: int = 0x40
        self.entry_stamp: bytes = self.DEFAULT_STAMP

    # ---- reading ----

    def read(self, filepath: str) -> List[LexEntry]:
        with open(filepath, "rb") as f:
            data = f.read()
        self.filepath = filepath
        if data[:8] != self.MAGIC:
            raise ValueError(f"Not an mschxudp file (magic={data[:8]!r})")

        self.idx_start = struct.unpack_from("<I", data, 0x10)[0]
        entry_start = struct.unpack_from("<I", data, 0x14)[0]

        self._raw_head = bytearray(data[: self.idx_start])

        # Read entry stamp from first entry (bytes +12..+15)
        if entry_start + 16 <= len(data):
            self.entry_stamp = bytes(data[entry_start + 12 : entry_start + 16])

        self.entries = []
        pos = entry_start
        while pos + 28 <= len(data):
            if data[pos : pos + 4] != self.ENTRY_MARKER:
                break
            # bytes +4..+5 store the word's byte offset within the entry
            word_offset = struct.unpack_from("<H", data, pos + 4)[0]
            code_bytes = data[pos + 16 : pos + 24]
            code = _decode_utf16le(code_bytes).rstrip("\x00")
            we = pos + word_offset
            while we + 1 < len(data) and not (data[we] == 0 and data[we + 1] == 0):
                we += 2
            word = _decode_utf16le(data[pos + word_offset : we])
            if word:
                self.entries.append(LexEntry(word=word, code=code))
            pos = we + 2

        return self.entries

    # ---- writing ----

    def _build_entry_bytes(self, e: LexEntry) -> bytes:
        code_str = e.code[:4]
        code_utf16 = _encode_utf16le(code_str)
        code_field = (code_utf16 + b"\x00" * 8)[:8]
        word_utf16 = _encode_utf16le(e.word)
        return (
            self.ENTRY_MARKER
            + self.ENTRY_CONST
            + self.DEFAULT_FLAGS
            + self.DEFAULT_ZEROS
            + self.entry_stamp
            + code_field
            + b"\x00\x00"
            + word_utf16
            + b"\x00\x00"
        )

    def save(self, filepath: Optional[str] = None) -> str:
        if filepath is None:
            filepath = self.filepath
        if filepath is None:
            raise ValueError("No output path")

        sorted_entries = sorted(self.entries, key=lambda e: e.code)
        n = len(sorted_entries)

        # Build entries section
        entries_data = bytearray()
        offsets: List[int] = []
        for e in sorted_entries:
            offsets.append(len(entries_data))
            entries_data += self._build_entry_bytes(e)

        # Build index table (sorted offsets, relative to entry_start)
        idx_data = bytearray()
        for off in offsets:
            idx_data += struct.pack("<I", off)

        new_entry_start = self.idx_start + len(idx_data)
        new_file_size = new_entry_start + len(entries_data)

        # Build header: keep original fixed prefix, update fields
        header = bytearray(self._raw_head) if len(self._raw_head) >= self.idx_start else bytearray(self.idx_start)
        header[0:8] = self.MAGIC
        struct.pack_into("<I", header, 0x14, new_entry_start)
        struct.pack_into("<I", header, 0x18, new_file_size)
        struct.pack_into("<I", header, 0x1C, n)

        with open(filepath, "wb") as f:
            f.write(header)
            f.write(idx_data)
            f.write(entries_data)

        return filepath


# ---------------------------------------------------------------------------
# imscwubi reader / writer  (ChsWubiNew.lex / rose format)
# ---------------------------------------------------------------------------

class ImscwubiFile:
    """
    Binary layout:
      0x00  magic "imscwubi" (8)
      0x08  unk  (4)
      0x0c  idx_start   uint32 (0x40)
      0x10  entry_start uint32 (0xa8)
      0x14  total_size  uint32
      0x18  unk         (4)
      0x1c  create_stamp uint32
      0x20  zeros...
      0x40  code_weight[26] uint32 each  (a..z)
      0xa8  entries
    
    Each entry:
      uint16 length   (total bytes of this entry, including the length field)
      uint16 priority
      uint16 code_len (chars)
      8 bytes code UTF-16LE
      (length-16) bytes word UTF-16LE
      2 bytes null
    """

    MAGIC = b"imscwubi"
    IDX_START = 0x40
    ENTRY_START = 0xA8

    def __init__(self):
        self.filepath: Optional[str] = None
        self.entries: List[LexEntry] = []
        self._raw_header: bytes = b""
        self.create_stamp: int = 0

    def read(self, filepath: str) -> List[LexEntry]:
        with open(filepath, "rb") as f:
            data = f.read()
        self.filepath = filepath
        if data[:8] != self.MAGIC:
            raise ValueError(f"Not an imscwubi file (magic={data[:8]!r})")

        entry_start = struct.unpack_from("<I", data, 0x10)[0]
        self.create_stamp = struct.unpack_from("<I", data, 0x1C)[0]
        self._raw_header = bytes(data[:entry_start])

        self.entries = []
        pos = entry_start
        while pos + 4 <= len(data):
            length = struct.unpack_from("<H", data, pos)[0]
            if length < 18:
                break
            priority = struct.unpack_from("<H", data, pos + 2)[0]
            code_len = struct.unpack_from("<H", data, pos + 4)[0]
            code_bytes = data[pos + 6 : pos + 6 + min(code_len * 2, 8)]
            code = _decode_utf16le(code_bytes)
            word_bytes = data[pos + 14 : pos + length - 2]
            word = _decode_utf16le(word_bytes)
            if word:
                self.entries.append(LexEntry(word=word, code=code, priority=priority))
            pos += length

        return self.entries

    def save(self, filepath: Optional[str] = None) -> str:
        if filepath is None:
            filepath = self.filepath
        if filepath is None:
            raise ValueError("No output path")

        # Build entries section + code weight table
        code_weight = [0] * 26
        entries_data = bytearray()
        for e in self.entries:
            word_bytes = _encode_utf16le(e.word)
            length = 16 + len(word_bytes)
            code_str = e.code[:4]
            code_utf16 = _encode_utf16le(code_str)
            code_field = (code_utf16 + b"\x00" * 8)[:8]
            first_char_byte = code_utf16[0] if code_utf16 else 0
            if ord("a") <= first_char_byte <= ord("z"):
                code_weight[first_char_byte - ord("a")] += 1
            entries_data += struct.pack("<HHH", length, e.priority, len(code_str))
            entries_data += code_field
            entries_data += word_bytes
            entries_data += b"\x00\x00"

        total_size = self.ENTRY_START + len(entries_data)

        # Rebuild header
        header = bytearray(max(len(self._raw_header), self.ENTRY_START))
        if self._raw_header:
            header[: len(self._raw_header)] = self._raw_header
        else:
            header[0:8] = self.MAGIC
            header[8:12] = b"\x01\x00\x01\x00"
            struct.pack_into("<I", header, 0x0C, self.IDX_START)
            struct.pack_into("<I", header, 0x10, self.ENTRY_START)
            struct.pack_into("<I", header, 0x1C, self.create_stamp or int(time.time()))

        struct.pack_into("<I", header, 0x14, total_size)
        for i in range(26):
            struct.pack_into("<I", header, self.IDX_START + i * 4, code_weight[i])

        with open(filepath, "wb") as f:
            f.write(header)
            f.write(entries_data)

        return filepath


# ---------------------------------------------------------------------------
# Generic LexFile wrapper
# ---------------------------------------------------------------------------

class LexFile:
    """Detects format and delegates to the appropriate implementation."""

    def __init__(self):
        self._impl = None
        self.entries: List[LexEntry] = []
        self.filepath: Optional[str] = None
        self.format_name: str = "unknown"
        self.read_only: bool = False

    def read(self, filepath: str) -> List[LexEntry]:
        with open(filepath, "rb") as f:
            magic = f.read(8)

        if magic == MschxudpFile.MAGIC:
            self._impl = MschxudpFile()
            self.format_name = "mschxudp"
            self.read_only = False
        elif magic == ImscwubiFile.MAGIC:
            self._impl = ImscwubiFile()
            self.format_name = "imscwubi"
            self.read_only = False
        else:
            raise ValueError(f"Unknown .lex magic bytes: {magic!r}")

        self.entries = self._impl.read(filepath)
        self.filepath = filepath
        return self.entries

    def save(self, filepath: Optional[str] = None) -> str:
        if self._impl is None:
            raise RuntimeError("No file loaded")
        self._impl.entries = self.entries
        return self._impl.save(filepath)


# ---------------------------------------------------------------------------
# Entry editor dialog
# ---------------------------------------------------------------------------

class EntryDialog(tk.Toplevel):
    def __init__(self, parent, title: str, entry: Optional[LexEntry] = None,
                 show_priority: bool = True):
        super().__init__(parent)
        self.title(title)
        self.result: Optional[LexEntry] = None
        self.resizable(False, False)
        self.transient(parent)
        self.configure(bg=_C["win"])

        # ── header strip ─────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=_C["bar"])
        hdr.pack(fill=tk.X)
        tk.Frame(hdr, height=1, bg=_C["sep"]).pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(hdr, text=title, font=_FONT_LG,
                 bg=_C["bar"], fg=_C["text"],
                 anchor=tk.W, padx=20, pady=14).pack(fill=tk.X)

        # ── body ─────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=_C["win"], padx=20, pady=8)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        def _lbl(row, text):
            tk.Label(body, text=text, font=_FONT_SM,
                     bg=_C["win"], fg=_C["text2"],
                     anchor=tk.W).grid(row=row * 2, column=0, columnspan=2,
                                       sticky=tk.W, pady=(10 if row else 0, 3))

        def _field(row, var, mono=False, width=28):
            outer = tk.Frame(body, bg=_C["ebdr"])
            e = tk.Entry(outer, textvariable=var, width=width,
                         font=_FONT_MO if mono else _FONT,
                         bg=_C["entry"], fg=_C["text"],
                         relief="flat", bd=4,
                         insertbackground=_C["accent"])
            e.pack(padx=1, pady=1)
            outer.grid(row=row * 2 + 1, column=0, columnspan=2,
                       sticky=tk.EW, pady=(0, 2))
            return e

        _lbl(0, "Word (词)")
        self._word = tk.StringVar(value=entry.word if entry else "")
        word_e = _field(0, self._word)

        _lbl(1, "Code (编码, ≤ 4 chars)")
        self._code = tk.StringVar(value=entry.code if entry else "")
        _field(1, self._code, mono=True, width=14)

        if show_priority:
            _lbl(2, "Priority (权重)")
            self._priority = tk.StringVar(value=str(entry.priority if entry else 60000))
            _field(2, self._priority, width=14)
        else:
            self._priority = tk.StringVar(value="0")

        # ── footer buttons ────────────────────────────────────────────────
        tk.Frame(self, height=1, bg=_C["sep"]).pack(fill=tk.X, pady=(8, 0))
        foot = tk.Frame(self, bg=_C["win"], padx=20, pady=14)
        foot.pack(fill=tk.X)

        def _mkbtn(parent, text, cmd, primary=False):
            bg  = _C["accent"] if primary else _C["bar"]
            fg  = _C["acc_fg"] if primary else _C["text"]
            hov = _C["acc_hov"] if primary else _C["btn_hov"]
            b = tk.Button(parent, text=text, font=_FONT,
                          bg=bg, fg=fg,
                          activebackground=hov, activeforeground=fg,
                          relief="flat", bd=0, padx=16, pady=6,
                          cursor="hand2", command=cmd)
            b.bind("<Enter>", lambda e: b.config(bg=hov))
            b.bind("<Leave>", lambda e: b.config(bg=bg))
            return b

        _mkbtn(foot, "Cancel", self.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        _mkbtn(foot, "Save", self._ok, primary=True).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        word_e.focus_set()
        self.wait_window()

    def _ok(self):
        word = self._word.get().strip()
        code = self._code.get().strip()[:4].lower()
        try:
            priority = int(self._priority.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Priority must be an integer.", parent=self)
            return
        if not word:
            messagebox.showerror("Error", "Word (词) cannot be empty.", parent=self)
            return
        if not code:
            messagebox.showerror("Error", "Code (编码) cannot be empty.", parent=self)
            return
        self.result = LexEntry(word=word, code=code, priority=priority)
        self.destroy()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class LexEditorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Wubi .lex Editor")
        self.root.geometry("1100x720")
        self.root.minsize(700, 500)

        self.lex = LexFile()
        self._all_entries: List[LexEntry] = []
        self._unsaved = False

        self._prefs_path = os.path.join(
            os.environ.get("TEMP") or os.environ.get("TMP") or os.path.expanduser("~"),
            ".lex_editor_prefs.json"
        )
        self._recent: List[str] = self._load_prefs().get("recent", [])

        self._setup_style()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()
        self._build_tree()

        self.root.bind("<Control-o>", lambda e: self.cmd_open())
        self.root.bind("<Control-s>", lambda e: self.cmd_save())
        self.root.bind("<Control-n>", lambda e: self.cmd_add())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # auto-open last file; fall back to IME lex if no recent history
        _ime = os.path.join(os.environ.get("USERPROFILE", ""),
                            r"AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex")
        _autoopen = self._recent[0] if self._recent else _ime
        if os.path.isfile(_autoopen):
            self.root.after(0, lambda p=_autoopen: self._load_file(p))

    # ---- UI construction ----

    # ---- prefs / recent files ----

    _MAX_RECENT = 10

    def _load_prefs(self) -> dict:
        try:
            with open(self._prefs_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_prefs(self):
        try:
            with open(self._prefs_path, "w", encoding="utf-8") as f:
                json.dump({"recent": self._recent}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _push_recent(self, filepath: str):
        path = os.path.abspath(filepath)
        if path in self._recent:
            self._recent.remove(path)
        self._recent.insert(0, path)
        self._recent = self._recent[:self._MAX_RECENT]
        self._save_prefs()
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self._recent_menu.delete(0, tk.END)
        if not self._recent:
            self._recent_menu.add_command(label="(empty)", state=tk.DISABLED)
        for path in self._recent:
            self._recent_menu.add_command(
                label=path,
                command=lambda p=path: self._load_file(p),
            )
        self._recent_menu.add_separator()
        self._recent_menu.add_command(
            label="Clear Recent",
            command=self._clear_recent,
        )

    def _clear_recent(self):
        self._recent.clear()
        self._save_prefs()
        self._rebuild_recent_menu()

    def _setup_style(self):
        """Configure ttk styles for an Apple-inspired flat look."""
        s = ttk.Style()
        s.theme_use("clam")
        bg, bar, sep = _C["win"], _C["bar"], _C["sep"]
        acc, txt, txt2 = _C["accent"], _C["text"], _C["text2"]
        self.root.configure(bg=bg)
        s.configure(".",
                    background=bg, foreground=txt, font=_FONT,
                    borderwidth=0, relief="flat")
        s.configure("TFrame",         background=bg)
        s.configure("TLabel",         background=bg,  foreground=txt,  font=_FONT)
        s.configure("Sec.TLabel",     background=bg,  foreground=txt2, font=_FONT_SM)
        s.configure("Treeview",
                    background=_C["panel"], foreground=txt,
                    font=_FONT, rowheight=28,
                    fieldbackground=_C["panel"],
                    borderwidth=0, relief="flat")
        s.configure("Treeview.Heading",
                    background=bar, foreground=txt2,
                    font=_FONT_SM, relief="flat",
                    borderwidth=0, padding=(8, 6))
        s.map("Treeview",
              background=[("selected", acc)],
              foreground=[("selected", _C["acc_fg"])])
        s.map("Treeview.Heading",
              background=[("active", _C["btn_hov"])],
              relief=[("active", "flat")])
        s.configure("TScrollbar",
                    background=bar, troughcolor=bg,
                    borderwidth=0, relief="flat", arrowsize=12,
                    gripcount=0)
        s.map("TScrollbar", background=[("active", sep)])

    def _refresh_mode_btns(self):
        cur = self._mode_var.get()
        for val, btn in self._mode_btns.items():
            if val == cur:
                btn.config(bg=_C["accent"], fg=_C["acc_fg"])
            else:
                btn.config(bg=_C["entry"], fg=_C["text2"])

    def _build_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)

        _IME_LEX = os.path.join(os.environ.get("USERPROFILE", ""),
                                r"AppData\Roaming\Microsoft\InputMethod\Chs\ChsWubiEUDPv1.lex")

        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="File", menu=fm)
        fm.add_command(label="Open…\tCtrl+O", command=self.cmd_open)
        fm.add_command(label="Open IME lex  (%userprofile%\\…\\ChsWubiEUDPv1.lex)",
                       command=lambda: self._load_file(_IME_LEX) if os.path.isfile(_IME_LEX)
                       else messagebox.showerror("Not found", f"File not found:\n{_IME_LEX}"))

        self._recent_menu = tk.Menu(fm, tearoff=0)
        fm.add_cascade(label="Open Recent", menu=self._recent_menu)
        self._rebuild_recent_menu()

        fm.add_separator()
        fm.add_command(label="Save\tCtrl+S", command=self.cmd_save)
        fm.add_command(label="Save As…", command=self.cmd_save_as)
        fm.add_separator()
        fm.add_command(label="About", command=self.cmd_about)
        fm.add_command(label="Exit", command=self._on_close)

        em = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Edit", menu=em)
        em.add_command(label="Add Entry\tCtrl+N", command=self.cmd_add)
        em.add_command(label="Edit Entry\tF2", command=self.cmd_edit)
        em.add_command(label="Delete Entry\tDel", command=self.cmd_delete)

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg=_C["bar"])
        bar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self.root, height=1, bg=_C["sep"]).pack(side=tk.TOP, fill=tk.X)

        # helper: flat hover-effect button
        def _tbtn(parent, text, cmd, danger=False):
            normal_bg = _C["danger"] if danger else _C["bar"]
            normal_fg = _C["acc_fg"] if danger else _C["text"]
            hover_bg  = _C["dan_hov"] if danger else _C["btn_hov"]
            b = tk.Button(parent, text=text, font=_FONT_SM,
                          bg=normal_bg, fg=normal_fg,
                          activebackground=hover_bg, activeforeground=normal_fg,
                          relief="flat", bd=0,
                          padx=12, pady=6, cursor="hand2", command=cmd)
            b.bind("<Enter>", lambda e: b.config(bg=hover_bg))
            b.bind("<Leave>", lambda e: b.config(bg=normal_bg))
            return b

        # left: file + entry action buttons
        left = tk.Frame(bar, bg=_C["bar"])
        left.pack(side=tk.LEFT, padx=8, pady=4)
        _tbtn(left, "Open",   self.cmd_open ).pack(side=tk.LEFT)
        _tbtn(left, "Save",   self.cmd_save ).pack(side=tk.LEFT)
        tk.Frame(left, width=1, bg=_C["sep"]).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=4)
        _tbtn(left, "+ Add",  self.cmd_add  ).pack(side=tk.LEFT)
        _tbtn(left, "Edit",   self.cmd_edit ).pack(side=tk.LEFT)
        _tbtn(left, "Delete", self.cmd_delete, danger=True).pack(side=tk.LEFT)

        # right: search + mode selector + format label
        right = tk.Frame(bar, bg=_C["bar"])
        right.pack(side=tk.RIGHT, padx=8, pady=4)

        self._format_label = tk.Label(right, text="", font=_FONT_SM,
                                      bg=_C["bar"], fg=_C["text2"])
        self._format_label.pack(side=tk.RIGHT, padx=(16, 0))

        # result count
        self._result_count = tk.Label(right, text="", font=_FONT_SM,
                                      bg=_C["bar"], fg=_C["text2"])
        self._result_count.pack(side=tk.RIGHT, padx=(8, 0))

        # segmented mode control [All | Word | Code]
        self._mode_var  = tk.StringVar(value="all")
        self._mode_btns: dict = {}
        seg_out = tk.Frame(right, bg=_C["ebdr"])
        seg_out.pack(side=tk.RIGHT, padx=(8, 0))
        seg_in = tk.Frame(seg_out, bg=_C["ebdr"])
        seg_in.pack(padx=1, pady=1)
        for label, val in [("All", "all"), ("Word", "word"), ("Code", "code")]:
            b = tk.Label(seg_in, text=label, font=_FONT_SM,
                         padx=10, pady=3, cursor="hand2")
            def _on_mode(e, v=val):
                self._mode_var.set(v)
                self._refresh_mode_btns()
                self._apply_filter()
            b.bind("<Button-1>", _on_mode)
            b.pack(side=tk.LEFT)
            self._mode_btns[val] = b
        self._refresh_mode_btns()

        # search field
        srch_out = tk.Frame(right, bg=_C["ebdr"])
        srch_out.pack(side=tk.RIGHT, padx=(0, 4))
        srch_in = tk.Frame(srch_out, bg=_C["entry"])
        srch_in.pack(padx=1, pady=1)
        tk.Label(srch_in, text="🔍", font=_FONT_SM,
                 bg=_C["entry"], fg=_C["text2"]).pack(side=tk.LEFT, padx=(6, 0))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(srch_in, textvariable=self._search_var, width=22,
                 font=_FONT, bg=_C["entry"], fg=_C["text"],
                 relief="flat", bd=0,
                 insertbackground=_C["accent"]).pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(srch_in, text="✕", font=_FONT_SM,
                  bg=_C["entry"], fg=_C["text2"],
                  activebackground=_C["entry"], activeforeground=_C["text"],
                  relief="flat", bd=0, padx=4, cursor="hand2",
                  command=self._clear_search).pack(side=tk.LEFT, padx=(0, 4))

    def _build_search_bar(self):
        pass  # integrated into _build_toolbar

    def _build_tree(self):
        outer = tk.Frame(self.root, bg=_C["sep"])
        outer.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(outer, bg=_C["panel"])
        inner.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        cols = ("word", "code", "priority")
        self._tree = ttk.Treeview(inner, columns=cols, show="headings",
                                  selectmode="browse")
        self._tree.heading("word",     text="Word  词",
                           command=lambda: self._sort("word"))
        self._tree.heading("code",     text="Code  编码",
                           command=lambda: self._sort("code"))
        self._tree.heading("priority", text="Priority  权重",
                           command=lambda: self._sort("priority"))
        self._tree.column("word",     width=360, minwidth=120)
        self._tree.column("code",     width=130, minwidth=80)
        self._tree.column("priority", width=110, minwidth=60, anchor=tk.CENTER)

        self._tree.tag_configure("odd",  background="#FFFFFF")
        self._tree.tag_configure("even", background=_C["row_alt"])

        sby = ttk.Scrollbar(inner, orient=tk.VERTICAL,   command=self._tree.yview)
        sbx = ttk.Scrollbar(inner, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=sby.set, xscrollcommand=sbx.set)

        sby.pack(side=tk.RIGHT,  fill=tk.Y)
        sbx.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        self._tree.bind("<Double-1>", lambda e: self.cmd_edit())
        self._tree.bind("<Delete>",   lambda e: self.cmd_delete())
        self._tree.bind("<F2>",       lambda e: self.cmd_edit())

        self._sort_rev: dict = {}

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=_C["bar"])
        sb.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(self.root, height=1, bg=_C["sep"]).pack(side=tk.BOTTOM, fill=tk.X)
        self._status_var = tk.StringVar(value="Ready — open a .lex file to begin.")
        tk.Label(sb, textvariable=self._status_var,
                 font=_FONT_SM, bg=_C["bar"], fg=_C["text2"],
                 anchor=tk.W, padx=12, pady=5).pack(fill=tk.X)

    # ---- file operations ----

    def _open_named(self, filename: str):
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, filename)
        if os.path.isfile(path):
            self._load_file(path)
        else:
            messagebox.showerror("Not found", f"{filename} not found in\n{here}")

    def cmd_about(self):
        win = tk.Toplevel(self.root)
        win.title("About")
        win.resizable(False, False)
        win.configure(bg=_C["win"])
        win.grab_set()

        # header strip
        hdr = tk.Frame(win, bg=_C["accent"], height=6)
        hdr.pack(fill=tk.X)

        body = tk.Frame(win, bg=_C["win"], padx=32, pady=24)
        body.pack(fill=tk.BOTH)

        tk.Label(body, text="Wubi .lex Editor", font=("Helvetica", 15, "bold"),
                 bg=_C["win"], fg=_C["text"]).pack(anchor=tk.W)
        tk.Label(body, text=_VERSION,
                 font=_FONT_SM, bg=_C["win"], fg=_C["text2"]).pack(anchor=tk.W, pady=(0, 2))
        tk.Label(body, text="Microsoft Wubi IME dictionary viewer & editor",
                 font=_FONT_SM, bg=_C["win"], fg=_C["text2"]).pack(anchor=tk.W, pady=(0, 16))

        for label, value in [("Author", "Jidor Tang"), ("Email", "tlqtangok@126.com"),
                              ("Source", "https://github.com/tlqtangok/lex_fix")]:
            row = tk.Frame(body, bg=_C["win"])
            row.pack(anchor=tk.W, pady=1)
            tk.Label(row, text=f"{label}:", width=7, anchor=tk.W,
                     font=_FONT_SM, bg=_C["win"], fg=_C["text2"]).pack(side=tk.LEFT)
            tk.Label(row, text=value, font=_FONT_SM,
                     bg=_C["win"], fg=_C["text"]).pack(side=tk.LEFT)

        tk.Frame(body, height=1, bg=_C["sep"]).pack(fill=tk.X, pady=(16, 12))
        ok = tk.Button(body, text="OK", width=8, font=_FONT,
                       bg=_C["accent"], fg=_C["acc_fg"], relief=tk.FLAT,
                       cursor="hand2", command=win.destroy)
        ok.pack(anchor=tk.E)
        win.bind("<Return>", lambda e: win.destroy())
        win.bind("<Escape>", lambda e: win.destroy())

    def cmd_open(self):
        here = os.path.dirname(os.path.abspath(__file__))
        path = filedialog.askopenfilename(
            title="Open .lex file",
            filetypes=[("Lex files", "*.lex"), ("All files", "*.*")],
            initialdir=here,
        )
        if path:
            self._load_file(path)

    def _load_file(self, filepath: str):
        try:
            self.lex = LexFile()
            self.lex.read(filepath)
            self._all_entries = list(self.lex.entries)
            self._unsaved = False
            self._apply_filter()
            self.root.title(f"Wubi .lex Editor — {filepath}")
            self._format_label.config(
                text=f"{self.lex.format_name}  •  {len(self._all_entries):,} entries",
                fg="#CC2A22" if self.lex.read_only else _C["text2"],
            )
            self._set_status(
                f"Loaded {os.path.basename(filepath)}  ({len(self._all_entries):,} entries)"
            )
            self._push_recent(filepath)
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def cmd_save(self):
        if not self.lex.filepath:
            self.cmd_save_as()
            return
        try:
            self.lex.entries = self._all_entries
            self.lex.save()
            self._mark_saved()
            self._set_status(
                f"Saved  {os.path.basename(self.lex.filepath)}"
                f"  ({len(self._all_entries):,} entries)"
            )
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def cmd_save_as(self):
        path = filedialog.asksaveasfilename(
            title="Save As",
            defaultextension=".lex",
            filetypes=[("Lex files", "*.lex"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.lex.entries = self._all_entries
            self.lex.save(path)
            self.lex.filepath = path
            self._mark_saved()
            self._set_status(f"Saved to {path}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    # ---- entry CRUD ----

    def cmd_add(self):
        show_pri = self.lex.format_name.startswith("imscwubi")
        dlg = EntryDialog(self.root, "Add Entry", show_priority=show_pri)
        if dlg.result:
            self._all_entries.append(dlg.result)
            self.lex.entries = self._all_entries
            self._apply_filter()
            self._mark_unsaved()
            self._set_status(
                f"Added: {dlg.result.word}  [{dlg.result.code}]"
            )

    def cmd_edit(self):
        entry, idx = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Edit", "Select an entry first.")
            return
        show_pri = self.lex.format_name.startswith("imscwubi")
        dlg = EntryDialog(self.root, "Edit Entry", entry=entry, show_priority=show_pri)
        if dlg.result:
            self._all_entries[idx] = dlg.result
            self.lex.entries = self._all_entries
            self._apply_filter()
            self._mark_unsaved()
            self._set_status(
                f"Updated: {dlg.result.word}  [{dlg.result.code}]"
            )

    def cmd_delete(self):
        entry, idx = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Delete", "Select an entry first.")
            return
        if messagebox.askyesno(
            "Confirm Delete",
            f"Delete entry?\n\nWord:  {entry.word}\nCode:  {entry.code}",
        ):
            self._all_entries.pop(idx)
            self.lex.entries = self._all_entries
            self._apply_filter()
            self._mark_unsaved()
            self._set_status(f"Deleted: {entry.word}  [{entry.code}]")

    # ---- tree helpers ----

    def _populate_tree(self, entries: List[LexEntry]):
        self._tree.delete(*self._tree.get_children())
        for i, e in enumerate(entries):
            tag = "odd" if i % 2 == 0 else "even"
            self._tree.insert("", tk.END, values=(e.word, e.code, e.priority), tags=(tag,))
        self._result_count.config(
            text=f"{len(entries):,} / {len(self._all_entries):,}"
        )

    def _apply_filter(self):
        q = self._search_var.get().strip().lower()
        mode = self._mode_var.get()
        if not q:
            self._populate_tree(self._all_entries)
            return
        out: List[LexEntry] = []
        for e in self._all_entries:
            if mode == "word" and q in e.word.lower():
                out.append(e)
            elif mode == "code" and q in e.code.lower():
                out.append(e)
            elif mode == "all" and (q in e.word.lower() or q in e.code.lower()):
                out.append(e)
        self._populate_tree(out)

    def _clear_search(self):
        self._search_var.set("")

    def _sort(self, col: str):
        rev = self._sort_rev.get(col, False)
        self._sort_rev[col] = not rev
        if col == "priority":
            self._all_entries.sort(key=lambda e: e.priority, reverse=rev)
        elif col == "word":
            self._all_entries.sort(key=lambda e: e.word, reverse=rev)
        else:
            self._all_entries.sort(key=lambda e: e.code, reverse=rev)
        self._apply_filter()

    def _selected_entry(self) -> Tuple[Optional[LexEntry], int]:
        sel = self._tree.selection()
        if not sel:
            return None, -1
        vals = self._tree.item(sel[0], "values")
        if not vals:
            return None, -1
        word, code = vals[0], vals[1]
        for i, e in enumerate(self._all_entries):
            if e.word == word and e.code == code:
                return e, i
        return None, -1

    # ---- misc ----

    def _mark_unsaved(self):
        self._unsaved = True
        if self.lex.filepath:
            self.root.title(f"Wubi .lex Editor — {self.lex.filepath} *")

    def _mark_saved(self):
        self._unsaved = False
        if self.lex.filepath:
            self.root.title(f"Wubi .lex Editor — {self.lex.filepath}")
        else:
            self.root.title("Wubi .lex Editor")

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _on_close(self):
        if self._unsaved:
            ans = messagebox.askyesnocancel(
                "Unsaved changes",
                "There are unsaved changes. Save before closing?",
            )
            if ans is None:
                return
            if ans:
                self.cmd_save()
        self.root.destroy()


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _match(entry: LexEntry, key: str, by: str) -> bool:
    key = key.lower()
    if by == "code":  return key in entry.code.lower()
    if by == "word":  return key in entry.word.lower()
    return key in entry.code.lower() or key in entry.word.lower()


def _fmt_table(entries: List[LexEntry]) -> str:
    if not entries:
        return "(no entries)"
    w = max(len(e.word) for e in entries)
    c = max(len(e.code) for e in entries)
    w, c = max(w, 4), max(c, 4)
    sep = f"+{'-'*(w+2)}+{'-'*(c+2)}+{'-'*10}+"
    hdr = f"| {'Word':<{w}} | {'Code':<{c}} | {'Priority':>8} |"
    rows = [sep, hdr, sep]
    for e in entries:
        rows.append(f"| {e.word:<{w}} | {e.code:<{c}} | {e.priority:>8} |")
    rows.append(sep)
    return "\n".join(rows)


def _fmt_csv(entries: List[LexEntry]) -> str:
    lines = ["word,code,priority"]
    for e in entries:
        word = e.word.replace('"', '""')
        lines.append(f'"{word}",{e.code},{e.priority}')
    return "\n".join(lines)


def _fmt_json(entries: List[LexEntry]) -> str:
    return json.dumps(
        [{"word": e.word, "code": e.code, "priority": e.priority} for e in entries],
        ensure_ascii=False, indent=2
    )


def _print_entries(entries: List[LexEntry], fmt: str):
    if fmt == "csv":
        print(_fmt_csv(entries))
    elif fmt == "json":
        print(_fmt_json(entries))
    else:
        print(_fmt_table(entries))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

USAGE_EXAMPLES = """
examples:
  # GUI (no --op)
  python lex_editor.py
  python lex_editor.py --input user.lex

  # list all entries
  python lex_editor.py --input user.lex --op list
  python lex_editor.py --input user.lex --op list --format json

  # search
  python lex_editor.py --input user.lex --op search --query 茅
  python lex_editor.py --input user.lex --op search --query acbb --by code
  python lex_editor.py --input user.lex --op search --query 茅 --format csv

  # add new entry
  python lex_editor.py --input user.lex --output user.lex --op add --code wxyz --word 新词
  python lex_editor.py --input user.lex --output user.lex --op add --code wxyz --word 新词 --priority 55000

  # edit entry  (--key matches code by default; use --by to match word)
  python lex_editor.py --input user.lex --output out.lex --op edit --key acbb --value 茅草地
  python lex_editor.py --input user.lex --output out.lex --op edit --key acbb --value 茅草地 --newcode abcd
  python lex_editor.py --input user.lex --output out.lex --op edit --key 茅子 --by word --value 茅草地

  # edit multiple keys at once (--key / --value pairs are matched positionally)
  python lex_editor.py --input user.lex --output user.lex --op edit --key now --value 今天 --key date --value 日期

  # delete entry (single or multiple keys)
  python lex_editor.py --input user.lex --output user.lex --op del --key acbb
  python lex_editor.py --input user.lex --output user.lex --op del --key 茅子 --by word
  python lex_editor.py --input user.lex --output user.lex --op del --key foo --key bar
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lex_editor.py",
        description="Wubi .lex file editor — GUI mode (no --op) or CLI mode (--op).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=USAGE_EXAMPLES,
    )

    p.add_argument("--input",  "-i", metavar="FILE",
                   help="Input .lex file path.")
    p.add_argument("--output", "-o", metavar="FILE",
                   help="Output .lex file path. Defaults to --input (in-place) for "
                        "write ops if omitted.")
    p.add_argument("--op", metavar="OP",
                   choices=["list", "search", "add", "edit", "del"],
                   help="Operation: list | search | add | edit | del  "
                        "(omit to launch GUI).")

    # -- search / match options
    p.add_argument("--query", "-q", metavar="TEXT",
                   help="Search query for --op search.")
    p.add_argument("--by", metavar="FIELD",
                   choices=["code", "word", "all"], default="code",
                   help="Field to match --key / --query against: "
                        "code (default) | word | all.")
    p.add_argument("--format", "-f", metavar="FMT",
                   choices=["table", "csv", "json"], default="table",
                   help="Output format for list/search: table (default) | csv | json.")

    # -- add / edit options
    p.add_argument("--code", metavar="CODE",
                   help="Wubi code (≤4 chars) for --op add.")
    p.add_argument("--word", metavar="WORD",
                   help="Word/phrase for --op add.")
    p.add_argument("--priority", metavar="N", type=int, default=60000,
                   help="Priority for --op add (default: 60000).")

    # -- edit options
    p.add_argument("--key", "-k", metavar="KEY", action="append", dest="key",
                   help="Key to find entry for --op edit / del "
                        "(matched against --by field). "
                        "Repeat to target multiple entries: --key k1 --value v1 --key k2 --value v2.")
    p.add_argument("--value", "-v", metavar="WORD", action="append", dest="value",
                   help="New word value for --op edit. "
                        "Must appear the same number of times as --key.")
    p.add_argument("--newcode", metavar="CODE",
                   help="New code for --op edit (optional; applies when a single --key is given).")

    return p


def cli_main(args) -> int:
    """Run a single CLI operation. Returns exit code."""
    # ---- load input file ----
    if not args.input:
        print("error: --input FILE is required for CLI mode.", file=sys.stderr)
        return 1
    if not os.path.isfile(args.input):
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 1

    lf = LexFile()
    try:
        lf.read(args.input)
    except Exception as exc:
        print(f"error reading {args.input}: {exc}", file=sys.stderr)
        return 1

    op = args.op

    # ------------------------------------------------------------------ list
    if op == "list":
        _print_entries(lf.entries, args.format)
        print(f"\n{len(lf.entries)} entries total.", file=sys.stderr)
        return 0

    # ---------------------------------------------------------------- search
    if op == "search":
        if not args.query:
            print("error: --query TEXT is required for --op search.", file=sys.stderr)
            return 1
        hits = [e for e in lf.entries if _match(e, args.query, args.by)]
        _print_entries(hits, args.format)
        print(f"\n{len(hits)} / {len(lf.entries)} entries matched.", file=sys.stderr)
        return 0

    # ------------------------------------------------------------------- add
    if op == "add":
        if not args.code or not args.word:
            print("error: --code and --word are required for --op add.", file=sys.stderr)
            return 1
        code = args.code[:4].lower()
        new_entry = LexEntry(word=args.word, code=code, priority=args.priority)
        # check for duplicate (same code + word)
        if any(e.code == code and e.word == args.word for e in lf.entries):
            print(f"warning: entry already exists: code={code!r} word={args.word!r}",
                  file=sys.stderr)
        lf.entries.append(new_entry)
        out = _save(lf, args)
        if out is None:
            return 1
        print(f"added: code={code!r}  word={args.word!r}  ->  {out}")
        return 0

    # ------------------------------------------------------------------ edit
    if op == "edit":
        keys   = args.key   or []
        values = args.value or []
        if not keys:
            print("error: --key KEY is required for --op edit.", file=sys.stderr)
            return 1
        if values and len(keys) != len(values):
            print(
                f"error: number of --key ({len(keys)}) and --value ({len(values)}) must match.",
                file=sys.stderr,
            )
            return 1
        if not values and not args.newcode:
            print(
                "error: at least one of --value / --newcode is required for --op edit.",
                file=sys.stderr,
            )
            return 1

        total_changed = 0
        for i, key in enumerate(keys):
            new_word = values[i] if i < len(values) else None
            # --newcode only applied when it uniquely maps (single key, or first key)
            new_code = args.newcode[:4].lower() if args.newcode else None
            hits = [e for e in lf.entries if _match(e, key, args.by)]
            if not hits:
                print(f"warning: no entries matched key={key!r} by={args.by}",
                      file=sys.stderr)
                continue
            for e in hits:
                old = repr(e)
                if new_word:
                    e.word = new_word
                if new_code:
                    e.code = new_code
                print(f"edited: {old}  ->  {e!r}")
            total_changed += len(hits)

        if total_changed == 0:
            print("error: no entries were changed.", file=sys.stderr)
            return 1
        out = _save(lf, args)
        if out is None:
            return 1
        print(f"saved {total_changed} change(s) -> {out}")
        return 0

    # ------------------------------------------------------------------- del
    if op == "del":
        keys = args.key or []
        if not keys:
            print("error: --key KEY is required for --op del.", file=sys.stderr)
            return 1
        before  = len(lf.entries)
        removed = [e for e in lf.entries if any(_match(e, k, args.by) for k in keys)]
        if not removed:
            key_repr = ", ".join(repr(k) for k in keys)
            print(f"error: no entries matched key(s) {key_repr} by={args.by}",
                  file=sys.stderr)
            return 1
        lf.entries = [e for e in lf.entries
                      if not any(_match(e, k, args.by) for k in keys)]
        out = _save(lf, args)
        if out is None:
            return 1
        for e in removed:
            print(f"deleted: {e!r}")
        print(f"saved {len(removed)} deletion(s) ({before} -> {len(lf.entries)}) -> {out}")
        return 0

    return 0


def _save(lf: LexFile, args) -> Optional[str]:
    """Save to args.output (or args.input if no output). Returns path or None on error."""
    dest = args.output or args.input
    try:
        lf.save(dest)
        return dest
    except Exception as exc:
        print(f"error saving {dest}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    # CLI mode: any --op given
    if args.op:
        sys.exit(cli_main(args))

    # GUI mode
    root = tk.Tk()
    app = LexEditorApp(root)

    # pre-load --input if provided, otherwise try user.lex next to this script
    if args.input:
        app._load_file(args.input)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        auto_load = os.path.join(here, "user.lex")
        if os.path.isfile(auto_load):
            app._load_file(auto_load)

    root.mainloop()


if __name__ == "__main__":
    main()
