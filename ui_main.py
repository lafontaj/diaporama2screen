#!/usr/bin/env python3
"""
ui_main.py — The main window: the list of photos, the preview, the caption,
and the production panel underneath.

The list on the left is BOTH the selection and the order of the slideshow:
keeping two separate lists would mean keeping them in step, which is exactly
the kind of bookkeeping that goes wrong.
"""
__version__ = "1.8.0"   # version propre à CE fichier ; incrémentée quand il change

import os
import subprocess
import tkinter as tk
from tkinter import ttk

import deps
import i18n
import launcher
import metadata
import paths
import preview as preview_mod
import project as project_mod
import ui_dialogs
import ui_import
import ui_rejects
import ui_picker
import ui_render
from ui_settings import SettingsPanel, format_duration

try:
    from i18n import _, ngettext
except ImportError:
    def _(s):
        return s

    def ngettext(singular, plural, n):
        return singular if n == 1 else plural

APP_TITLE = "diaporama2screen"


class App(tk.Tk):
    """The application window."""

    def __init__(self):
        super().__init__()
        self.proj = project_mod.Project()
        self.preview = preview_mod.Preview()
        self._preview_job = None
        self._current_photo = None
        self._caption_photo = None    # whose caption the field is holding
        self._shown_image = None      # keeps Tk from discarding the image

        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(900, 600)

        self._build_menu()
        self._build_body()
        self._bind_keys()

        self.settings_panel.load_from_project()
        self.refresh_list()
        self.update_title()
        self.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.after(200, self._check_tools)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------

    def _deferred(self, callback):
        """Wrap a menu command so it runs just after the menu is put away.

        A posted Tk menu holds an exclusive grab on the pointer and the
        keyboard. The command runs while that grab is still being released,
        and a window that opens at that moment is refused the foreground by
        the window manager — which is why a dialog opened from the menu came
        up behind the window while the same dialog opened from the toolbar
        behaved. Returning to the event loop first lets the grab go."""
        def start():
            self.after(80, callback)
        return start

    def _build_menu(self):
        bar = tk.Menu(self)
        later = self._deferred

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label=_("New project"), accelerator="Ctrl+N",
                              command=later(self.on_new))
        file_menu.add_command(label=_("Open…"), accelerator="Ctrl+O",
                              command=later(self.on_open))
        file_menu.add_separator()
        file_menu.add_command(label=_("Save"), accelerator="Ctrl+S",
                              command=later(self.on_save))
        file_menu.add_command(label=_("Save as…"),
                              command=later(self.on_save_as))
        file_menu.add_separator()
        file_menu.add_command(label=_("Import from a tag…"),
                              command=later(self.on_import_tag))
        file_menu.add_command(label=_("Rejected photographs…"),
                              command=later(self.on_rejected))
        file_menu.add_separator()
        file_menu.add_command(label=_("Quit"), command=later(self.on_quit))
        bar.add_cascade(label=_("File"), menu=file_menu)

        lang_menu = tk.Menu(bar, tearoff=0)
        self.var_lang = tk.StringVar(value=i18n.read_language_setting())
        for code, label in (("auto", _("System language")),
                            ("fr", "Français"),
                            ("en", "English")):
            lang_menu.add_radiobutton(label=label, value=code,
                                      variable=self.var_lang,
                                      command=self.on_language)
        bar.add_cascade(label=_("Language"), menu=lang_menu)

        tools_menu = tk.Menu(bar, tearoff=0)
        tools_menu.add_command(label=_("Install a launcher…"),
                               command=later(self.on_install_launcher))
        tools_menu.add_command(label=_("Remove the launcher"),
                               command=later(self.on_remove_launcher))
        tools_menu.add_separator()
        tools_menu.add_command(label=_("Required programs"),
                               command=later(self.on_tools))
        bar.add_cascade(label=_("Tools"), menu=tools_menu)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label=_("About"), command=later(self.on_about))
        bar.add_cascade(label=_("Help"), menu=help_menu)

        self.configure(menu=bar)

    @staticmethod
    def _button_width(labels):
        """A ttk button width, in characters, that holds every label.

        ttk counts a width in characters, not pixels, so counting the letters
        of the longest label is only right for the font it was counted in.
        The labels are therefore measured in the font actually in use and
        converted back into ttk's unit, with two characters to spare."""
        labels = list(labels)      # the fallback must still see them
        try:
            import tkinter.font as tkfont
            font = tkfont.nametofont("TkDefaultFont")
            unit = max(1, font.measure("0"))
            widest = max(font.measure(label) for label in labels)
            return widest // unit + 2
        except Exception:
            return max(len(label) for label in labels) + 2

    def _build_body(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(side="top", fill="x")
        ttk.Button(toolbar, text=_("Add photos…"),
                   command=self.on_add_photos).pack(side="left")
        ttk.Button(toolbar, text=_("Remove from the slideshow"),
                   command=self.on_remove).pack(side="left", padx=(18, 0))
        ttk.Button(toolbar, text=_("Re-read the captions"),
                   command=self.on_refresh_captions).pack(side="left",
                                                          padx=(18, 0))
        ttk.Button(toolbar, text=_("Write captions into the files…"),
                   command=self.on_write_all).pack(side="left", padx=(6, 0))

        self.status = ttk.Label(self, anchor="w", padding=(10, 4))
        self.status.pack(side="bottom", fill="x")

        self.settings_panel = SettingsPanel(self, self)
        self.settings_panel.pack(side="bottom", fill="x")

        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x")

        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 6))

        panes.add(self._build_list(panes), weight=3)
        panes.add(self._build_preview(panes), weight=4)

    def _build_list(self, parent):
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("n", "name", "caption")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings",
                                 selectmode="extended")
        self.tree.heading("n", text="#")
        self.tree.heading("name", text=_("File"))
        self.tree.heading("caption", text=_("Caption"))
        self.tree.column("n", width=48, anchor="e", stretch=False)
        self.tree.column("name", width=210, anchor="w")
        self.tree.column("caption", width=260, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("missing", foreground="#b00020")
        self.tree.tag_configure("nocaption", foreground="#777777")

        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        order = ttk.Frame(frame, padding=(0, 6, 0, 0))
        order.grid(row=1, column=0, columnspan=2, sticky="w")
        # The four buttons share one width so that the row stays even, and
        # that width is taken from the longest label in the language actually
        # in use rather than fixed: "Descendre" needs more room than "Down",
        # and a ttk width is counted in characters, so a fixed one truncates
        # as soon as a translation is longer than the English it was set for.
        moves = ((_("Top"), lambda: self.on_edge(True)),
                 (_("Up"), lambda: self.on_move(-1)),
                 (_("Down"), lambda: self.on_move(1)),
                 (_("Bottom"), lambda: self.on_edge(False)))
        move_width = self._button_width(label for label, _command in moves)
        for position, (label, command) in enumerate(moves):
            ttk.Button(order, text=label, width=move_width,
                       command=command).pack(
                           side="left", padx=((4, 0) if position else 0))
        ttk.Button(order, text=_("Sort by name"),
                   command=self.on_sort_name).pack(side="left", padx=(16, 0))
        ttk.Button(order, text=_("Sort by date"),
                   command=self.on_sort_date).pack(side="left", padx=(4, 0))
        return frame

    def _build_preview(self, parent):
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        holder = tk.Frame(frame, background="#1c1c1c", highlightthickness=0)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.bind("<Configure>", self._on_preview_resize)
        self.preview_holder = holder

        self.preview_label = tk.Label(holder, background="#1c1c1c",
                                      foreground="#cccccc",
                                      text=_("Select a photo to see it here."))
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")

        info_line = ttk.Frame(frame)
        info_line.grid(row=1, column=0, sticky="ew")
        info_line.columnconfigure(0, weight=1)
        self.lbl_info = ttk.Label(info_line, anchor="w",
                                  padding=(2, 6, 2, 0))
        self.lbl_info.grid(row=0, column=0, sticky="ew")
        self.btn_copy_path = ttk.Button(
            info_line, text=_("Copy the path"), command=self.on_copy_path)
        self.btn_copy_path.grid(row=0, column=1, sticky="e", padx=(8, 2))
        self.btn_copy_path.state(["disabled"])

        # The whole path, wrapped rather than cut: knowing which of two
        # folders a photograph came from is the point, and a path shortened
        # in the middle hides exactly that. Grey and small, so it informs
        # without competing with the caption below.
        self.lbl_path = ttk.Label(frame, anchor="w", justify="left",
                                  foreground="#777777",
                                  padding=(2, 1, 2, 0))
        self.lbl_path.grid(row=2, column=0, sticky="ew")

        # The same two actions under the right button, for whoever looks
        # for them there. The button alone would be discoverable but not
        # where the path actually is; the menu alone would be invisible.
        self.path_menu = tk.Menu(self, tearoff=0)
        self.path_menu.add_command(label=_("Copy the path"),
                                   command=self.on_copy_path)
        self.path_menu.add_command(label=_("Copy the file name"),
                                   command=self.on_copy_name)
        self.path_menu.add_separator()
        self.path_menu.add_command(label=_("Open the containing folder"),
                                   command=self.on_open_containing)
        for widget in (self.lbl_info, self.lbl_path):
            widget.bind("<Button-3>", self._post_path_menu)

        caption_box = ttk.LabelFrame(frame, text=_("Caption"), padding=(8, 6))
        caption_box.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        caption_box.columnconfigure(0, weight=1)

        self.var_caption = tk.StringVar()
        self.entry_caption = ttk.Entry(caption_box,
                                       textvariable=self.var_caption)
        self.entry_caption.grid(row=0, column=0, sticky="ew")
        self.entry_caption.bind("<Return>", self.on_caption_apply)
        self.entry_caption.bind("<FocusOut>", self.on_caption_apply)

        ttk.Button(caption_box, text=_("Restore the file's caption"),
                   command=self.on_caption_reset).grid(row=0, column=1,
                                                       sticky="e",
                                                       padx=(8, 0))
        ttk.Button(caption_box, text=_("Write into the file"),
                   command=self.on_write_one).grid(row=0, column=2,
                                                   sticky="e", padx=(6, 0))
        self.lbl_caption_origin = ttk.Label(caption_box, text="",
                                            foreground="#777777")
        self.lbl_caption_origin.grid(row=1, column=0, columnspan=2,
                                     sticky="w", pady=(4, 0))
        return frame

    def _bind_keys(self):
        self.bind("<Control-n>", lambda e: self.on_new())
        self.bind("<Control-o>", lambda e: self.on_open())
        self.bind("<Control-s>", lambda e: self.on_save())
        self.tree.bind("<Delete>", lambda e: self.on_remove())

    # ------------------------------------------------------------------
    # the list
    # ------------------------------------------------------------------

    def selected_indexes(self):
        return sorted(int(iid) for iid in self.tree.selection())

    def _row(self, index):
        """The values and tags of one line of the list."""
        photo = self.proj.photos[index]
        if not photo.exists:
            return (index + 1, photo.name, _("file not found")), ("missing",)
        if not photo.caption:
            return (index + 1, photo.name, ""), ("nocaption",)
        caption = photo.caption
        if photo.has_override:
            caption = "* " + caption
        return (index + 1, photo.name, caption), ()

    def _update_row(self, index):
        """Rewrite one line in place, leaving the selection alone.

        Rebuilding the whole list to show a changed caption used to cost the
        user the line they had just clicked: the click moved the focus out
        of the caption field, which applied the caption, which rebuilt the
        list and put the selection back where it had been."""
        iid = str(index)
        if self.tree.exists(iid):
            values, tags = self._row(index)
            self.tree.item(iid, values=values, tags=tags)

    def refresh_list(self, select=None):
        """Rebuild the list. `select` is a list of indexes to re-select."""
        keep = select if select is not None else self.selected_indexes()
        self.tree.delete(*self.tree.get_children())
        for i, _photo in enumerate(self.proj.photos):
            values, tags = self._row(i)
            self.tree.insert("", "end", iid=str(i), values=values, tags=tags)
        for i in keep:
            if 0 <= i < len(self.proj.photos):
                self.tree.selection_add(str(i))
        if keep:
            first = [i for i in keep if 0 <= i < len(self.proj.photos)]
            if first:
                self.tree.see(str(first[0]))
        self.refresh_status()
        self.settings_panel.refresh_estimate()

    def refresh_status(self):
        total, captioned, overridden, gone = self.proj.counts()
        if total == 0:
            self.status.configure(text=_("Empty slideshow. Add a folder or "
                                         "some photos to begin."))
            return
        bits = [ngettext("{n} photo", "{n} photos", total).format(n=total),
                ngettext("{n} with a caption", "{n} with captions",
                         captioned).format(n=captioned)]
        if overridden:
            bits.append(ngettext("{n} edited here only",
                                 "{n} edited here only",
                                 overridden).format(n=overridden))
        if gone:
            bits.append(ngettext("{n} missing file", "{n} missing files",
                                 gone).format(n=gone))
        refused = len(self.proj.rejected)
        if refused:
            bits.append(ngettext("{n} rejected", "{n} rejected",
                                 refused).format(n=refused))
        bits.append(_("duration {d}").format(
            d=format_duration(self.proj.duration())))
        self.status.configure(text="   ·   ".join(bits))

    # ------------------------------------------------------------------
    # the preview
    # ------------------------------------------------------------------

    def on_select(self, event=None):
        indexes = self.selected_indexes()
        if len(indexes) == 1:
            self._current_photo = self.proj.photos[indexes[0]]
        else:
            self._current_photo = None
        self._show_caption()
        self._schedule_preview()

    def _on_preview_resize(self, event=None):
        # The wrap width has to follow the panel, otherwise a long path
        # either pushes the window wider or disappears off its edge.
        if event is not None and event.width > 40:
            self.lbl_path.configure(wraplength=event.width - 12)
        self._schedule_preview()

    def _schedule_preview(self):
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._show_preview)

    def _show_preview(self):
        self._preview_job = None
        photo = self._current_photo
        if photo is None:
            self._shown_image = None
            self.preview_label.configure(
                image="", text=_("Select a photo to see it here."))
            self.lbl_info.configure(text="")
            self.lbl_path.configure(text="")
            self.btn_copy_path.state(["disabled"])
            return
        if not photo.exists:
            self._shown_image = None
            self.preview_label.configure(image="",
                                         text=_("This file no longer exists."))
            self.lbl_info.configure(text=photo.name)
            self.lbl_path.configure(text=photo.path)
            self.btn_copy_path.state(["!disabled"])
            return
        width = max(64, self.preview_holder.winfo_width() - 16)
        height = max(64, self.preview_holder.winfo_height() - 16)
        image, info = self.preview.get(photo.path, width, height)
        if image is None:
            self._shown_image = None
            self.preview_label.configure(
                image="",
                text=_("This photo cannot be displayed:\n{reason}").format(
                    reason=info))
        else:
            self._shown_image = image
            self.preview_label.configure(image=image, text="")
        date = photo.date or _("no date")
        self.lbl_info.configure(text="{name}   ·   {date}".format(
            name=photo.name, date=date))
        self.lbl_path.configure(text=photo.path)
        self.btn_copy_path.state(["!disabled"])

    # ------------------------------------------------------------------
    # captions
    # ------------------------------------------------------------------

    def _show_caption(self):
        photo = self._current_photo
        # Remember whose caption the field is holding. What the field shows
        # and what the list has selected are not always the same thing for a
        # moment: clicking another line moves the focus before the selection
        # changes, so the edit has to be applied to the photo it was typed
        # for, not to whichever one happens to be selected by then.
        self._caption_photo = photo
        if photo is None:
            self.var_caption.set("")
            self.entry_caption.configure(state="disabled")
            self.lbl_caption_origin.configure(text="")
            return
        self.entry_caption.configure(state="normal")
        self.var_caption.set(photo.caption)
        if photo.has_override:
            self.lbl_caption_origin.configure(
                text=_("Edited here only. In the file: {text}").format(
                    text=photo.file_caption or _("(none)")))
        elif photo.caption:
            self.lbl_caption_origin.configure(text=_("Read from the file."))
        else:
            self.lbl_caption_origin.configure(
                text=_("This photo has no caption in its metadata."))

    def _post_path_menu(self, event):
        if self._current_photo is None:
            return
        try:
            self.path_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.path_menu.grab_release()

    def _copy(self, text):
        """Put some text on the clipboard and say so for a moment.

        Tk hands the clipboard over as long as the application runs; what is
        copied here is therefore available until diaporama2screen is closed,
        which is the usual X11 behaviour rather than a limitation of ours."""
        if not text:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError:
            return
        self.btn_copy_path.configure(text=_("Copied"))
        self.after(1500, self._restore_copy_button)

    def on_copy_path(self):
        if self._current_photo is not None:
            self._copy(self._current_photo.path)

    def on_copy_name(self):
        if self._current_photo is not None:
            self._copy(self._current_photo.name)

    def _restore_copy_button(self):
        try:
            self.btn_copy_path.configure(text=_("Copy the path"))
        except tk.TclError:
            pass

    def on_open_containing(self):
        photo = self._current_photo
        if photo is None:
            return
        folder = os.path.dirname(photo.path)
        try:
            subprocess.Popen(["xdg-open", folder])
        except OSError as exc:
            ui_dialogs.error(self, str(exc))

    def on_caption_apply(self, event=None):
        photo = self._caption_photo
        if photo is None:
            return
        try:
            index = self.proj.photos.index(photo)
        except ValueError:
            return
        text = self.var_caption.get().strip()
        if text == photo.caption:
            return
        self.proj.set_override(index, text)
        self._update_row(index)
        self._show_caption()
        self.update_title()

    def on_caption_reset(self):
        photo = self._current_photo
        if photo is None:
            return
        try:
            index = self.proj.photos.index(photo)
        except ValueError:
            return
        self.proj.set_override(index, None)
        self._update_row(index)
        self._show_caption()
        self.update_title()

    def on_refresh_captions(self):
        """Re-read every caption from the files. Project-only edits are kept."""
        self.proj.refresh_metadata()
        self.refresh_list()
        self._show_caption()

    # ---- writing captions into the user's own photographs ----

    def on_write_one(self):
        photo = self._current_photo
        if photo is None:
            return
        if not photo.has_override:
            ui_dialogs.info(self, _("This caption is already the one in the "
                                    "file. There is nothing to write."))
            return
        self._write_captions([photo])

    def on_write_all(self):
        pending = [p for p in self.proj.photos if p.has_override and p.exists]
        if not pending:
            ui_dialogs.info(self, _("No caption has been edited here, so "
                                    "there is nothing to write."))
            return
        self._write_captions(pending)

    def _write_captions(self, photos):
        """Write the project's captions into the photographs themselves.
        This is the only place in the application that modifies the user's
        own files, and it never happens without this confirmation."""
        if len(photos) == 1:
            question = _("Write this caption into the photograph itself?\n\n"
                         "{name}\n{caption}").format(
                name=photos[0].name, caption=photos[0].caption or _("(empty)"))
        else:
            question = ngettext(
                "Write {n} caption into the photograph itself?",
                "Write {n} captions into the photographs themselves?",
                len(photos)).format(n=len(photos))
        question += "\n\n" + _("The files are modified. digiKam will show the "
                               "new captions once it re-reads them.")

        go, keep = ui_dialogs.confirm_with_option(
            self, question,
            _("Keep a copy of each original file (name_original)"),
            option_default=True,
            title=_("Write into the files"),
            ok_text=_("Write"))
        if not go:
            return

        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            written, failures = metadata.write_many(
                [(p.path, p.caption) for p in photos], keep_backup=keep)
            self.proj.refresh_metadata(photos)
            for photo in photos:
                if photo.override == photo.file_caption:
                    photo.override = None
        finally:
            self.configure(cursor="")

        self.refresh_list()
        self._show_caption()
        self.update_title()

        if failures:
            detail = "\n".join("  {}: {}".format(os.path.basename(p), why)
                               for p, why in failures[:8])
            if len(failures) > 8:
                detail += "\n  …"
            ui_dialogs.warning(
                self,
                _("{ok} captions written, {bad} failed:\n{detail}").format(
                    ok=written, bad=len(failures), detail=detail))
        else:
            ui_dialogs.success(
                self, ngettext("{n} caption written into the file.",
                               "{n} captions written into the files.",
                               written).format(n=written))

    # ------------------------------------------------------------------
    # adding, removing, ordering
    # ------------------------------------------------------------------

    def _last_folder(self):
        if self.proj.photos:
            return os.path.dirname(self.proj.photos[-1].path)
        return i18n.read_setting("last_photo_folder", os.path.expanduser("~"))

    def on_add_photos(self):
        """One dialog: browse folders and tick the photos, on the picture."""
        start = self._last_folder()
        already = {p.path for p in self.proj.photos}
        chosen = ui_picker.choose(self, start, already=already,
                                  recursive=i18n.read_setting(
                                      "include_subfolders", False),
                                  title=_("Choose the photos to add"))
        if not chosen:
            return
        i18n.write_setting("last_photo_folder", os.path.dirname(chosen[0]))
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            added, skipped, refused = self.proj.add_paths(chosen)
        finally:
            self.configure(cursor="")
        self.refresh_list()
        self.update_title()
        self._report_added(added, skipped, refused)

    def _report_added(self, added, skipped, refused=0):
        if refused:
            ui_dialogs.info(
                self,
                ngettext(
                    "{added} added. {refused} photograph was left out "
                    "because it had been taken out of this slideshow "
                    "before. File ▸ Rejected photographs… undoes that.",
                    "{added} added. {refused} photographs were left out "
                    "because they had been taken out of this slideshow "
                    "before. File ▸ Rejected photographs… undoes that.",
                    refused).format(added=added, refused=refused))
            return
        if added == 0 and skipped:
            ui_dialogs.info(
                self,
                _("Nothing added: those photos are already in the slideshow, "
                  "or are not images."))

    def on_import_tag(self):
        """Add the photographs that carry a tag chosen in digiKam."""
        missing = deps.missing(deps.FOR_CAPTIONS)
        if missing:
            ui_dialogs.error(self, deps.report(deps.FOR_CAPTIONS))
            return

        # Not _last_folder(): that one follows the last photograph added,
        # which is a leaf deep in the tree — a poor place to start a sweep
        # for tags. The sweep remembers its own folder, and falls back to
        # the pictures folder the first time.
        start = (i18n.read_setting("last_tag_folder", "")
                 or paths.pictures_dir())
        chosen, replace = ui_import.choose(
            self, start, title=_("Import from a tag"))
        if not chosen:
            return

        if replace and not self._confirm_discard():
            return

        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            if replace:
                self.proj = project_mod.Project()
                self.settings_panel.load_from_project()
            added, skipped, refused = self.proj.add_paths(
                chosen, respect_rejections=True)
        finally:
            self.configure(cursor="")
        self.refresh_list()
        self.update_title()
        self._report_added(added, skipped, refused)

    def on_rejected(self):
        """Show what was taken out of the slideshow, and let it back in."""
        if ui_rejects.show(self, self.proj,
                           title=_("Rejected photographs")):
            self.update_title()
            self.refresh_status()

    def on_remove(self):
        indexes = self.selected_indexes()
        if not indexes:
            return
        self.proj.remove(indexes)
        self._current_photo = None
        self.refresh_list(select=[])
        self._show_caption()
        self._schedule_preview()
        self.update_title()

    def on_move(self, delta):
        indexes = self.selected_indexes()
        if not indexes:
            return
        new = self.proj.move(indexes, delta)
        self.refresh_list(select=new)
        self.update_title()

    def on_edge(self, to_start):
        indexes = self.selected_indexes()
        if not indexes:
            return
        new = self.proj.move_to_edge(indexes, to_start)
        self.refresh_list(select=new)
        self.update_title()

    def on_sort_name(self):
        self.proj.sort_by_name()
        self.refresh_list(select=[])
        self.update_title()

    def on_sort_date(self):
        self.proj.sort_by_date()
        self.refresh_list(select=[])
        self.update_title()

    # ------------------------------------------------------------------
    # production
    # ------------------------------------------------------------------

    def on_produce(self):
        missing = deps.missing(deps.FOR_IMAGES + deps.FOR_VIDEO)
        if missing:
            ui_dialogs.error(self, deps.report(deps.FOR_IMAGES
                                               + deps.FOR_VIDEO))
            return

        usable = [p for p in self.proj.photos if p.exists]
        if not usable:
            ui_dialogs.warning(self, _("None of these photos can be read."))
            return
        gone = len(self.proj.photos) - len(usable)
        if gone:
            if not ui_dialogs.confirm(
                    self,
                    ngettext(
                        "{n} file is missing and will be left out. Continue?",
                        "{n} files are missing and will be left out. "
                        "Continue?", gone).format(n=gone),
                    ok_text=_("Continue")):
                return

        target = self.proj.video_path()
        if os.path.exists(target):
            if not ui_dialogs.confirm(
                    self,
                    _("“{f}” already exists. Replace it?").format(
                        f=os.path.basename(target)),
                    ok_text=_("Replace"), kind="warning"):
                return

        images = self.proj.images_dir()
        if not ui_dialogs.confirm(
                self,
                _("The laid-out images go to:\n{images}\n\n"
                  "The video goes to:\n{video}\n\n"
                  "Numbered images already in that folder are replaced.")
                .format(images=images, video=target),
                ok_text=_("Produce"), title=_("Produce the video")):
            return

        result = ui_render.produce(self, self.proj)
        if result:
            self.settings_panel.refresh_outputs()

    # ------------------------------------------------------------------
    # project files
    # ------------------------------------------------------------------

    def update_title(self):
        name = self.proj.title or _("untitled")
        mark = "*" if self.proj.dirty else ""
        self.title("{mark}{name} — {app}".format(mark=mark, name=name,
                                                 app=APP_TITLE))
        self.refresh_status()
        self.settings_panel.refresh_outputs()

    def _confirm_discard(self):
        """True when it is safe to drop the current project."""
        if not self.proj.dirty:
            return True
        answer = ui_dialogs.ask_save_discard_cancel(
            self, _("This project has unsaved changes. Save it now?"))
        if answer is None:
            return False
        if answer:
            return self.on_save()
        return True

    def on_new(self):
        if not self._confirm_discard():
            return
        self.proj = project_mod.Project()
        self._current_photo = None
        self.preview.clear()
        self.settings_panel.load_from_project()
        self.refresh_list(select=[])
        self._show_caption()
        self._schedule_preview()
        self.update_title()

    def on_open(self):
        if not self._confirm_discard():
            return
        paths.ensure(paths.projects_dir())
        name = ui_dialogs.pick_open(
            self, title=_("Open a project"),
            initialdir=paths.projects_dir(),
            pattern="*" + project_mod.SUFFIX,
            pattern_label=_("Slideshow projects"))
        if not name:
            return
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            self.proj = project_mod.Project.load(name)
        except (OSError, ValueError) as exc:
            ui_dialogs.error(
                self,
                _("This project could not be opened:\n{reason}").format(
                    reason=exc))
            return
        finally:
            self.configure(cursor="")
        self._current_photo = None
        self.preview.clear()
        self.settings_panel.load_from_project()
        self.refresh_list(select=[])
        self._show_caption()
        self._schedule_preview()
        self.update_title()

    def on_save(self):
        if not self.proj.file_path:
            return self.on_save_as()
        return self._save_to(self.proj.file_path)

    def on_save_as(self):
        paths.ensure(paths.projects_dir())
        name = ui_dialogs.pick_save(
            self, title=_("Save the project"),
            initialdir=paths.projects_dir(),
            initialfile=(self.proj.title or _("slideshow"))
            + project_mod.SUFFIX,
            suffix=project_mod.SUFFIX,
            pattern="*" + project_mod.SUFFIX,
            pattern_label=_("Slideshow projects"))
        if not name:
            return False
        return self._save_to(name)

    def _save_to(self, name):
        try:
            self.proj.save(name)
        except (OSError, ValueError) as exc:
            ui_dialogs.error(
                self,
                _("This project could not be saved:\n{reason}").format(
                    reason=exc))
            return False
        self.update_title()
        return True

    def on_quit(self):
        if not self._confirm_discard():
            return
        self.destroy()

    # ------------------------------------------------------------------
    # language, tools, about
    # ------------------------------------------------------------------

    def on_language(self):
        i18n.write_language_setting(self.var_lang.get())
        ui_dialogs.info(
            self,
            _("The language will change the next time the application "
              "starts."))

    def _check_tools(self):
        report = deps.report(deps.FOR_CAPTIONS + deps.FOR_IMAGES)
        if report:
            ui_dialogs.warning(self, report)

    def on_tools(self):
        report = deps.report()
        ui_dialogs.info(self,
                        report or _("Every required program is installed."))

    def on_install_launcher(self):
        in_menu, on_desktop = launcher.is_installed()
        question = _("Put diaporama2screen in the Graphics group of the "
                     "menu, and a launcher on the desktop?")
        if in_menu or on_desktop:
            question += "\n\n" + _("An existing launcher will be replaced.")
        go, with_desktop = ui_dialogs.confirm_with_option(
            self, question, _("Also put a launcher on the desktop"),
            option_default=True, title=_("Install a launcher"),
            ok_text=_("Install"), kind="question")
        if not go:
            return
        written, problems = launcher.install(in_menu=True,
                                             on_desktop=with_desktop)
        if problems and not written:
            ui_dialogs.error(self, "\n".join(problems))
            return
        message = _("Launcher installed:") + "\n" + "\n".join(
            "  " + p for p in written)
        if problems:
            message += "\n\n" + "\n".join(problems)
        message += "\n\n" + _("The menu may take a moment to notice it.")
        ui_dialogs.success(self, message)

    def on_remove_launcher(self):
        gone = launcher.remove()
        if gone:
            ui_dialogs.info(self, _("Launcher removed:") + "\n"
                            + "\n".join("  " + p for p in gone))
        else:
            ui_dialogs.info(self, _("No launcher was installed."))

    def on_about(self):
        # The version rides in through {app} on purpose: the sentence itself
        # is unchanged, so the translation catalogues stay valid.
        ui_dialogs.info(
            self,
            _("{app}\n\nBuild a photo slideshow with captions burnt into the "
              "image, ready to play on a television.").format(
                  app="{} {}".format(APP_TITLE, paths.APP_VERSION)))
