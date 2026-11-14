#!/usr/bin/env python3
"""
ui_render.py — The window shown while the slideshow is produced.

The work happens in a thread; tkinter may only be touched from the main one.
Messages therefore travel through a queue that this window drains on a timer.
That is the whole trick, and the reason the window stays responsive and the
Cancel button answers at once.
"""
__version__ = "1.0.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import queue
import subprocess
import tkinter as tk
from tkinter import ttk

import render as render_mod
import ui_dialogs

try:
    from i18n import _
except ImportError:
    def _(s):
        return s


class RenderWindow(tk.Toplevel):
    """Progress, detail and cancellation for one production run."""

    def __init__(self, parent, project):
        super().__init__(parent)
        self.proj = project
        self.queue = queue.Queue()
        self.result = None
        self.finished = False

        self.title(_("Producing the slideshow"))
        self.transient(parent)
        self.geometry("720x460")
        self.minsize(520, 340)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self.renderer = render_mod.Renderer(project, self._report)
        self.renderer.start()
        self.after(100, self._drain)
        self.grab_set()

    # ---------- construction ----------

    def _build(self):
        head = ttk.Frame(self, padding=(14, 12))
        head.pack(side="top", fill="x")
        head.columnconfigure(0, weight=1)

        self.lbl_step = ttk.Label(head, text=_("Starting…"),
                                  font=("", 11, "bold"))
        self.lbl_step.grid(row=0, column=0, sticky="w")

        self.bar = ttk.Progressbar(head, mode="determinate", maximum=100)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.lbl_detail = ttk.Label(head, text="")
        self.lbl_detail.grid(row=2, column=0, sticky="w", pady=(6, 0))

        ttk.Separator(self, orient="horizontal").pack(side="top", fill="x")

        foot = ttk.Frame(self, padding=(14, 10))
        foot.pack(side="bottom", fill="x")
        self.btn_close = ttk.Button(foot, text=_("Cancel"),
                                    command=self._on_close)
        self.btn_close.pack(side="right")
        self.btn_open = ttk.Button(foot, text=_("Open the folder"),
                                   command=self._open_folder,
                                   state="disabled")
        self.btn_open.pack(side="right", padx=(0, 8))

        body = ttk.Frame(self, padding=(14, 8))
        body.pack(side="top", fill="both", expand=True)
        box = tk.Frame(body, borderwidth=1, relief="solid")
        box.pack(fill="both", expand=True)

        self.text = tk.Text(box, wrap="word", height=8, borderwidth=0,
                            highlightthickness=0, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(box, orient="vertical",
                               command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)

    # ---------- messages from the worker ----------

    def _report(self, kind, payload):
        """Called from the WORKER thread: only ever touches the queue."""
        self.queue.put((kind, payload))

    def _drain(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if not self.finished:
            self.after(100, self._drain)

    def _handle(self, kind, payload):
        if kind == "step":
            self.lbl_step.configure(text=payload)
            self.bar.configure(value=0)
            self.lbl_detail.configure(text="")
            self._log(payload)
        elif kind == "progress":
            done, total = payload
            self.bar.configure(value=(100 * done / total) if total else 0)
            if total == 100:
                self.lbl_detail.configure(text="{} %".format(done))
            else:
                self.lbl_detail.configure(
                    text=_("{done} of {total}").format(done=done,
                                                       total=total))
        elif kind == "log":
            self._log(payload)
        elif kind == "done":
            self._on_done(payload)

    def _log(self, line):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    # ---------- the end ----------

    def _on_done(self, path):
        self.finished = True
        self.result = path
        self.btn_close.configure(text=_("Close"))
        if path:
            self.bar.configure(value=100)
            self.lbl_step.configure(text=_("Finished"))
            size = ""
            try:
                size = " — {:.0f} MB".format(os.path.getsize(path) / 1e6)
            except OSError:
                pass
            self.lbl_detail.configure(text=os.path.basename(path) + size)
            self._log(_("Written to: {path}").format(path=path))
            self.btn_open.configure(state="normal")
        elif self.renderer.cancelled:
            self.lbl_step.configure(text=_("Stopped"))
            self.lbl_detail.configure(
                text=_("Nothing more was written."))
        else:
            self.lbl_step.configure(text=_("Failed"))
            self.lbl_detail.configure(
                text=_("See the detail below."))

    def _open_folder(self):
        if not self.result:
            return
        folder = os.path.dirname(self.result)
        try:
            subprocess.Popen(["xdg-open", folder])
        except OSError as exc:
            ui_dialogs.error(self, str(exc))

    def _on_close(self):
        if self.finished:
            self.destroy()
            return
        if ui_dialogs.confirm(
                self, _("Stop the production now?"),
                ok_text=_("Stop"), cancel_text=_("Keep going")):
            self.lbl_step.configure(text=_("Stopping…"))
            self.renderer.cancel()


def produce(parent, project):
    """Run a production and return the video path, or None."""
    window = RenderWindow(parent, project)
    parent.wait_window(window)
    return window.result
