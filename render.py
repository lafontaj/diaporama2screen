#!/usr/bin/env python3
"""
render.py — Producing the images and the video.

Two steps, deliberately kept apart.

The first lays out every photo at the chosen resolution with its caption in a
black band underneath, and writes the result as a numbered JPEG. The second
assembles those images into a video with cross-fades and music.

Both run in a worker thread and report through a callback, so the window stays
alive and the work can be stopped. Nothing here touches tkinter: the caller is
responsible for bringing the messages back to the main thread.

The commands are those of the shell scripts this application grew from, kept
as they were because they are known to work:

  - ImageMagick interprets % and a leading @ in a caption, so both are
    neutralised rather than quoted.
  - Intermediate files are MIFF, not PNG: a greyscale scan carrying an RGB
    colour profile makes the PNG encoder warn on every single image.
  - Decimal numbers are formatted in Python, never by a shell tool, because a
    French locale writes 4,000 and a comma separates arguments in an FFmpeg
    filter.
"""
__version__ = "1.1.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import re
import shutil
import subprocess
import tempfile
import threading

try:
    from i18n import _, ngettext
except ImportError:
    def _(s):
        return s

    def ngettext(singular, plural, n):
        return singular if n == 1 else plural

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
)

FPS = 30
JPEG_QUALITY = 92
AUDIO_FADE_IN = 2.0
AUDIO_FADE_OUT = 4.0

_TIME_RE = re.compile(r"out_time_ms=(\d+)")


def find_font():
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def clean_caption(text):
    """Neutralise what ImageMagick would interpret in a caption."""
    text = (text or "").replace("%", "%%")
    if text.startswith("@"):
        text = " " + text
    return text


def number(value):
    """A decimal FFmpeg will read, whatever the locale of the machine."""
    return "{:.3f}".format(float(value))


class Cancelled(Exception):
    """Raised inside the worker when the user asked to stop."""


