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
__version__ = "1.4.0"   # version propre à CE fichier ; incrémentée quand il change

import json
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

# Evening out the music. The target is ReplayGain's own reference, so a
# library already tagged by other tools lands where it expects to. The
# ceiling leaves a decibel of headroom before the encoder, and the limit on
# the gain keeps a nearly silent recording from being blown up into noise.
MUSIC_TARGET_LUFS = -18.0
MUSIC_PEAK_CEILING = -1.0
MUSIC_MAX_GAIN = 20.0
MUSIC_SILENCE = -70.0

# Trimming the silence the pieces themselves carry. Measured on a real
# montage, four pieces held fifteen seconds of silence between them, the
# worst of it at the loop point. The cut only ever happens INSIDE silence
# already detected: a piece whose silence is shorter than the margin is
# left alone.
#
# The floor is -80 dB and not something closer to hearing. At -50 dB a
# piano's decay is declared silent while it is still sounding — measured
# on one of these pieces, nearly four seconds of decay sat between the two
# thresholds, and cutting there was audible as a piece stopping before it
# had finished. -80 dB is the threshold this household already settled on
# for the same question elsewhere.
SILENCE_FLOOR_DB = -80.0
SILENCE_MIN = 0.3
SILENCE_KEEP = 0.3

# A bed built to the length of the film could otherwise grow without end
# behind a long slideshow and a short piece of music.
MUSIC_MAX_PIECES = 60

