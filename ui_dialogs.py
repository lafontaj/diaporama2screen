#!/usr/bin/env python3
"""
ui_dialogs.py — File selectors and message boxes.

Two engines, one reason each.

File selection goes through zenity when it is present: Tk's own selector lays
files out in horizontal columns with a horizontal scrollbar, which is
unpleasant to use and does not show the places and network shortcuts of the
desktop. Tk's filedialog remains the fallback on a machine without zenity, and
the API here is the same either way.

Messages use a small dialog of our own rather than tkinter.messagebox, whose
Motif-era look sits badly in the window.
"""
__version__ = "1.4.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

import i18n

try:
    from i18n import _
except ImportError:
    def _(s):
        return s

_ZENITY = shutil.which("zenity")
_WMCTRL = shutil.which("wmctrl")
APP_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_FILTER = "*.jpg *.jpeg *.JPG *.JPEG *.png *.PNG *.tif *.tiff"
AUDIO_FILTER = "*.flac *.mp3 *.m4a *.ogg *.opus *.wav"


# ------------------------------------------------------------------
# zenity plumbing
# ------------------------------------------------------------------

def _wmctrl(args):
    """Run wmctrl and return its output, or '' when anything goes wrong."""
    try:
        done = subprocess.run([_WMCTRL] + args, capture_output=True,
                              text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout


def _find_window(title):
    """The X11 id and size of the window whose title contains `title`.

    `wmctrl -lG` lists one window per line: id, desktop, x, y, width, height,
    client machine, then the title — which is the only field that may itself
    contain spaces, hence the limited split."""
    for line in _wmctrl(["-lG"]).splitlines():
        parts = line.split(None, 7)
        if len(parts) < 8 or title not in parts[7]:
            continue
        try:
            return parts[0], int(parts[4]), int(parts[5])
        except ValueError:
            return parts[0], 0, 0
    return None, 0, 0


def _settle_window(title, parent_box):
    """Put a freshly opened zenity window in front, centred on its caller.

    Two separate ailments are treated here. A window that appears while
    another program holds a pointer grab is refused the foreground, so it is
    asked for by name. And zenity lets the window manager choose its
    position, which on Muffin means the top-left corner of the screen rather
    than the middle of the window it belongs to.

    The work happens in a thread because zenity is still being waited on, and
    it reads nothing from Tk: the caller's geometry is measured beforehand and
    passed in, since Tk must only ever be touched from the main thread."""
    if not _WMCTRL or not title:
        return

    def later():
        deadline = time.time() + 3.0
        while time.time() < deadline:
            time.sleep(0.2)
            wid, width, height = _find_window(title)
            if not wid:
                continue
            if parent_box and width and height:
                px, py, pw, ph = parent_box
                x = max(0, px + (pw - width) // 2)
                y = max(0, py + (ph - height) // 3)
                _wmctrl(["-i", "-r", wid, "-e",
                         "0,{},{},-1,-1".format(x, y)])
            _wmctrl(["-i", "-a", wid])
            return

    threading.Thread(target=later, daemon=True).start()


def _box(parent):
    """Position and size of the calling window, measured in the main thread."""
    if parent is None:
        return None
    try:
        top = parent.winfo_toplevel()
        return (top.winfo_rootx(), top.winfo_rooty(),
                top.winfo_width(), top.winfo_height())
    except Exception:
        return None


def _zenity(args, multiple=False, parent_box=None):
    """Run zenity. Returns the chosen path, a list when multiple, or None.
    The locale environment follows the language chosen in the application, so
    zenity's own buttons match the rest of the window."""
    try:
        env = i18n.subprocess_env()
    except Exception:
        env = None
    title = ""
    if "--title" in args:
        index = args.index("--title")
        if index + 1 < len(args):
            title = args[index + 1]
    try:
        process = subprocess.Popen([_ZENITY] + args, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True,
                                   env=env)
    except Exception:
        return [] if multiple else None
    _settle_window(title, parent_box)
    try:
        out_text, _err = process.communicate()
    except Exception:
        return [] if multiple else None
    proc = subprocess.CompletedProcess([], process.returncode, out_text, "")
    if proc.returncode != 0:          # cancelled
        return [] if multiple else None
    out = proc.stdout.strip()
    if not out:
        return [] if multiple else None
    if multiple:
        return [p for p in out.split("\n") if p]
    return out


def _window_icon():
    """The application icon, for zenity's own title bar. Without it zenity
    shows its default cog, which looks like a stray system dialog."""
    for size in (128, 64, 48):
        candidate = os.path.join(APP_DIR, "icons",
                                 "diaporama2screen-{}.png".format(size))
        if os.path.isfile(candidate):
            return candidate
    return ""


def _window_id(parent):
    """The X11 window of the calling window, so the selector can be attached
    to it. Without this the window manager treats zenity as an unrelated
    application and is free to put it behind, or to leave it minimised."""
    if parent is None:
        return ""
    try:
        return str(parent.winfo_toplevel().winfo_id())
    except Exception:
        return ""


def _common(parent, title):
    """Title, modality, parent and icon — what every selector should carry."""
    args = ["--title", title, "--modal"]
    icon = _window_icon()
    if icon:
        args += ["--window-icon", icon]
    xid = _window_id(parent)
    if xid:
        args += ["--attach", xid]
    return args


def _start(path):
    """A starting location zenity understands (trailing slash = directory)."""
    if not path:
        return os.path.expanduser("~") + "/"
    if os.path.isdir(path):
        return path.rstrip("/") + "/"
    return path


# ------------------------------------------------------------------
# selectors
# ------------------------------------------------------------------

def pick_directory(parent=None, title=None, initialdir=None):
    """Choose one folder."""
    title = title or _("Choose a folder")
    if _ZENITY:
        return _zenity(["--file-selection", "--directory"]
                       + _common(parent, title)
                       + ["--filename", _start(initialdir)],
                       parent_box=_box(parent))
    return filedialog.askdirectory(parent=parent, title=title,
                                   initialdir=initialdir) or None


def pick_images(parent=None, title=None, initialdir=None):
    """Choose one or several image files. Returns a list, possibly empty."""
    title = title or _("Add photos")
    if _ZENITY:
        return _zenity(["--file-selection", "--multiple", "--separator", "\n"]
                       + _common(parent, title)
                       + ["--filename", _start(initialdir),
                          "--file-filter", _("Images") + " | " + IMAGE_FILTER,
                          "--file-filter", _("All files") + " | *"],
                       multiple=True, parent_box=_box(parent))
    names = filedialog.askopenfilenames(
        parent=parent, title=title, initialdir=initialdir,
        filetypes=[(_("Images"), IMAGE_FILTER), (_("All files"), "*")])
    return list(names)


def pick_audio(parent=None, title=None, initialdir=None):
    """Choose one or several music files. Returns a list, possibly empty."""
    title = title or _("Add music files")
    if _ZENITY:
        return _zenity(["--file-selection", "--multiple", "--separator", "\n"]
                       + _common(parent, title)
                       + ["--filename", _start(initialdir),
                          "--file-filter", _("Audio files") + " | " + AUDIO_FILTER,
                          "--file-filter", _("All files") + " | *"],
                       multiple=True, parent_box=_box(parent))
    names = filedialog.askopenfilenames(
        parent=parent, title=title, initialdir=initialdir,
        filetypes=[(_("Audio files"), AUDIO_FILTER), (_("All files"), "*")])
    return list(names)


def pick_open(parent=None, title=None, initialdir=None, pattern="*",
              pattern_label=None):
    """Choose one existing file."""
    title = title or _("Open")
    if _ZENITY:
        args = (["--file-selection"] + _common(parent, title)
                + ["--filename", _start(initialdir)])
        if pattern != "*":
            args += ["--file-filter",
                     (pattern_label or pattern) + " | " + pattern,
                     "--file-filter", _("All files") + " | *"]
        return _zenity(args, parent_box=_box(parent))
    types = ([(pattern_label or pattern, pattern)] if pattern != "*" else []) \
        + [(_("All files"), "*")]
    return filedialog.askopenfilename(parent=parent, title=title,
                                      initialdir=initialdir,
                                      filetypes=types) or None


def pick_save(parent=None, title=None, initialdir=None, initialfile="",
              suffix="", pattern="*", pattern_label=None):
    """Choose where to write a file. The suffix is appended when the user did
    not type it; an existing file is then re-confirmed, because zenity's own
    confirmation applies to the name as typed."""
    title = title or _("Save as")
    if _ZENITY:
        start = os.path.join(initialdir or os.path.expanduser("~"),
                             initialfile)
        args = (["--file-selection", "--save", "--confirm-overwrite"]
                + _common(parent, title) + ["--filename", start])
        if pattern != "*":
            args += ["--file-filter",
                     (pattern_label or pattern) + " | " + pattern,
                     "--file-filter", _("All files") + " | *"]
        path = _zenity(args, parent_box=_box(parent))
        if path and suffix and not path.lower().endswith(suffix.lower()):
            path += suffix
            if os.path.exists(path):
                if not confirm(parent,
                               _("The file “{f}” already exists. Replace it?")
                               .format(f=os.path.basename(path)),
                               ok_text=_("Replace")):
                    return None
        return path
    types = ([(pattern_label or pattern, pattern)] if pattern != "*" else []) \
        + [(_("All files"), "*")]
    return filedialog.asksaveasfilename(
        parent=parent, title=title, initialdir=initialdir,
        initialfile=initialfile, defaultextension=suffix,
        filetypes=types) or None


# ------------------------------------------------------------------
# messages
# ------------------------------------------------------------------

_MARKS = {
    "info": ("i", "#2d6cdf"),
    "success": ("✔", "#1e7a34"),
    "warning": ("!", "#b06a00"),
    "error": ("✘", "#b00020"),
    "question": ("?", "#2d6cdf"),
}


class _Dialog(tk.Toplevel):
    """A modal message box that looks like the rest of the window."""

    def __init__(self, parent, message, kind="info", title=None,
                 ok_text=None, cancel_text=None):
        super().__init__(parent)
        self.result = False
        self.title(title or "diaporama2screen")
        self.resizable(False, False)
        self.transient(parent)
        # Built out of sight, then shown where it belongs: a window that is
        # mapped first and moved afterwards is seen to jump across the screen.
        self.withdraw()

        body = ttk.Frame(self, padding=(18, 16))
        body.pack(fill="both", expand=True)

        mark, colour = _MARKS.get(kind, _MARKS["info"])
        badge = tk.Label(body, text=mark, foreground="white",
                         background=colour, width=3, font=("", 14, "bold"))
        badge.grid(row=0, column=0, sticky="n", padx=(0, 14), pady=(2, 0))

        label = ttk.Label(body, text=message, justify="left", wraplength=460)
        label.grid(row=0, column=1, sticky="w")

        self._extra(body, 1)

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(18, 0))
        if cancel_text:
            ttk.Button(buttons, text=cancel_text,
                       command=self._cancel).pack(side="right", padx=(8, 0))
        ok = ttk.Button(buttons, text=ok_text or _("OK"), command=self._ok)
        ok.pack(side="right")
        ok.focus_set()

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        self._centre(parent)
        self.deiconify()
        self.grab_set()
        self.wait_window(self)

    def _extra(self, body, row):
        """Hook for subclasses that add a widget between text and buttons."""

    def _centre(self, parent):
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        except Exception:
            px = py = 0
            pw = ph = 0
        # The requested size, not the current one: the window is still hidden
        # at this point and an unmapped window measures one pixel wide.
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 3)
        self.geometry("+{}+{}".format(x, y))

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


def info(parent, message, title=None):
    _Dialog(parent, message, "info", title)


def success(parent, message, title=None):
    _Dialog(parent, message, "success", title)


def warning(parent, message, title=None):
    _Dialog(parent, message, "warning", title)


def error(parent, message, title=None):
    _Dialog(parent, message, "error", title)


def confirm(parent, message, title=None, ok_text=None, cancel_text=None,
            kind="question"):
    """Yes/Cancel. Returns True when confirmed."""
    d = _Dialog(parent, message, kind, title,
                ok_text=ok_text or _("Yes"),
                cancel_text=cancel_text or _("Cancel"))
    return d.result


class _WithOption(_Dialog):
    """A confirmation carrying one tick box, for a choice that belongs with
    the question rather than in a settings panel."""

    def __init__(self, parent, message, option_text, option_default,
                 title=None, ok_text=None, cancel_text=None, kind="warning"):
        self.option = tk.BooleanVar(value=option_default)
        self._option_text = option_text
        super().__init__(parent, message, kind, title, ok_text, cancel_text)

    def _extra(self, body, row):
        ttk.Checkbutton(body, text=self._option_text,
                        variable=self.option).grid(row=row, column=1,
                                                   sticky="w", pady=(12, 0))


def confirm_with_option(parent, message, option_text, option_default=True,
                        title=None, ok_text=None, cancel_text=None,
                        kind="warning"):
    """Returns (confirmed, option_state)."""
    d = _WithOption(parent, message, option_text, option_default, title,
                    ok_text or _("Yes"), cancel_text or _("Cancel"), kind)
    return d.result, bool(d.option.get())


class _ThreeWay(_Dialog):
    """Save / Discard / Cancel, for the unsaved-changes question."""

    def __init__(self, parent, message, title, save_text, discard_text,
                 cancel_text):
        self.answer = None
        tk.Toplevel.__init__(self, parent)
        self.result = False
        self.title(title or "diaporama2screen")
        self.resizable(False, False)
        self.transient(parent)
        # Built out of sight, then shown where it belongs: a window that is
        # mapped first and moved afterwards is seen to jump across the screen.
        self.withdraw()

        body = ttk.Frame(self, padding=(18, 16))
        body.pack(fill="both", expand=True)
        mark, colour = _MARKS["question"]
        tk.Label(body, text=mark, foreground="white", background=colour,
                 width=3, font=("", 14, "bold")).grid(
            row=0, column=0, sticky="n", padx=(0, 14), pady=(2, 0))
        ttk.Label(body, text=message, justify="left",
                  wraplength=460).grid(row=0, column=1, sticky="w")

        buttons = ttk.Frame(body)
        buttons.grid(row=1, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text=cancel_text,
                   command=lambda: self._set(None)).pack(side="right",
                                                         padx=(8, 0))
        ttk.Button(buttons, text=discard_text,
                   command=lambda: self._set(False)).pack(side="right",
                                                          padx=(8, 0))
        save = ttk.Button(buttons, text=save_text,
                          command=lambda: self._set(True))
        save.pack(side="right")
        save.focus_set()

        self.bind("<Escape>", lambda e: self._set(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self._set(None))
        self.update_idletasks()
        self._centre(parent)
        self.deiconify()
        self.grab_set()
        self.wait_window(self)

    def _set(self, value):
        self.answer = value
        self.destroy()


def ask_save_discard_cancel(parent, message, title=None):
    """True = save, False = discard, None = cancel."""
    d = _ThreeWay(parent, message, title, _("Save"), _("Discard"),
                  _("Cancel"))
    return d.answer