class Renderer:
    """Runs the two steps in a thread and reports progress.

    report(kind, payload) is called from the worker thread with:
      ("step",     text)             a new phase has begun
      ("progress", (done, total))    where we are inside the phase
      ("log",      text)             a line for the detail pane
      ("done",     path or None)     finished; None when it failed or stopped
    """

    def __init__(self, project, report):
        self.proj = project
        self.report = report
        self._stop = threading.Event()
        self._process = None
        self._lock = threading.Lock()
        self.thread = None

    # ---------- control ----------

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def cancel(self):
        self._stop.set()
        with self._lock:
            if self._process is not None:
                try:
                    self._process.terminate()
                except Exception:
                    pass

    @property
    def cancelled(self):
        return self._stop.is_set()

    def _check(self):
        if self._stop.is_set():
            raise Cancelled()

    # ---------- running external programs ----------

    def _run_command(self, args, capture_progress=False, total_seconds=0.0):
        """Run one external program. Returns its exit code. While it runs the
        process is remembered, so cancelling can terminate it."""
        self._check()
        popen_args = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1)
        try:
            process = subprocess.Popen(args, **popen_args)
        except OSError as exc:
            self.report("log", str(exc))
            return 1
        with self._lock:
            self._process = process
        last = -1
        try:
            for line in process.stdout:
                if self._stop.is_set():
                    break
                if capture_progress and total_seconds > 0:
                    match = _TIME_RE.search(line)
                    if match:
                        seconds = int(match.group(1)) / 1_000_000.0
                        percent = int(100 * seconds / total_seconds)
                        if percent != last:
                            last = percent
                            self.report("progress", (min(percent, 100), 100))
                elif line.strip():
                    self.report("log", line.rstrip())
        finally:
            process.stdout.close()
            code = process.wait()
            with self._lock:
                self._process = None
        return code

    # ---------- step one: the images ----------

    def build_images(self, tmp):
        proj = self.proj
        width, height = proj.size
        font = find_font()
        if font is None:
            self.report("log", _("No DejaVu font found; captions will use "
                                 "the ImageMagick default."))

        text_size = max(12, height * 4 // 100)
        margin = height * 2 // 100
        band_min = height * 10 // 100
        text_width = width * 90 // 100

        out_dir = proj.images_dir()
        os.makedirs(out_dir, exist_ok=True)
        for name in os.listdir(out_dir):
            if re.match(r"^\d{3}_.*\.jpg$", name):
                try:
                    os.remove(os.path.join(out_dir, name))
                except OSError:
                    pass

        photos = [p for p in proj.photos if p.exists]
        total = len(photos)
        produced = []
        self.report("step", _("Laying out the images"))

        for index, photo in enumerate(photos, start=1):
            self._check()
            band_height = 0
            caption = clean_caption(photo.caption)
            if caption:
                args = ["convert", "-background", "black", "-fill", "white"]
                if font:
                    args += ["-font", font]
                args += ["-pointsize", str(text_size),
                         "-size", "{}x".format(text_width),
                         "-gravity", "center", "caption:" + caption,
                         os.path.join(tmp, "brut.miff")]
                if self._run_command(args) == 0:
                    measured = self._measure(os.path.join(tmp, "brut.miff"))
                    if measured:
                        band_height = max(measured + 2 * margin, band_min)
                        if self._run_command(
                                ["convert", os.path.join(tmp, "brut.miff"),
                                 "-background", "black", "-gravity", "center",
                                 "-extent", "{}x{}".format(width,
                                                           band_height),
                                 os.path.join(tmp, "bande.miff")]) != 0:
                            band_height = 0
                else:
                    self.report("log", _("Caption unusable for {name}").format(
                        name=photo.name))

            photo_height = height - band_height
            if self._run_command(
                    ["convert", photo.path, "-auto-orient",
                     "-resize", "{}x{}".format(width, photo_height),
                     "-background", "black", "-gravity", "center",
                     "-extent", "{}x{}".format(width, photo_height),
                     os.path.join(tmp, "photo.miff")]) != 0:
                self.report("log", _("Could not read {name}").format(
                    name=photo.name))
                continue

            stem = os.path.splitext(photo.name)[0]
            target = os.path.join(out_dir,
                                  "{:03d}_{}.jpg".format(index, stem))
            if band_height > 0:
                args = ["convert", os.path.join(tmp, "photo.miff"),
                        os.path.join(tmp, "bande.miff"), "-append"]
            else:
                args = ["convert", os.path.join(tmp, "photo.miff")]
            args += ["-quality", str(JPEG_QUALITY), target]
            if self._run_command(args) == 0:
                produced.append(target)
            self.report("progress", (index, total))

        return produced

    def _measure(self, path):
        """Height of an intermediate image, or 0."""
        try:
            out = subprocess.run(["identify", "-format", "%h", path],
                                 capture_output=True, text=True, timeout=60)
            return int(out.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0

    # ---------- the music bed ----------

    def build_music(self, tmp):
        """Return the path of the music to use, or None.
        Several pieces are joined into one file first, so that looping repeats
        the whole sequence rather than the first piece."""
        files = [f for f in self.proj.settings.get("music_files", [])
                 if os.path.isfile(f)]
        if not files:
            return None
        if len(files) == 1:
            return files[0]
        self.report("step", ngettext("Joining {n} piece of music",
                                     "Joining {n} pieces of music",
                                     len(files)).format(
            n=len(files)))
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        parts = []
        for index, path in enumerate(files):
            args += ["-i", path]
            parts.append("[{}:a]aresample=48000,"
                         "aformat=sample_fmts=s16:channel_layouts=stereo"
                         "[p{}];".format(index, index))
        graph = "".join(parts) + "".join(
            "[p{}]".format(i) for i in range(len(files)))
        graph += "concat=n={}:v=0:a=1[bs]".format(len(files))
        bed = os.path.join(tmp, "bande-son.wav")
        args += ["-filter_complex", graph, "-map", "[bs]",
                 "-c:a", "pcm_s16le", bed]
        if self._run_command(args) != 0:
            self.report("log", _("The music could not be joined; "
                                 "the video will be silent."))
            return None
        return bed

    # ---------- step two: the video ----------

    def build_video(self, images, music):
        proj = self.proj
        width, height = proj.size
        seconds = float(proj.settings.get("seconds_per_photo", 10))
        fade = float(proj.settings.get("crossfade", 2))
        black = float(proj.settings.get("black_fade", 2))
        count = len(images)
        total = count * seconds - (count - 1) * fade

        target = proj.video_path()
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)

        args = ["ffmpeg", "-hide_banner", "-y"]
        for path in images:
            args += ["-loop", "1", "-t", number(seconds), "-i", path]
        if music:
            args += ["-stream_loop", "-1", "-i", music]

        parts = []
        for index in range(count):
            parts.append(
                "[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                "pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
                "fps={fps},format=yuv420p[v{i}];".format(
                    i=index, w=width, h=height, fps=FPS))

        if count == 1:
            parts.append("[v0]null[vx];")
        else:
            previous = "v0"
            for index in range(1, count):
                offset = index * (seconds - fade)
                label = "vx" if index == count - 1 else "x{}".format(index)
                parts.append(
                    "[{prev}][v{i}]xfade=transition=fade:"
                    "duration={d}:offset={o}[{out}];".format(
                        prev=previous, i=index, d=number(fade),
                        o=number(offset), out=label))
                previous = label

        parts.append("[vx]fade=t=in:st=0:d={b},"
                     "fade=t=out:st={s}:d={b}[vout];".format(
                         b=number(black),
                         s=number(max(0.0, total - black))))

        maps = ["-map", "[vout]"]
        if music:
            parts.append(
                "[{i}:a]atrim=0:{t},asetpts=PTS-STARTPTS,"
                "afade=t=in:st=0:d={fi},"
                "afade=t=out:st={fo}:d={fd}[aout];".format(
                    i=count, t=number(total), fi=number(AUDIO_FADE_IN),
                    fo=number(max(0.0, total - AUDIO_FADE_OUT)),
                    fd=number(AUDIO_FADE_OUT)))
            maps += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
        else:
            maps += ["-an"]

        graph = "".join(parts).rstrip(";")
        args += ["-filter_complex", graph] + maps
        args += ["-t", number(total),
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                 "-nostats", "-progress", "pipe:1", target]

        self.report("step", _("Encoding the video"))
        self.report("progress", (0, 100))
        code = self._run_command(args, capture_progress=True,
                                 total_seconds=total)
        self._check()
        if code != 0:
            return None
        return target

    # ---------- the whole thing ----------

    def _run(self):
        tmp = tempfile.mkdtemp(prefix="diaporama2screen-")
        try:
            images = self.build_images(tmp)
            if not images:
                self.report("log", _("No image could be produced."))
                self.report("done", None)
                return
            music = self.build_music(tmp)
            video = self.build_video(images, music)
            self.report("done", video)
        except Cancelled:
            self.report("done", None)
        except Exception as exc:                       # unexpected, but shown
            self.report("log", "{}: {}".format(type(exc).__name__, exc))
            self.report("done", None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
