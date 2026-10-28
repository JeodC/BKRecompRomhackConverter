"""The converter window."""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import bkrom, convert, mod_files, notecount, project_file
from map_names import MAP_NAMES

TITLE = "BK Recomp Romhack Converter"
ROM_TYPES = [("N64 ROM", "*.z64 *.n64 *.v64"), ("All files", "*.*")]
ROMHACK_TYPES = [("BPS patch or N64 ROM", "*.bps *.z64 *.n64 *.v64"), ("All files", "*.*")]
EXE_TYPES = [("Program", "*.exe"), ("All files", "*.*")] if os.name == "nt" else [("All files", "*")]
PNG_TYPES = [("PNG image", "*.png")]
MD_TYPES = [("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")]
PROJECT_TYPES = [("Converter project", "*" + project_file.PROJECT_SUFFIX)]


def _parse_int(text):
    text = text.strip()
    return int(text, 0) if text else 0


def _open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


class EditableTable(ttk.Frame):
    def __init__(self, parent, columns, widths, height=10):
        super().__init__(parent)
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=height, selectmode="extended")
        for column, width in zip(columns, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._edit)
        self.read_only_columns = set()

    def _edit(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or not column:
            return
        index = int(column[1:]) - 1
        if index in self.read_only_columns:
            return
        x, y, w, h = self.tree.bbox(item, column)
        entry = ttk.Entry(self.tree)
        entry.insert(0, self.tree.item(item, "values")[index])
        entry.select_range(0, "end")
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus()

        def commit(_=None):
            values = list(self.tree.item(item, "values"))
            values[index] = entry.get()
            self.tree.item(item, values=values)
            entry.destroy()
            self.event_generate("<<TableEdited>>")

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda _: entry.destroy())

    def rows(self):
        return [self.tree.item(item, "values") for item in self.tree.get_children()]

    def set_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", values=row)

    def add(self, row):
        self.tree.see(self.tree.insert("", "end", values=row))

    def remove_selected(self):
        self.tree.delete(*self.tree.selection())


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITLE)
        self.geometry("900x760")
        self.minsize(760, 600)
        self.project_path = None
        self.message_queue = queue.Queue()
        self.busy = False
        self.icon_image = None

        self.fields = {name: tk.StringVar() for name in (
            "vanilla_rom", "romhack", "romhack_tool", "output_dir", "thumbnail",
            "mod_id", "display_name", "version", "authors", "short_description", "minimum_recomp_version",
            "package_name", "website_url", "icon_path")}
        self.note_saving = tk.BooleanVar(value=True)
        self.make_thunderstore = tk.BooleanVar(value=True)

        self._build_menu()
        self._build_layout()
        self.load_project(project_file.Project())
        self.after(100, self._poll_messages)

    def _build_menu(self):
        bar = tk.Menu(self)
        menu = tk.Menu(bar, tearoff=False)
        menu.add_command(label="New project", command=self.new_project)
        menu.add_command(label="Open project...", command=self.open_project)
        menu.add_command(label="Save project", command=self.save_project, accelerator="Ctrl+S")
        menu.add_command(label="Save project as...", command=lambda: self.save_project(ask=True))
        menu.add_separator()
        menu.add_command(label="Exit", command=self.destroy)
        bar.add_cascade(label="File", menu=menu)
        self.config(menu=bar)
        self.bind("<Control-s>", lambda _: self.save_project())

    def _build_layout(self):
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        notebook.add(self._files_tab(notebook), text="Files")
        notebook.add(self._mod_tab(notebook), text="Mod info")
        notebook.add(self._notes_tab(notebook), text="Notes")
        notebook.add(self._thunderstore_tab(notebook), text="Thunderstore")

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        self.convert_button = ttk.Button(bottom, text="Convert", command=self.run_conversion)
        self.convert_button.pack(side="right")
        self.status_label = ttk.Label(bottom, text="")
        self.status_label.pack(side="left")
        self.log_view = ScrolledText(outer, height=9, state="disabled", wrap="word", font="TkFixedFont")
        self.log_view.pack(fill="both", pady=(8, 0))

    def _path_row(self, parent, row, label, variable, filetypes=None, folder=False, note=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=6)

        def browse():
            if folder:
                path = filedialog.askdirectory()
            else:
                path = filedialog.askopenfilename(filetypes=filetypes)
            if path:
                variable.set(os.path.normpath(path))

        ttk.Button(parent, text="Browse...", command=browse).grid(row=row, column=2)
        if note:
            ttk.Label(parent, text=note, foreground="gray").grid(row=row + 1, column=1, sticky="w", padx=6)

    def _entry_row(self, parent, row, label, variable, note=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=6)
        if note:
            ttk.Label(parent, text=note, foreground="gray").grid(row=row + 1, column=1, sticky="w", padx=6)

    def _text_row(self, parent, row, label, height):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", pady=3)
        text = tk.Text(parent, height=height, wrap="word", undo=True, font="TkTextFont")
        text.grid(row=row, column=1, columnspan=2, sticky="nsew", padx=6, pady=3)
        return text

    def _files_tab(self, parent):
        tab = ttk.Frame(parent, padding=10)
        tab.columnconfigure(1, weight=1)
        self._path_row(tab, 0, "Banjo-Kazooie ROM", self.fields["vanilla_rom"], ROM_TYPES,
                       note="The unmodified NTSC-U 1.0 (Rev 0) ROM, the same one Banjo: Recompiled uses.")
        self._path_row(tab, 2, "Romhack", self.fields["romhack"], ROMHACK_TYPES,
                       note="Your romhack's .bps patch, or the patched ROM.")
        self._path_row(tab, 4, "BKRecompRomhackTool", self.fields["romhack_tool"], EXE_TYPES,
                       note="Not included with this converter. Get it from Wiseguy "
                            "(github.com/Mr-Wiseguy/BKRecompRomhackTool).")
        self._path_row(tab, 6, "Output folder", self.fields["output_dir"], folder=True)
        return tab

    def _mod_tab(self, parent):
        tab = ttk.Frame(parent, padding=10)
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="What Banjo: Recompiled shows in its mod menu. Examples are from The Jiggies of Time.",
                  foreground="gray").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._entry_row(tab, 1, "Mod ID", self.fields["mod_id"],
                        note="Lowercase letters, numbers and underscores. Keep it the same between versions. "
                             "e.g. bk_jiggies_of_time")
        self._entry_row(tab, 3, "Display name", self.fields["display_name"], note="e.g. BK The Jiggies of Time")
        self._entry_row(tab, 5, "Version", self.fields["version"], note="e.g. 1.0.1")
        self._entry_row(tab, 7, "Authors", self.fields["authors"], note="Separate several with commas, e.g. Kurko Mods")
        self._entry_row(tab, 9, "Short description", self.fields["short_description"],
                        note="One line for the mod list. Long text gets cut off. "
                             "e.g. Explore the land of Hyrule with Banjo & Kazooie!")
        self.mod_description = self._text_row(tab, 11, "Description", 6)
        tab.rowconfigure(11, weight=1)
        ttk.Label(tab, text="e.g. A full mod crossover between BK and Ocarina Of Time.",
                  foreground="gray").grid(row=12, column=1, sticky="w", padx=6)
        self._entry_row(tab, 13, "Minimum version", self.fields["minimum_recomp_version"],
                        note="The oldest Banjo: Recompiled the mod runs on, e.g. 1.0.0")
        self._path_row(tab, 15, "In-game thumbnail", self.fields["thumbnail"], PNG_TYPES,
                       note="PNG, 256x256 recommended. Leave empty to use the Thunderstore icon.")
        return tab

    def _notes_tab(self, parent):
        tab = ttk.Frame(parent, padding=10)
        tab.columnconfigure(0, weight=1)
        ttk.Checkbutton(tab, text="Support Banjo: Recompiled's note saving", variable=self.note_saving,
                        command=self._sync_note_state).grid(row=0, column=0, sticky="w")
        ttk.Label(tab, text="Count the notes from your romhack, then double-click a cell to add bundle notes:\n"
                          "ones dropped by enemies or objects instead of placed in the map.",
                  foreground="gray", justify="left").grid(row=1, column=0, sticky="w", pady=(2, 6))

        buttons = ttk.Frame(tab)
        buttons.grid(row=2, column=0, sticky="w")
        self.count_button = ttk.Button(buttons, text="Count notes from romhack", command=self.count_notes)
        self.count_button.pack(side="left")
        ttk.Button(buttons, text="Add map",
                   command=lambda: self.note_table.add(("0x00", "", "0", "0"))).pack(side="left", padx=4)
        ttk.Button(buttons, text="Remove",
                   command=lambda: (self.note_table.remove_selected(), self._update_note_total())).pack(side="left")
        self.note_total = ttk.Label(buttons, text="")
        self.note_total.pack(side="left", padx=10)

        self.note_table = EditableTable(tab, ("Map", "Vanilla name", "Static notes", "Bundle notes"),
                                        (70, 260, 110, 110))
        self.note_table.read_only_columns = {1}
        self.note_table.grid(row=3, column=0, sticky="nsew", pady=4)
        self.note_table.bind("<<TableEdited>>", lambda _: self._refresh_note_names())
        tab.rowconfigure(3, weight=1)

        ttk.Label(tab, text="Hidden actors (optional)").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Label(tab, text="Actors to hide while note saving is on, e.g. signs saying notes reset. FFFF means any.\n"
                          "One entry per actor ID. The Jiggies of Time hides actor 0x0054, model 0x03EB.",
                  foreground="gray", justify="left").grid(row=5, column=0, sticky="w")
        actor_buttons = ttk.Frame(tab)
        actor_buttons.grid(row=6, column=0, sticky="w", pady=2)
        ttk.Button(actor_buttons, text="Add actor",
                   command=lambda: self.actor_table.add(("0x0000", "0xFFFF", "0xFFFF"))).pack(side="left")
        ttk.Button(actor_buttons, text="Remove",
                   command=lambda: self.actor_table.remove_selected()).pack(side="left", padx=4)
        self.actor_table = EditableTable(tab, ("Actor ID", "Model ID", "Type field"), (120, 120, 120), height=4)
        self.actor_table.grid(row=7, column=0, sticky="ew")
        return tab

    def _thunderstore_tab(self, parent):
        tab = ttk.Frame(parent, padding=10)
        tab.columnconfigure(1, weight=1)
        ttk.Checkbutton(tab, text="Make a Thunderstore package", variable=self.make_thunderstore).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self._entry_row(tab, 1, "Package name", self.fields["package_name"],
                        note="Letters, numbers and underscores only, e.g. BK_The_Jiggies_of_Time")
        ttk.Label(tab, text="Description").grid(row=3, column=0, sticky="nw", pady=3)
        self.thunderstore_description = tk.Text(tab, height=3, wrap="word", font="TkTextFont")
        self.thunderstore_description.grid(row=3, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        self.description_counter = ttk.Label(tab, text="", foreground="gray")
        self.description_counter.grid(row=4, column=1, sticky="w", padx=6)
        self.thunderstore_description.bind("<KeyRelease>", lambda _: self._update_description_counter())
        self._entry_row(tab, 5, "Website URL", self.fields["website_url"],
                        note="Optional, e.g. https://github.com/Mr-Wiseguy/JiggiesOfTimeRecomp")
        ttk.Label(tab, text="Dependencies").grid(row=7, column=0, sticky="nw", pady=3)
        self.dependencies = tk.Text(tab, height=2, wrap="none", font="TkFixedFont")
        self.dependencies.grid(row=7, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        ttk.Label(tab, text="One per line, as Author-Package-1.0.0. Usually none.",
                  foreground="gray").grid(row=8, column=1, sticky="w", padx=6)

        icon_row = ttk.Frame(tab)
        icon_row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        icon_row.columnconfigure(1, weight=1)
        self._path_row(icon_row, 0, "Icon", self.fields["icon_path"], PNG_TYPES, note="Your own 256x256 PNG.")
        self.icon_preview = ttk.Label(icon_row)
        self.icon_preview.grid(row=0, column=3, rowspan=2, padx=(8, 0))
        self.fields["icon_path"].trace_add("write", lambda *_: self._update_icon())

        markdown_tabs = ttk.Notebook(tab)
        markdown_tabs.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        tab.rowconfigure(10, weight=1)
        self.readme = self._markdown_page(markdown_tabs, "README.md")
        self.changelog = self._markdown_page(markdown_tabs, "CHANGELOG.md (optional)")
        return tab

    def _markdown_page(self, notebook, title):
        page = ttk.Frame(notebook, padding=4)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        text = ScrolledText(page, wrap="word", undo=True, font="TkFixedFont", height=8)

        def import_file():
            path = filedialog.askopenfilename(filetypes=MD_TYPES)
            if path:
                with open(path, encoding="utf-8") as file:
                    text.delete("1.0", "end")
                    text.insert("1.0", file.read())

        ttk.Button(page, text="Import file...", command=import_file).grid(row=0, column=0, sticky="w")
        text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        notebook.add(page, text=title)
        return text

    def _set_text(self, widget, value):
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def _get_text(self, widget):
        return widget.get("1.0", "end-1c")

    def _update_description_counter(self):
        length = len(self._get_text(self.thunderstore_description).strip())
        self.description_counter.configure(
            text=f"{length} / {mod_files.THUNDERSTORE_DESCRIPTION_MAX}. "
                 "e.g. A full mod crossover between BK and Ocarina Of Time.",
            foreground="red" if length > mod_files.THUNDERSTORE_DESCRIPTION_MAX else "gray")

    def _update_icon(self):
        path = self.fields["icon_path"].get()
        self.icon_image = None
        if path and os.path.isfile(path) and mod_files.png_size(path):
            try:
                image = tk.PhotoImage(file=path)
                factor = max(1, image.width() // 64)
                self.icon_image = image.subsample(factor, factor)
            except tk.TclError:
                pass
        self.icon_preview.configure(image=self.icon_image or "")

    def _sync_note_state(self):
        state = "normal" if self.note_saving.get() else "disabled"
        self.count_button.configure(state=state)

    def _refresh_note_names(self):
        rows = []
        for row in self.note_table.rows():
            try:
                map_id = _parse_int(row[0])
                name = MAP_NAMES.get(map_id, "")
                rows.append((f"0x{map_id:02X}", name, row[2], row[3]))
            except ValueError:
                rows.append(row)
        self.note_table.set_rows(rows)
        self._update_note_total()

    def _update_note_total(self):
        total = 0
        for row in self.note_table.rows():
            try:
                total += _parse_int(row[2]) + _parse_int(row[3])
            except ValueError:
                pass
        self.note_total.configure(text=f"Total: {total} notes")

    def _set_note_rows(self, counts):
        self.note_table.set_rows([(f"0x{map_id:02X}", MAP_NAMES.get(map_id, ""), static, bundle)
                                  for map_id, (static, bundle) in sorted(counts.items())])
        self._update_note_total()

    def load_project(self, project):
        for key in ("vanilla_rom", "romhack", "romhack_tool", "output_dir", "thumbnail"):
            self.fields[key].set(getattr(project, key))
        mod = project.mod
        self.fields["mod_id"].set(mod.mod_id)
        self.fields["display_name"].set(mod.display_name)
        self.fields["version"].set(mod.version)
        self.fields["authors"].set(", ".join(mod.authors))
        self.fields["short_description"].set(mod.short_description)
        self.fields["minimum_recomp_version"].set(mod.minimum_recomp_version)
        self._set_text(self.mod_description, mod.description)
        thunderstore = project.thunderstore
        self.fields["package_name"].set(thunderstore.package_name)
        self.fields["website_url"].set(thunderstore.website_url)
        self.fields["icon_path"].set(thunderstore.icon_path)
        self._set_text(self.thunderstore_description, thunderstore.description)
        self._set_text(self.dependencies, "\n".join(thunderstore.dependencies))
        self._set_text(self.readme, thunderstore.readme)
        self._set_text(self.changelog, thunderstore.changelog)
        self.make_thunderstore.set(project.make_thunderstore)
        self.note_saving.set(project.note_saving)
        self._set_note_rows(project.note_counts)
        self.actor_table.set_rows([tuple(f"0x{value:04X}" for value in row) for row in project.hidden_actors])
        self._sync_note_state()
        self._update_description_counter()

    def to_project(self):
        project = project_file.Project()
        for key in ("vanilla_rom", "romhack", "romhack_tool", "output_dir", "thumbnail"):
            setattr(project, key, self.fields[key].get().strip())
        project.mod = mod_files.ModInfo(
            mod_id=self.fields["mod_id"].get().strip(),
            version=self.fields["version"].get().strip(),
            display_name=self.fields["display_name"].get().strip(),
            short_description=self.fields["short_description"].get().strip(),
            description=self._get_text(self.mod_description).strip(),
            authors=[author.strip() for author in self.fields["authors"].get().split(",") if author.strip()],
            minimum_recomp_version=self.fields["minimum_recomp_version"].get().strip(),
        )
        project.thunderstore = mod_files.ThunderstoreInfo(
            package_name=self.fields["package_name"].get().strip(),
            description=self._get_text(self.thunderstore_description).strip(),
            website_url=self.fields["website_url"].get().strip(),
            dependencies=[line.strip() for line in self._get_text(self.dependencies).splitlines() if line.strip()],
            readme=self._get_text(self.readme),
            changelog=self._get_text(self.changelog),
            icon_path=self.fields["icon_path"].get().strip(),
        )
        project.make_thunderstore = self.make_thunderstore.get()
        project.note_saving = self.note_saving.get()
        project.note_counts = {}
        for row in self.note_table.rows():
            try:
                project.note_counts[_parse_int(row[0])] = [_parse_int(row[2]), _parse_int(row[3])]
            except ValueError:
                raise ValueError(f"Note table row {row[0]} has a value that isn't a number.")
        project.hidden_actors = []
        for row in self.actor_table.rows():
            try:
                project.hidden_actors.append([_parse_int(value) for value in row])
            except ValueError:
                raise ValueError(f"Hidden actor {row[0]} has a value that isn't a number.")
        return project

    def new_project(self):
        self.project_path = None
        self.title(TITLE)
        self.load_project(project_file.Project())

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=PROJECT_TYPES)
        if path:
            self.open_project_file(path)

    def open_project_file(self, path):
        try:
            self.load_project(project_file.load(path))
        except (OSError, project_file.ProjectFileError) as error:
            messagebox.showerror(TITLE, f"Couldn't open the project:\n{error}")
            return
        self.project_path = path
        self.title(f"{TITLE} - {os.path.basename(path)}")

    def save_project(self, ask=False):
        if ask or not self.project_path:
            name = (self.fields["mod_id"].get().strip() or "romhack") + project_file.PROJECT_SUFFIX
            path = filedialog.asksaveasfilename(filetypes=PROJECT_TYPES, initialfile=name,
                                                defaultextension=project_file.PROJECT_SUFFIX)
            if not path:
                return
            self.project_path = path
        try:
            project_file.save(self.to_project(), self.project_path)
        except (OSError, ValueError) as error:
            messagebox.showerror(TITLE, f"Couldn't save the project:\n{error}")
            return
        self.title(f"{TITLE} - {os.path.basename(self.project_path)}")
        self.status_label.configure(text="Project saved.")

    def _log(self, text):
        self.message_queue.put(("log", text))

    def _poll_messages(self):
        try:
            while True:
                kind, payload = self.message_queue.get_nowait()
                if kind == "log":
                    self.log_view.configure(state="normal")
                    self.log_view.insert("end", payload + "\n")
                    self.log_view.see("end")
                    self.log_view.configure(state="disabled")
                elif kind == "done":
                    self._finish(*payload)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_messages)

    def _run_in_background(self, label, work, on_success):
        if self.busy:
            return
        self.busy = True
        self.convert_button.configure(state="disabled")
        self.status_label.configure(text=label)

        def worker():
            try:
                self.message_queue.put(("done", (on_success, work(), None)))
            except Exception as error:
                self.message_queue.put(("done", (on_success, None, error)))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, on_success, result, error):
        self.busy = False
        self.convert_button.configure(state="normal")
        self.status_label.configure(text="")
        if error is not None:
            self._log(f"Error: {error}")
            messagebox.showerror(TITLE, str(error))
        else:
            on_success(result)

    def report_callback_exception(self, exc, value, tb):
        # The packaged app has no console for Tk's default traceback.
        messagebox.showerror(TITLE, "".join(traceback.format_exception(exc, value, tb)))

    def count_notes(self):
        vanilla_path, romhack_path = self.fields["vanilla_rom"].get().strip(), self.fields["romhack"].get().strip()
        if not vanilla_path or not romhack_path:
            messagebox.showinfo(TITLE, "Choose the Banjo-Kazooie ROM and your romhack on the Files tab first.")
            return

        def work():
            vanilla = bkrom.load_vanilla(vanilla_path)
            romhack, _ = convert.load_romhack(vanilla, romhack_path, self._log)
            return notecount.count_notes(romhack)

        def done(counts):
            self._set_note_rows(counts)
            static = sum(static for static, _ in counts.values())
            bundle = sum(bundle for _, bundle in counts.values())
            self._log(f"Counted {static} static notes and estimated {bundle} bundle notes from huts and note actors. "
                      "Adjust those if your romhack drops notes some other way.")

        self._run_in_background("Counting notes...", work, done)

    def run_conversion(self):
        try:
            project = self.to_project()
        except ValueError as error:
            messagebox.showerror(TITLE, str(error))
            return
        if project.note_saving and not project.note_counts:
            if not messagebox.askyesno(TITLE, "The note table is empty, so the converter will count the "
                                              "notes itself. Continue?"):
                return

        def done(files):
            self._log("Done.")
            if messagebox.askyesno(TITLE, "Finished:\n\n" + "\n".join(os.path.basename(path) for path in files)
                                   + "\n\nOpen the output folder?"):
                _open_folder(project.output_dir)

        self._run_in_background("Converting...", lambda: convert.run(project, self._log), done)


def main(project_path=None):
    app = App()
    if project_path:
        app.open_project_file(project_path)
    app.mainloop()
