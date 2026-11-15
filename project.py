#!/usr/bin/env python3
"""
project.py — The state of a slideshow: which photos, in what order, with what
captions and settings.

A project is a plain JSON file. It holds paths, never copies of the photos, so
it stays a few kilobytes whatever the size of the slideshow. Removing a photo
from a project never touches the file on disk.

Captions come from the files themselves (see metadata.py). A project may hold
an OVERRIDE for a photo: a text that is used for the slideshow without being
written back into the archive. That is the safe default; writing into the
originals is a separate, explicit action.
"""
__version__ = "1.1.0"   # version propre à CE fichier ; incrémentée quand il change

import json
import os

import metadata
import paths

SUFFIX = ".d2s.json"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")

FORMATS = {
    "HD": (1920, 1080),
    "4K": (3840, 2160),
}

DEFAULT_SETTINGS = {
    "format": "HD",
    "seconds_per_photo": 10.0,
    "crossfade": 2.0,
    "black_fade": 2.0,
    "music_files": [],
    # Empty means "follow the project name"; a path set by the user is kept.
    "images_dir": "",
    "video_path": "",
}


class Photo:
    """One photo in the slideshow."""

    __slots__ = ("path", "file_caption", "override", "date")

    def __init__(self, path, file_caption="", override=None, date=""):
        self.path = path
        self.file_caption = file_caption
        self.override = override
        self.date = date

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def caption(self):
        """What the slideshow will show: the override if there is one."""
        if self.override is not None:
            return self.override
        return self.file_caption

    @property
    def has_override(self):
        return self.override is not None and self.override != self.file_caption

    @property
    def exists(self):
        return os.path.isfile(self.path)

    def to_dict(self):
        d = {"path": self.path}
        if self.override is not None:
            d["override"] = self.override
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(d.get("path", ""), override=d.get("override"))


