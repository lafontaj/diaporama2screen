#!/usr/bin/env python3
"""
diaporama2screen — Build a photo slideshow with the caption burnt into the
image, ready to play on a television.

Entry point. Keeps nothing of its own: it checks that a graphical display is
reachable, opens the window, and gets out of the way.
"""
__version__ = "1.2.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import sys


def _set_window_icon(app, here):
    """Give the window its icon. A missing or unreadable file is not a reason
    to refuse to start, so every failure here is silent."""
    import tkinter as tk
    for size in (128, 64, 48):
        path = os.path.join(here, "icons",
                            "diaporama2screen-{}.png".format(size))
        if os.path.isfile(path):
            try:
                image = tk.PhotoImage(file=path)
                app.iconphoto(True, image)
                app._window_icon = image      # Tk discards an unreferenced one
                return
            except Exception:
                continue


USAGE = """Usage: diaporama2screen.py [OPTION]

Build a photo slideshow with the caption burnt into the image, ready to play
on a television. Without an option, the window opens.

  -V, --version   print the version and exit
  -h, --help      print this help and exit
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    # Answered before anything graphical is touched, so that a version can be
    # read on a machine with no display — which is where a bug report is
    # usually being written.
    argument = sys.argv[1] if len(sys.argv) > 1 else ""
    if argument in ("-V", "--version"):
        import paths
        sys.stdout.write("{} {}\n".format(paths.APP_NAME, paths.APP_VERSION))
        return 0
    if argument in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0

    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "tkinter is missing. Install it with:\n"
            "  sudo apt install python3-tk\n")
        return 1

    from ui_main import App

    try:
        app = App()
        _set_window_icon(app, here)
    except Exception as exc:                      # no display, broken theme…
        sys.stderr.write("The window could not be opened: {}\n".format(exc))
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
