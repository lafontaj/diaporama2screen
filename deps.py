#!/usr/bin/env python3
"""
deps.py — External programs the application relies on.

Nothing here is imported at start-up for its own sake: the check is cheap and
its only purpose is to fail with a sentence a human can act on, rather than
with a traceback in the middle of an encoding run.
"""
__version__ = "1.1.0"   # version propre à CE fichier ; incrémentée quand il change

import shutil

try:
    from i18n import _
except ImportError:
    def _(s):
        return s


def N_(text):
    """Marks a string for extraction without translating it here.

    The purposes below are stored in a dictionary and only translated when a
    report is built. xgettext cannot see a translation that happens through a
    variable, so the string is marked at the place it is written instead."""
    return text


# Program -> what it is needed for, and the Debian/Ubuntu package providing it
TOOLS = {
    "exiftool": (N_("reading the captions"), "libimage-exiftool-perl"),
    "convert": (N_("laying out the images"), "imagemagick"),
    "identify": (N_("measuring the caption band"), "imagemagick"),
    "ffmpeg": (N_("encoding the video"), "ffmpeg"),
    "ffprobe": (N_("inspecting the music files"), "ffmpeg"),
}

# What each stage of the workflow actually needs
FOR_CAPTIONS = ("exiftool",)
FOR_IMAGES = ("convert", "identify")
FOR_VIDEO = ("ffmpeg", "ffprobe")


def missing(names=None):
    """Return the list of programs that are not on PATH."""
    names = names if names is not None else tuple(TOOLS)
    return [n for n in names if shutil.which(n) is None]


def packages_for(names):
    """Return the sorted set of packages that would provide these programs."""
    return sorted({TOOLS[n][1] for n in names if n in TOOLS})


def report(names=None):
    """Human-readable sentence about what is missing, or '' when all is well."""
    absent = missing(names)
    if not absent:
        return ""
    pkgs = " ".join(packages_for(absent))
    lines = [_("Some required programs are missing:")]
    for n in absent:
        purpose = TOOLS.get(n, ("", ""))[0]
        lines.append("  - {name} ({purpose})".format(name=n, purpose=_(purpose)))
    lines.append("")
    lines.append(_("Install them with:"))
    lines.append("  sudo apt install " + pkgs)
    return "\n".join(lines)