_SILENCE_START = re.compile(r"silence_start: (-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end: ([\d.]+)")

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

    def _capture_command(self, args):
        """Run a program and return (code, its output) without logging it.

        _run_command reports every line it reads, which is right for ffmpeg
        working but wrong for ffmpeg measuring: the measurement is a block
        of JSON nobody needs to read."""
        self._check()
        try:
            process = subprocess.Popen(args, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
        except OSError as exc:
            self.report("log", str(exc))
            return 1, ""
        with self._lock:
            self._process = process
        try:
            out, _err = process.communicate()
        finally:
            with self._lock:
                self._process = None
        return process.returncode, out or ""

    # ---------- the music, measured ----------

    def video_seconds(self, photo_count):
        """How long the film will run. The cross-fades overlap, so the
        photographs do not simply add up."""
        seconds = float(self.proj.settings.get("seconds_per_photo", 10))
        fade = float(self.proj.settings.get("crossfade", 2))
        if photo_count <= 0:
            return 0.0
        return photo_count * seconds - (photo_count - 1) * fade

    def _duration(self, path):
        """Length in seconds, or 0.0. Read from the header, not decoded."""
        code, text = self._capture_command(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path])
        try:
            return float(text.strip())
        except ValueError:
            return 0.0

    def _music_analysis(self, path):
        """What to do with one piece: (gain in dB, start, end).

        One reading pass answers both questions. The level is measured
        rather than read from the file's ReplayGain tags: ffmpeg applies
        those for FLAC but not for every format, and a library that mixes
        formats would come out half corrected, which is worse than not
        corrected at all because it cannot be predicted. The silence at
        each end is detected in the same pass, since the audio is being
        decoded anyway."""
        duration = self._duration(path)
        code, text = self._capture_command(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-af", "silencedetect=noise={}dB:d={},"
                    "loudnorm=print_format=json".format(
                        number(SILENCE_FLOOR_DB), number(SILENCE_MIN)),
             "-f", "null", "-"])
        if code != 0:
            return 0.0, 0.0, duration, duration
        begin, finish = self._bounds_from(text, duration)
        return self._gain_from(text), begin, finish, duration

    @staticmethod
    def _gain_from(text):
        start, end = text.rfind("{"), text.rfind("}")
        if start < 0 or end < start:
            return 0.0
        try:
            data = json.loads(text[start:end + 1])
            measured = float(data["input_i"])
            peak = float(data["input_tp"])
        except (ValueError, KeyError, TypeError):
            return 0.0
        if measured <= MUSIC_SILENCE:
            return 0.0           # silence: there is nothing to lift
        gain = MUSIC_TARGET_LUFS - measured
        if peak == peak and abs(peak) != float("inf"):   # not NaN, not inf
            gain = min(gain, MUSIC_PEAK_CEILING - peak)
        return max(-MUSIC_MAX_GAIN, min(MUSIC_MAX_GAIN, gain))

    @staticmethod
    def _bounds_from(text, duration):
        """Where the music really starts and ends, from silencedetect.

        A boundary is moved only when the silence is longer than the
        margin kept, so the cut always falls inside silence."""
        starts = [float(v) for v in _SILENCE_START.findall(text)]
        ends = [float(v) for v in _SILENCE_END.findall(text)]
        begin, finish = 0.0, duration

        if starts and ends and starts[0] <= 0.05:
            head = ends[0]
            if head > SILENCE_KEEP:
                begin = head - SILENCE_KEEP

        tail = None
        if len(starts) > len(ends):
            tail = starts[-1]            # silence running to the end
        elif starts and ends and duration and abs(ends[-1] - duration) < 0.3:
            tail = starts[-1]
        if tail is not None and duration - tail > SILENCE_KEEP:
            finish = tail + SILENCE_KEEP

        if finish <= begin:              # nonsense: leave the piece alone
            return 0.0, duration
        return begin, finish

    def _music_plan(self, files, even, trim):
        """Measure every piece once and say what to do with each."""
        self.report("step", ngettext("Measuring {n} piece of music",
                                     "Measuring {n} pieces of music",
                                     len(files)).format(n=len(files)))
        self.report("progress", (0, len(files)))
        plan = []
        for index, path in enumerate(files):
            self._check()
            gain, begin, finish, duration = self._music_analysis(path)
            if not even:
                gain = 0.0
            if not trim:
                begin, finish = 0.0, 0.0
            plan.append((gain, begin, finish))
            name = os.path.basename(path)
            if even and abs(gain) >= 0.1:
                self.report("log", _("{gain} dB applied to {name}").format(
                    gain="{:+.1f}".format(gain), name=name))
            if trim and duration:
                cut = begin + max(0.0, duration - finish)
                if cut >= 0.3:
                    self.report("log", _("{seconds} s of silence trimmed "
                                         "from {name}").format(
                        seconds="{:.1f}".format(cut), name=name))
            self.report("progress", (index + 1, len(files)))
        return plan

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

    def build_music(self, tmp, seconds_needed=0.0):
        """Return the path of the music to use, or None.

        Each piece is faded out at its end and the next begins at full
        volume, without overlap. Trimming takes away silence, but a long
        decay is music: cutting it is heard, and letting it run under the
        next entry muddles both. A fade brings it down deliberately.

        The bed is built long enough to cover the whole film rather than
        left to repeat, so that the moment where the music starts over gets
        the same fade as any other junction instead of being a splice."""
        files = [f for f in self.proj.settings.get("music_files", [])
                 if os.path.isfile(f)]
        if not files:
            return None

        even = bool(self.proj.settings.get("normalise_music", True))
        trim = bool(self.proj.settings.get("trim_music_silence", True))
        fade = max(0.0, float(self.proj.settings.get("music_fade_out", 3.0)))
        if not even and not trim and not fade and len(files) == 1:
            return files[0]          # nothing to join, measure, trim or fade

        plan = self._music_plan(files, even, trim)
        lengths = [max(0.1, (finish or self._duration(path)) - begin)
                   for (gain, begin, finish), path
                   in zip(plan, files)]

        order = self._music_order(lengths, seconds_needed)
        self.report("step", ngettext("Joining {n} piece of music",
                                     "Joining {n} pieces of music",
                                     len(order)).format(n=len(order)))

        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        parts = []
        for position, index in enumerate(order):
            args += ["-i", files[index]]
            gain, begin, finish = plan[index]
            chain = ""
            if begin > 0.01 or finish > 0.01:
                # atrim cuts, asetpts restarts the clock, without which the
                # join would honour the gap it was asked to remove.
                bounds = []
                if begin > 0.01:
                    bounds.append("start=" + number(begin))
                if finish > 0.01:
                    bounds.append("end=" + number(finish))
                chain += "atrim=" + ":".join(bounds) + ",asetpts=PTS-STARTPTS,"
            if abs(gain) >= 0.01:
                chain += "volume={}dB,".format(number(gain))
            # The fade belongs to the piece that is ending; the one that
            # follows comes in at full volume.
            if fade > 0.01 and lengths[index] > fade + 0.5:
                chain += "afade=t=out:st={}:d={},".format(
                    number(lengths[index] - fade), number(fade))
            parts.append("[{}:a]{}aresample=48000,"
                         "aformat=sample_fmts=s16:channel_layouts=stereo"
                         "[p{}];".format(position, chain, position))

        parts.append(self._music_join(len(order)))
        graph = "".join(parts).rstrip(";")
        bed = os.path.join(tmp, "bande-son.wav")
        args += ["-filter_complex", graph, "-map", "[bs]",
                 "-c:a", "pcm_s16le", bed]
        if self._run_command(args) != 0:
            self.report("log", _("The music could not be joined; "
                                 "the video will be silent."))
            return None
        return bed

    @staticmethod
    def _music_order(lengths, seconds_needed):
        """Which piece plays when, repeating the sequence as needed.

        Building the bed to the length of the film costs a little disk and
        buys a cross-faded junction where the music starts over — the one
        place a listener hears the montage rather than the music."""
        count = len(lengths)
        order = list(range(count))
        if seconds_needed <= 0:
            return order
        covered = sum(lengths)
        while covered < seconds_needed and len(order) < MUSIC_MAX_PIECES:
            for index in range(count):
                order.append(index)
                covered += lengths[index]
                if covered >= seconds_needed or len(order) >= MUSIC_MAX_PIECES:
                    break
        return order

    @staticmethod
    def _music_join(count):
        """The pieces, end to end. They do not overlap: each one has
        already been faded out, and the next is meant to arrive whole."""
        if count == 1:
            return "[p0]anull[bs];"
        return ("".join("[p{}]".format(i) for i in range(count))
                + "concat=n={}:v=0:a=1[bs];".format(count))

    # ---------- step two: the video ----------

    def build_video(self, images, music):
        proj = self.proj
        width, height = proj.size
        seconds = float(proj.settings.get("seconds_per_photo", 10))
        fade = float(proj.settings.get("crossfade", 2))
        black = float(proj.settings.get("black_fade", 2))
        count = len(images)
        total = self.video_seconds(count)

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
            music = self.build_music(tmp, self.video_seconds(len(images)))
            video = self.build_video(images, music)
            self.report("done", video)
        except Cancelled:
            self.report("done", None)
        except Exception as exc:                       # unexpected, but shown
            self.report("log", "{}: {}".format(type(exc).__name__, exc))
            self.report("done", None)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
