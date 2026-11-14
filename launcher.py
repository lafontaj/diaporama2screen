#!/usr/bin/env python3
"""
launcher.py — Putting the application in the menu and on the desktop.

Writes a freedesktop .desktop file into the user's own applications folder,
so it appears in the Graphics group of the menu, and optionally copies it to
the desktop.

Two details matter on Cinnamon and GNOME and are easy to miss: a launcher
dropped on the desktop must be executable, and it must carry the
metadata::trusted attribute, or the desktop shows "Untrusted application
launcher" and refuses to start it.
"""
__version__ = "1.0.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import shutil
import subprocess
import sys

try:
    from i18n import _
except ImportError:
    def _(s):
        return s

APP_ID = "diaporama2screen"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ENTRY_POINT = os.path.join(APP_DIR, "diaporama2screen.py")
ICON_DIR = os.path.join(APP_DIR, "icons")

NAME = "diaporama2screen"
GENERIC_EN = "Photo slideshow"
GENERIC_FR = "Diaporama photo"
COMMENT_EN = "Build a photo slideshow with captions, ready for a television"
COMMENT_FR = ("Monter un diaporama photo avec légendes, prêt pour un "
              "téléviseur")


def icon_path():
    """The largest icon that exists, or '' when none is installed."""
    for size in (512, 256, 128, 64, 48):
        candidate = os.path.join(ICON_DIR,
                                 "{}-{}.png".format(APP_ID, size))
        if os.path.isfile(candidate):
            return candidate
    return ""


def applications_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "applications")


def desktop_dir():
    """The desktop folder, whatever its name in the user's language."""
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                             capture_output=True, text=True, timeout=5)
        path = out.stdout.strip()
        if path and os.path.isdir(path):
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    for name in ("Bureau", "Desktop"):
        candidate = os.path.expanduser("~/" + name)
        if os.path.isdir(candidate):
            return candidate
    return ""


def contents():
    """The text of the .desktop file."""
    icon = icon_path() or APP_ID
    exec_line = "{python} {script}".format(
        python=shutil.which("python3") or sys.executable, script=ENTRY_POINT)
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=" + NAME,
        "GenericName=" + GENERIC_EN,
        "GenericName[fr]=" + GENERIC_FR,
        "Comment=" + COMMENT_EN,
        "Comment[fr]=" + COMMENT_FR,
        "Exec=" + exec_line,
        "Icon=" + icon,
        "Path=" + APP_DIR,
        "Terminal=false",
        "Categories=Graphics;Photography;AudioVideo;",
        "Keywords=slideshow;photo;video;diaporama;",
        "StartupNotify=true",
        "",
    ])


def _write(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o755)


def _trust(path):
    """Mark a desktop launcher as trusted, which Cinnamon and GNOME require
    before they will start it. Absent gio, the user ticks it by hand."""
    try:
        subprocess.run(["gio", "set", path, "metadata::trusted", "true"],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _refresh_menu():
    directory = applications_dir()
    try:
        subprocess.run(["update-desktop-database", directory],
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass   # not every system ships it; the menu picks the file up anyway


def install(in_menu=True, on_desktop=True):
    """Create the launcher. Returns (written, problems), both lists."""
    text = contents()
    written = []
    problems = []

    if in_menu:
        target = os.path.join(applications_dir(), APP_ID + ".desktop")
        try:
            _write(target, text)
            written.append(target)
        except OSError as exc:
            problems.append(str(exc))
        else:
            _refresh_menu()

    if on_desktop:
        folder = desktop_dir()
        if not folder:
            problems.append(_("The desktop folder could not be found."))
        else:
            target = os.path.join(folder, APP_ID + ".desktop")
            try:
                _write(target, text)
                _trust(target)
                written.append(target)
            except OSError as exc:
                problems.append(str(exc))

    return written, problems


def is_installed():
    """(in the menu, on the desktop)"""
    menu = os.path.isfile(os.path.join(applications_dir(),
                                       APP_ID + ".desktop"))
    folder = desktop_dir()
    desk = bool(folder) and os.path.isfile(os.path.join(folder,
                                                        APP_ID + ".desktop"))
    return menu, desk


def remove():
    """Take the launcher away again. Returns the list of removed paths."""
    gone = []
    candidates = [os.path.join(applications_dir(), APP_ID + ".desktop")]
    folder = desktop_dir()
    if folder:
        candidates.append(os.path.join(folder, APP_ID + ".desktop"))
    for path in candidates:
        try:
            os.remove(path)
            gone.append(path)
        except OSError:
            pass
    if gone:
        _refresh_menu()
    return gone
