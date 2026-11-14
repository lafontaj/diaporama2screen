#!/usr/bin/env python3
"""
metadata.py — Reading the caption and the capture date from image files.

Captions are read from the file itself, never from a catalogue database, so
that what the application shows is what digiKam actually wrote to disk.

Reading is done in ONE exiftool call for the whole list. Calling exiftool once
per file costs about a tenth of a second each: imperceptible on ten photos,
half a minute on three hundred.

This module never writes. Writing captions back into the user's own archive
belongs to a separate, explicit action (see write_caption, which is deliberate
and confirmed by the caller).
"""
__version__ = "1.1.0"   # version propre à CE fichier ; incrémentée quand il change

import json
import os
import subprocess
import tempfile

try:
    from i18n import _
except ImportError:
    def _(s):
        return s

# Fields read, in order of preference. digiKam writes the first three.
CAPTION_FIELDS = ("Caption-Abstract", "Description", "ImageDescription")
DATE_FIELDS = ("DateTimeOriginal", "CreateDate", "FileModifyDate")

_READ_ARGS = [
    "exiftool", "-j", "-charset", "filename=utf8",
    "-IPTC:Caption-Abstract", "-XMP:Description", "-EXIF:ImageDescription",
    "-EXIF:DateTimeOriginal", "-EXIF:CreateDate", "-FileModifyDate",
    "-@", "-",
]


def read_many(file_paths, timeout=300):
    """Read captions and dates for a list of files in a single exiftool call.

    Returns {path: {"caption": str, "date": str}}. Files exiftool could not
    read simply get empty values; the call never raises."""
    out = {p: {"caption": "", "date": ""} for p in file_paths}
    if not file_paths:
        return out
    try:
        proc = subprocess.run(
            _READ_ARGS,
            input="\n".join(file_paths),
            capture_output=True, text=True, timeout=timeout,
        )
        entries = json.loads(proc.stdout) if proc.stdout.strip() else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return out

    for entry in entries:
        src = entry.get("SourceFile")
        if src not in out:
            continue
        caption = ""
        for field in CAPTION_FIELDS:
            value = entry.get(field)
            if isinstance(value, str) and value.strip():
                caption = value.strip()
                break
        date = ""
        for field in DATE_FIELDS:
            value = entry.get(field)
            if isinstance(value, str) and value.strip():
                date = value.strip()
                break
        out[src] = {"caption": caption, "date": date}
    return out


def read_one(file_path):
    """Convenience wrapper around read_many for a single file."""
    return read_many([file_path]).get(file_path, {"caption": "", "date": ""})


def write_many(items, keep_backup=False, timeout=900):
    """Write captions into the files themselves.

    `items` is a sequence of (path, caption). All of it goes through a single
    exiftool process driven by an argument file: one process per photo would
    cost a tenth of a second each, which is a visible freeze on a hundred.

    When `keep_backup` is true exiftool leaves the untouched original beside
    the new file, named <name>_original. Otherwise the file is rewritten in
    place and there is no way back.

    Returns (written, failures) where failures is a list of (path, reason).
    What was really written is verified by reading the files back."""
    items = [(p, (c or "").replace("\n", " ").strip()) for p, c in items]
    if not items:
        return 0, []

    lines = []
    for path, caption in items:
        if not keep_backup:
            lines.append("-overwrite_original")
        lines.append("-charset")
        lines.append("filename=utf8")
        lines.append("-codedcharacterset=utf8")
        lines.append("-IPTC:Caption-Abstract=" + caption)
        lines.append("-XMP:Description=" + caption)
        lines.append("-EXIF:ImageDescription=" + caption)
        lines.append(path)
        lines.append("-execute")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".args",
                                     delete=False) as handle:
        handle.write("\n".join(lines) + "\n")
        argfile = handle.name

    try:
        subprocess.run(["exiftool", "-@", argfile],
                       capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        os.unlink(argfile)
        return 0, [(p, str(exc)) for p, _c in items]
    finally:
        try:
            os.unlink(argfile)
        except OSError:
            pass

    # Verify rather than trust the exit code: a file that is read-only, or on
    # a share mounted read-only, fails for that one photo alone.
    back = read_many([p for p, _c in items])
    written = 0
    failures = []
    for path, caption in items:
        if back.get(path, {}).get("caption", "") == caption:
            written += 1
        else:
            failures.append((path, _("the file still holds its old caption")))
    return written, failures


def write_caption(file_path, caption, timeout=60):
    """Write a caption into the file's own metadata, in the three fields
    digiKam reads. The original is overwritten in place (no _original copy):
    the caller is responsible for warning the user first.

    Returns (True, '') on success, (False, message) otherwise."""
    args = [
        "exiftool", "-charset", "filename=utf8", "-overwrite_original",
        "-IPTC:Caption-Abstract=" + caption,
        "-XMP:Description=" + caption,
        "-EXIF:ImageDescription=" + caption,
        file_path,
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout).strip()
    return True, ""
