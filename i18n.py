#!/usr/bin/env python3
"""
i18n.py — Translation foundation for diaporama2screen (GNU gettext).

Single source of truth for language resolution, shared by every module.
Import pattern:

    try:
        from i18n import _
    except ImportError:          # standalone use without the catalogs
        def _(s):                # graceful fallback: source strings (English)
            return s

Language resolution order:
  1. Explicit user preference in settings.json ("language": "en" / "fr")
  2. "auto" (or missing) -> operating system language (LC_MESSAGES / LANG)
  3. Fallback -> English (the language of the source msgid strings)

Compiled catalogs are expected under:
    <project dir>/locale/<lang>/LC_MESSAGES/diaporama2screen.mo
Their absence never breaks anything: gettext falls back to the source strings.
"""
__version__ = "1.1.0"   # version propre à CE fichier ; incrémentée quand il change

import gettext
import json
import os

import paths

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(APP_DIR, "locale")
DOMAIN = "diaporama2screen"

SUPPORTED = ("en", "fr")
SOURCE_LANGUAGE = "en"   # language of the msgid strings in the code


# ---------- settings.json (shared, other keys preserved) ----------

def _read_settings():
    try:
        with open(paths.settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_setting(key, default=None):
    """Generic settings.json getter for any key."""
    return _read_settings().get(key, default)


def write_setting(key, value):
    """Generic settings.json setter, preserving all other keys.
    Atomic replace; returns True on success."""
    data = _read_settings()
    data[key] = value
    path = paths.settings_path()
    tmp = path + ".tmp"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, mode=0o700, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def read_language_setting():
    """Return the stored preference: 'en', 'fr' or 'auto' (default)."""
    lang = read_setting("language", "auto")
    return lang if lang in SUPPORTED + ("auto",) else "auto"


def write_language_setting(lang):
    """Persist the preference ('en', 'fr' or 'auto'). Returns True on success."""
    if lang not in SUPPORTED + ("auto",):
        return False
    return write_setting("language", lang)


# ---------- language resolution ----------

def system_language():
    """Two-letter OS language code from the environment, or ''."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "")
        if val:
            code = val.split(".")[0].split("_")[0].lower()
            if code:
                return code
    return ""


def resolve_language():
    """Effective language: explicit setting > OS language > source language."""
    pref = read_language_setting()
    if pref in SUPPORTED:
        return pref
    sys_lang = system_language()
    return sys_lang if sys_lang in SUPPORTED else SOURCE_LANGUAGE


# ---------- gettext installation ----------

def _translation():
    """The catalog for the resolved language. Never raises: a missing catalog
    falls back to the source (English) strings."""
    try:
        return gettext.translation(DOMAIN, LOCALE_DIR,
                                   languages=[resolve_language()],
                                   fallback=True)
    except Exception:
        return gettext.NullTranslations()


def install():
    """Return the translation function for the resolved language."""
    return _translation().gettext


def install_plural():
    """Return the translation function for COUNTED strings.

    A counted sentence cannot go through the ordinary one: gettext has to be
    told the number, because the form to use is a property of the language,
    not of the string. French and English both have two forms but do not
    agree on where the boundary falls — French says "0 photo" where English
    says "0 photos" — and other languages have three or more."""
    return _translation().ngettext


# ---------- locale environment for external programs (zenity) ----------

def _available_locales():
    """Set of locales installed on the system (via `locale -a`), lowercase."""
    import subprocess
    try:
        out = subprocess.run(["locale", "-a"], capture_output=True, text=True,
                             timeout=5).stdout
        return {l.strip().lower() for l in out.splitlines() if l.strip()}
    except Exception:
        return set()


def subprocess_env():
    """Environment for launching an EXTERNAL localized program, so that its own
    buttons follow the language chosen here rather than the system locale.
    Returns a copy of os.environ; never raises."""
    env = os.environ.copy()
    lang = resolve_language()
    if lang == system_language():
        return env
    if lang == "en":
        env["LC_ALL"] = "C.UTF-8"
        env["LANGUAGE"] = "en"
        return env
    available = _available_locales()
    regions = {"fr": ("CA", "FR"), "en": ("US", "GB")}
    candidates = [lang + ".utf8", lang + ".UTF-8"]
    for region in regions.get(lang, ()):
        candidates += ["{}_{}.utf8".format(lang, region),
                       "{}_{}.UTF-8".format(lang, region)]
    for candidate in candidates:
        if candidate.lower() in available:
            env["LC_ALL"] = candidate
            env["LANGUAGE"] = lang
            return env
    return env


_ = install()
ngettext = install_plural()
