#!/usr/bin/env python3
"""
paths.py — Where diaporama2screen keeps its settings, projects and cache.

Single place that resolves every location the application writes to, so no
other module ever builds a path by hand. Follows the XDG base directory
specification, with an environment override for testing.
"""
__version__ = "1.1.1"   # version propre à CE fichier ; incrémentée quand il change

import os

APP_NAME = "diaporama2screen"

# Version of the APPLICATION as a whole — not of this file, which carries its
# own __version__ above like every other module. This is the number a bug
# report should quote, so it lives in the one module every other one imports.
APP_VERSION = "1.0.5"
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _base(var, default):
    """XDG base directory from the environment, or its documented default."""
    return os.environ.get(var) or os.path.expanduser(default)


def config_dir():
    """Directory holding settings.json."""
    return os.path.join(_base("XDG_CONFIG_HOME", "~/.config"), APP_NAME)


def settings_path():
    """Path of settings.json. DIAPORAMA2SCREEN_SETTINGS overrides it."""
    override = os.environ.get("DIAPORAMA2SCREEN_SETTINGS")
    if override:
        return override
    return os.path.join(config_dir(), "settings.json")


def cache_dir():
    """Directory for thumbnails and other disposable data."""
    return os.path.join(_base("XDG_CACHE_HOME", "~/.cache"), APP_NAME)


def output_dir():
    """Where produced images and videos are written."""
    return os.path.join(os.path.expanduser("~"), "Diaporama")


def projects_dir():
    """Where project files (.d2s.json) are kept by default."""
    return os.path.join(output_dir(), "projets")


def ensure(path):
    """Create a directory if it does not exist. Returns the path.
    Never raises: a read-only location simply yields a later, clearer error."""
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return path