class Project:
    """The whole slideshow: an ordered list of photos plus the settings."""

    def __init__(self):
        self.photos = []
        self.settings = dict(DEFAULT_SETTINGS)
        self.file_path = None
        self.dirty = False

    # ---------- naming ----------

    @property
    def title(self):
        if self.file_path:
            base = os.path.basename(self.file_path)
            if base.endswith(SUFFIX):
                return base[: -len(SUFFIX)]
            return os.path.splitext(base)[0]
        return ""

    # ---------- adding and removing ----------

    def _known_paths(self):
        return {p.path for p in self.photos}

    def add_paths(self, file_paths):
        """Add files, skipping duplicates and non-images.
        Returns (added, skipped)."""
        known = self._known_paths()
        fresh = []
        skipped = 0
        for p in file_paths:
            full = os.path.abspath(p)
            if not os.path.isfile(full):
                skipped += 1
                continue
            if os.path.splitext(full)[1].lower() not in IMAGE_EXTENSIONS:
                skipped += 1
                continue
            if full in known:
                skipped += 1
                continue
            known.add(full)
            fresh.append(Photo(full))
        if fresh:
            self.photos.extend(fresh)
            self.refresh_metadata(fresh)
            self.dirty = True
        return len(fresh), skipped

    def add_folder(self, folder, recursive=True):
        """Add every image of a folder, in alphabetical order of full path."""
        return self.add_paths(scan_folder(folder, recursive))

    def remove(self, indexes):
        """Remove photos by index. The files on disk are never touched."""
        for i in sorted(indexes, reverse=True):
            if 0 <= i < len(self.photos):
                del self.photos[i]
                self.dirty = True

    # ---------- ordering ----------

    def move(self, indexes, delta):
        """Move the selected photos up (delta<0) or down (delta>0) by one.
        Returns the new indexes of the moved photos."""
        if not indexes or delta == 0:
            return list(indexes)
        order = sorted(indexes, reverse=(delta > 0))
        moved = []
        for i in order:
            j = i + delta
            if j < 0 or j >= len(self.photos) or j in moved:
                moved.append(i)
                continue
            self.photos[i], self.photos[j] = self.photos[j], self.photos[i]
            moved.append(j)
            self.dirty = True
        return sorted(moved)

    def move_to_edge(self, indexes, to_start):
        """Move the selected photos to the very start or the very end."""
        if not indexes:
            return []
        picked = [self.photos[i] for i in sorted(indexes)]
        rest = [p for k, p in enumerate(self.photos) if k not in set(indexes)]
        if to_start:
            self.photos = picked + rest
            new = list(range(len(picked)))
        else:
            self.photos = rest + picked
            new = list(range(len(rest), len(self.photos)))
        self.dirty = True
        return new

    def sort_by_name(self):
        self.photos.sort(key=lambda p: p.path.lower())
        self.dirty = True

    def sort_by_date(self):
        """Sort by capture date; photos without a date keep to the end,
        in alphabetical order."""
        self.photos.sort(key=lambda p: (p.date == "", p.date, p.path.lower()))
        self.dirty = True

    def reverse(self):
        self.photos.reverse()
        self.dirty = True

    # ---------- captions ----------

    def refresh_metadata(self, subset=None):
        """Re-read captions and dates from the files, in one exiftool call."""
        photos = self.photos if subset is None else subset
        if not photos:
            return
        data = metadata.read_many([p.path for p in photos])
        for p in photos:
            info = data.get(p.path, {})
            p.file_caption = info.get("caption", "")
            p.date = info.get("date", "")

    def set_override(self, index, text):
        """Set or clear the project-only caption of one photo."""
        if not (0 <= index < len(self.photos)):
            return
        photo = self.photos[index]
        if text is None or text == photo.file_caption:
            photo.override = None
        else:
            photo.override = text
        self.dirty = True

    def counts(self):
        """(total, with a caption, with a project-only caption, missing file)"""
        total = len(self.photos)
        captioned = sum(1 for p in self.photos if p.caption)
        overridden = sum(1 for p in self.photos if p.has_override)
        gone = sum(1 for p in self.photos if not p.exists)
        return total, captioned, overridden, gone

    # ---------- settings ----------

    @property
    def size(self):
        """(width, height) for the chosen format."""
        return FORMATS.get(self.settings.get("format", "HD"), FORMATS["HD"])

    def duration(self):
        """Total length of the slideshow, in seconds."""
        n = len(self.photos)
        if n == 0:
            return 0.0
        d = float(self.settings.get("seconds_per_photo", 10))
        f = float(self.settings.get("crossfade", 2))
        return n * d - (n - 1) * f

    def set_setting(self, key, value):
        if self.settings.get(key) != value:
            self.settings[key] = value
            self.dirty = True

    # ---------- where the results are written ----------

    @property
    def base_name(self):
        """Stem used for the produced files when the user set no path."""
        return self.title or "diaporama"

    def images_dir(self):
        """Folder that will hold the laid-out images."""
        chosen = (self.settings.get("images_dir") or "").strip()
        if chosen:
            return chosen
        width, height = self.size
        return os.path.join(paths.output_dir(),
                            "{}-{}x{}".format(self.base_name, width, height))

    def video_path(self):
        """File that will hold the video.

        The resolution is part of the name, exactly as it is for the images
        folder: a trial in HD and a final cut in 4K are two different files
        and should not have to fight over one name."""
        chosen = (self.settings.get("video_path") or "").strip()
        if chosen:
            return chosen
        width, height = self.size
        return os.path.join(paths.output_dir(),
                            "{}-{}x{}.mp4".format(self.base_name,
                                                  width, height))

    def images_dir_is_automatic(self):
        return not (self.settings.get("images_dir") or "").strip()

    def video_path_is_automatic(self):
        return not (self.settings.get("video_path") or "").strip()

    # ---------- persistence ----------

    def to_dict(self):
        return {
            "application": "diaporama2screen",
            "version": 1,
            "settings": self.settings,
            "photos": [p.to_dict() for p in self.photos],
        }

    def save(self, file_path=None):
        """Write the project as JSON. Atomic replace. Raises OSError on
        failure, so the caller can show a real message."""
        target = file_path or self.file_path
        if not target:
            raise ValueError("no project path")
        if not target.endswith(SUFFIX):
            target += SUFFIX
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, target)
        self.file_path = target
        self.dirty = False
        return target

    @classmethod
    def load(cls, file_path):
        """Read a project file. Raises OSError or ValueError on failure."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("not a project file")
        proj = cls()
        proj.settings = dict(DEFAULT_SETTINGS)
        stored = data.get("settings")
        if isinstance(stored, dict):
            proj.settings.update(stored)
        proj.photos = [Photo.from_dict(d)
                       for d in data.get("photos", [])
                       if isinstance(d, dict) and d.get("path")]
        proj.file_path = file_path
        proj.dirty = False
        proj.refresh_metadata()
        return proj


def scan_folder(folder, recursive=True):
    """Every image file of a folder, sorted, hidden directories left out."""
    found = []
    if recursive:
        for root, dirs, names in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for n in sorted(names):
                if os.path.splitext(n)[1].lower() in IMAGE_EXTENSIONS:
                    found.append(os.path.join(root, n))
    else:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return found
        for n in names:
            full = os.path.join(folder, n)
            if (os.path.isfile(full)
                    and os.path.splitext(n)[1].lower() in IMAGE_EXTENSIONS):
                found.append(full)
    return found


def default_project_path(name):
    """Where a project called <name> is saved by default."""
    paths.ensure(paths.projects_dir())
    return os.path.join(paths.projects_dir(), name + SUFFIX)
