#!/usr/bin/env python3
"""
preview.py — Showing one photo at a time, fast enough to browse a list.

Decoding a scan takes long enough to be felt when stepping through a list with
the arrow keys, so results are kept in a small LRU cache. The cache holds the
Tk images themselves: Tk discards an image whose last Python reference is gone,
which is the classic reason a preview turns blank for no visible reason.
"""
__version__ = "1.0.1"   # version propre à CE fichier ; incrémentée quand il change

from collections import OrderedDict

try:
    from PIL import Image, ImageOps, ImageTk
    AVAILABLE = True
except ImportError:          # Pillow absent: the window still opens
    AVAILABLE = False

if AVAILABLE:
    # Pillow warns above 89.5 megapixels, as a guard against a crafted file
    # made to exhaust memory. A photograph scanned at 1200 dpi reaches 100
    # megapixels honestly, so the guard is raised rather than switched off:
    # it still catches a file far outside anything a scanner produces.
    Image.MAX_IMAGE_PIXELS = 512_000_000


class Preview:
    """Decode, orient and scale a photo to fit a box, with a small cache."""

    def __init__(self, max_items=24):
        self.max_items = max_items
        self._cache = OrderedDict()

    def clear(self):
        self._cache.clear()

    def forget(self, path):
        for key in [k for k in self._cache if k[0] == path]:
            del self._cache[key]

    def get(self, path, box_width, box_height):
        """Return (image, (width, height)) scaled to fit the box, or
        (None, error_message). Never raises."""
        if not AVAILABLE:
            return None, "Pillow"
        box_width = max(32, int(box_width))
        box_height = max(32, int(box_height))
        # Quantise the box so a slow window resize does not thrash the cache
        key = (path, box_width // 16, box_height // 16)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        try:
            with Image.open(path) as im:
                # draft() asks the JPEG decoder for a 1/2, 1/4 or 1/8 scale
                # image, so the full resolution is never built. On a 1200 dpi
                # scan this is the difference between a frozen window and a
                # fluid one. It must come before any access to the pixels,
                # and does nothing for formats that cannot do it.
                try:
                    im.draft("RGB", (box_width, box_height))
                except Exception:
                    pass
                im = ImageOps.exif_transpose(im)
                im = im.convert("RGB")
                im.thumbnail((box_width, box_height), Image.LANCZOS,
                             reducing_gap=2.0)
                photo = ImageTk.PhotoImage(im)
                result = (photo, im.size)
        except Exception as exc:
            return None, str(exc)
        self._cache[key] = result
        while len(self._cache) > self.max_items:
            self._cache.popitem(last=False)
        return result
