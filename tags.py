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
by its full path and once by its leaf. The leaf is merged into the hierarchy
ending with it rather than dropped, because a photograph may carry only the
keyword.

SPEED. A library of eighteen thousand photographs on a network share takes
about two and a half minutes to sweep with one exiftool, which is too long
to wait for a list of tags. Two things are done about it.

Several exiftool processes run at once. The cost per file is mostly waiting
for the share to answer, not computing, and waiting parallelises well:
measured on NFS, six processes did the work four times faster than one.

What was read is kept, with each file's size and modification time. A later
sweep reads only the files that are new or have changed since — which, for
a library that grows by a handful of scans at a time, is almost none of
them. The index is a cache and nothing depends on it: deleting it costs one
slow sweep, no more.
"""
__version__ = "2.0.0"   # version propre à CE fichier ; incrémentée quand il change

import json
import os
import subprocess
import threading

import paths

IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "tif", "tiff")

HIERARCHICAL_FIELDS = ("TagsList", "HierarchicalSubject")
FLAT_FIELDS = ("Subject", "Keywords")

# A hierarchy is written with "/" by digiKam and "|" by Lightroom.
SEPARATORS = ("|", "/")

DEFAULT_WORKERS = 6
INDEX_NAME = "tags-index.json"
INDEX_VERSION = 1


def index_path():
    return os.path.join(paths.cache_dir(), INDEX_NAME)


def forget_index():
    """Delete the cache. The next sweep then reads everything again."""
    try:
        os.remove(index_path())
        return True
    except OSError:
        return False


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


def _labels(entry):
    """The tags of one file, as (hierarchical, flat), both sorted."""
    hierarchical, flat = set(), set()
    for field in HIERARCHICAL_FIELDS:
        for value in _values(entry, field):
            label = _canonical(value)
            if label:
                hierarchical.add(label)
    for field in FLAT_FIELDS:
        for value in _values(entry, field):
            label = _canonical(value)
            if label:
                flat.add(label)
    return sorted(hierarchical), sorted(flat)


def _group(per_file):
    """Group files by tag. `per_file` maps a path to (hierarchical, flat)."""
    hierarchical, flat = {}, {}
    for path, (hier_labels, flat_labels) in per_file.items():
        for label in hier_labels:
            hierarchical.setdefault(label, set()).add(path)
        for label in flat_labels:
            flat.setdefault(label, set()).add(path)

    # A flat keyword that is the leaf of exactly one hierarchical tag is the
    # same tag, written twice: its files join that tag rather than forming a
    # second entry. Merging matters — a photograph may carry only the
    # keyword, and dropping it would lose that photograph. When two
    # hierarchies end with the same leaf the keyword is ambiguous, so it is
    # left standing on its own and the user decides.
    by_leaf = {}
    for label in hierarchical:
        by_leaf.setdefault(label.rsplit("/", 1)[-1], []).append(label)

    tags = {label: set(files) for label, files in hierarchical.items()}
    for label, files in flat.items():
        owners = by_leaf.get(label, [])
        if len(owners) == 1:
            tags[owners[0]] |= files
        elif label not in tags:
            tags[label] = set(files)

    return {label: sorted(files) for label, files in tags.items()}


class TagScan:
    """One sweep of a folder. Blocking, cancellable, never raises."""

    def __init__(self, folder, recursive=True, workers=DEFAULT_WORKERS,
                 use_index=True, timeout=1800):
        self.folder = folder
        self.recursive = recursive
        self.workers = max(1, int(workers))
        self.use_index = use_index
        self.timeout = timeout
        self._lock = threading.Lock()
        self._processes = set()
        self._cancelled = False

    # ---------- cancelling ----------

    def cancel(self):
        """Stop the sweep. Safe from another thread, and safe before it
        starts or after it ends."""
        with self._lock:
            self._cancelled = True
            live = list(self._processes)
        for process in live:
            try:
                process.terminate()
            except OSError:
                pass

    @property
    def cancelled(self):
        with self._lock:
            return self._cancelled

    # ---------- the files on disk ----------

    def _walk(self):
        """Every image under the folder, with its size and modification
        time. On NFS the share returns those attributes along with the
        directory listing, so this costs far less than opening each file.

        Hidden directories are left out, as they are everywhere else in the
        application. That is what keeps deleted photographs from coming
        back: digiKam moves them to a `.dtrash` folder inside the album
        root, and the desktop moves them to `.Trash-1000` or to
        `~/.local/share/Trash`. All three keep the file, and its tags, in
        place — so a sweep that walked into them would offer photographs
        their owner had thrown away."""
        found = {}
        stack = [self.folder]
        while stack:
            if self.cancelled:
                return found
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if self.recursive and not entry.name.startswith("."):
                            stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    extension = os.path.splitext(entry.name)[1].lower()
                    if extension.lstrip(".") not in IMAGE_EXTENSIONS:
                        continue
                    status = entry.stat()
                except OSError:
                    continue
                found[entry.path] = (int(status.st_mtime), status.st_size)
        return found

    # ---------- the cache ----------

    def _load_index(self):
        if not self.use_index:
            return {}
        try:
            with open(index_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("version") != INDEX_VERSION:
            return {}
        files = data.get("files")
        return files if isinstance(files, dict) else {}

    def _save_index(self, index):
        if not self.use_index:
            return
        try:
            os.makedirs(paths.cache_dir(), exist_ok=True)
            temporary = index_path() + ".new"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"version": INDEX_VERSION, "files": index}, handle)
            os.replace(temporary, index_path())
        except OSError:
            pass          # a cache that cannot be written is not an error

    # ---------- reading with exiftool ----------

    def _exiftool_args(self):
        args = ["exiftool", "-j", "-q", "-q", "-charset", "filename=utf8"]
        for field in HIERARCHICAL_FIELDS + FLAT_FIELDS:
            args.append("-" + field)
        args.append("-@")
        args.append("-")
        return args

    def _read_chunk(self, chunk):
        """Read one batch of files. Returns a list of exiftool entries."""
        if self.cancelled:
            return []
        try:
            process = subprocess.Popen(
                self._exiftool_args(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            raise RuntimeError("exiftool")

        with self._lock:
            if self._cancelled:
                process.terminate()
                return []
            self._processes.add(process)
        try:
            out, _err = process.communicate("\n".join(chunk),
                                            timeout=self.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError("timeout")
        finally:
            with self._lock:
                self._processes.discard(process)

        if not out or not out.strip():
            return []
        try:
            return json.loads(out)
        except ValueError:
            raise RuntimeError("output")

    def _read_all(self, files, progress):
        """Read every file in `files`, several exiftool at a time.

        The list is cut into more chunks than there are workers, so that a
        batch of slow files does not leave five processes idle while the
        sixth finishes, and so that progress advances more than six times."""
        results = {}
        if not files:
            return results, ""

        pieces = max(self.workers * 8, 1)
        size = max(25, (len(files) + pieces - 1) // pieces)
        chunks = [files[i:i + size] for i in range(0, len(files), size)]

        state = {"next": 0, "done": 0, "error": ""}
        lock = threading.Lock()

        def worker():
            while True:
                with lock:
                    if state["error"] or self.cancelled:
                        return
                    if state["next"] >= len(chunks):
                        return
                    chunk = chunks[state["next"]]
                    state["next"] += 1
                try:
                    entries = self._read_chunk(chunk)
                except RuntimeError as exc:
                    with lock:
                        state["error"] = str(exc)
                    return
                with lock:
                    for entry in entries:
                        path = entry.get("SourceFile")
                        if path:
                            results[path] = _labels(entry)
                    state["done"] += len(chunk)
                    done, total = state["done"], len(files)
                if progress:
                    progress("read", done, total)

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(min(self.workers, len(chunks)))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results, state["error"]

    # ---------- the sweep ----------

    def run(self, progress=None):
        """Sweep the folder.

        `progress` is called as progress(stage, done, total) from a worker
        thread, with stage "walk" then "read"; a caller that touches a
        window must hand the figures to its own thread.

        Returns (tags, files, error): `tags` maps a tag to the sorted list
        of files carrying it, `files` is how many photographs were
        considered, and `error` is empty unless the sweep failed."""
        if not os.path.isdir(self.folder):
            return {}, 0, "folder"

        if progress:
            progress("walk", 0, 0)
        on_disk = self._walk()
        if self.cancelled:
            return {}, 0, "cancelled"
        if not on_disk:
            return {}, 0, ""

        index = self._load_index()
        per_file = {}
        stale = []
        for path, (mtime, size) in on_disk.items():
            kept = index.get(path)
            if (isinstance(kept, list) and len(kept) == 4
                    and kept[0] == mtime and kept[1] == size):
                per_file[path] = (kept[2], kept[3])
            else:
                stale.append(path)

        if progress:
            progress("read", 0, len(stale))

        fresh, error = self._read_all(sorted(stale), progress)
        if self.cancelled:
            return {}, 0, "cancelled"
        if error:
            return {}, 0, error

        per_file.update(fresh)

        # Only files still on disk are kept, so the cache cannot grow for
        # ever on a library that is reorganised.
        new_index = {}
        for path, (hier_labels, flat_labels) in per_file.items():
            mtime, size = on_disk[path]
            new_index[path] = [mtime, size, hier_labels, flat_labels]
        self._save_index(new_index)

        return _group(per_file), len(per_file), ""
