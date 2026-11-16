#!/usr/bin/env python3
"""
tags.py — Finding photographs by the tags written into their files.

A selection made in digiKam — by tag, by face, by whatever its search can
do — reaches this application through the files themselves rather than
through digiKam's database. digiKam writes its tags into the photograph's
XMP and IPTC fields, so a folder can be swept with exiftool and every tag
it holds recovered, with the files that carry it.

That choice mirrors the one made for captions: what the application acts on
is what is actually on disk. A tagged selection therefore survives a rebuilt
catalogue, a move to another machine, or a change of cataloguing program,
and stays readable by any tool that can read a photograph.

Four fields are consulted, because taggers do not agree:

  XMP:TagsList            digiKam, hierarchical, "Events/Slideshow"
  XMP:HierarchicalSubject Lightroom's spelling of the same, "Events|Slideshow"
  XMP:Subject             the flat keyword
  IPTC:Keywords           the older flat keyword

digiKam usually writes all four, which would show the same tag twice — once
by its full path and once by its leaf. The leaf is dropped when some
hierarchical tag already ends with it, so the list shows one entry per tag.
"""
__version__ = "1.0.0"   # version propre à CE fichier ; incrémentée quand il change

import json
import os
import subprocess
import threading

IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "tif", "tiff")

HIERARCHICAL_FIELDS = ("TagsList", "HierarchicalSubject")
FLAT_FIELDS = ("Subject", "Keywords")

# A hierarchy is written with "/" by digiKam and "|" by Lightroom.
SEPARATORS = ("|", "/")


def _values(entry, field):
    """The values of one exiftool field, as a list of non-empty strings.
    exiftool gives a string for a single value and a list for several."""
    raw = entry.get(field)
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    elif not isinstance(raw, (list, tuple)):
        raw = [str(raw)]
    return [str(v).strip() for v in raw if str(v).strip()]


def _canonical(label):
    """A hierarchical tag written with one separator."""
    for sep in SEPARATORS:
        label = label.replace(sep, "/")
    return "/".join(part.strip() for part in label.split("/") if part.strip())


class TagScan:
    """One sweep of a folder. Blocking, cancellable, never raises."""

    def __init__(self, folder, recursive=True, timeout=1800):
        self.folder = folder
        self.recursive = recursive
        self.timeout = timeout
        self._lock = threading.Lock()
        self._process = None
        self._cancelled = False

    def cancel(self):
        """Stop the sweep. Safe to call from another thread, and safe to
        call when the sweep has not started or has already finished."""
        with self._lock:
            self._cancelled = True
            process = self._process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    def _command(self):
        args = ["exiftool", "-j", "-q", "-q", "-charset", "filename=utf8"]
        for field in HIERARCHICAL_FIELDS + FLAT_FIELDS:
            args.append("-" + field)
        if self.recursive:
            args.append("-r")
        for extension in IMAGE_EXTENSIONS:
            args += ["-ext", extension]
        args.append(self.folder)
        return args

    def run(self):
        """Sweep the folder.

        Returns (tags, files, error): `tags` maps a tag to the sorted list of
        files carrying it, `files` is how many photographs were read, and
        `error` is an empty string unless the sweep could not be done."""
        if not os.path.isdir(self.folder):
            return {}, 0, "folder"

        try:
            process = subprocess.Popen(
                self._command(), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return {}, 0, "exiftool"

        with self._lock:
            if self._cancelled:            # cancelled before it started
                process.terminate()
                return {}, 0, "cancelled"
            self._process = process

        try:
            out, _err = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self.cancel()
            return {}, 0, "timeout"
        finally:
            with self._lock:
                self._process = None

        if self._cancelled:
            return {}, 0, "cancelled"
        if not out or not out.strip():
            return {}, 0, ""

        try:
            entries = json.loads(out)
        except ValueError:
            return {}, 0, "output"

        return self._collect(entries)

    @staticmethod
    def _collect(entries):
        """Group the files by tag, dropping the leaf duplicates."""
        hierarchical = {}
        flat = {}
        files = 0

        for entry in entries:
            path = entry.get("SourceFile")
            if not path:
                continue
            files += 1
            for field in HIERARCHICAL_FIELDS:
                for value in _values(entry, field):
                    label = _canonical(value)
                    if label:
                        hierarchical.setdefault(label, set()).add(path)
            for field in FLAT_FIELDS:
                for value in _values(entry, field):
                    label = _canonical(value)
                    if label:
                        flat.setdefault(label, set()).add(path)

        # A flat keyword that is the leaf of exactly one hierarchical tag is
        # the same tag, written twice: its files join that tag rather than
        # forming a second entry. Merging matters — a photograph may carry
        # only the keyword, and dropping it would lose that photograph. When
        # two hierarchies end with the same leaf the keyword is ambiguous,
        # so it is left standing on its own and the user decides.
        by_leaf = {}
        for label in hierarchical:
            by_leaf.setdefault(label.rsplit("/", 1)[-1], []).append(label)

        tags = {label: set(paths) for label, paths in hierarchical.items()}
        for label, paths in flat.items():
            owners = by_leaf.get(label, [])
            if len(owners) == 1:
                tags[owners[0]] |= paths
            elif label not in tags:
                tags[label] = set(paths)

        return ({label: sorted(paths) for label, paths in tags.items()},
                files, "")
