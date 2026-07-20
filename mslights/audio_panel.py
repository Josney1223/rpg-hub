"""'Audio' tab: named OST/SFX playlists, one of each playing at once,
plus music-pack import/export."""

import os

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import audio as audiomod
from . import packs

AUDIO_TYPES = [("Audio", "*.ogg *.mp3 *.wav *.flac"), ("All files", "*.*")]


class AudioPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        self.app = app
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(top, text="New playlist", command=self._new).pack(side="left")
        ttk.Button(top, text="Import pack", command=self._import).pack(side="left", padx=4)
        ttk.Button(top, text="Export pack", command=self._export).pack(side="left")

        canvas = tk.Canvas(self, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.holder = ttk.Frame(canvas)
        self.holder.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.holder, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

        ctrl = ttk.LabelFrame(self, text="Playback", padding=6)
        ctrl.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ctrl.columnconfigure(1, weight=1)
        self.now_lbl = ttk.Label(ctrl, text="OST: —    SFX: —")
        self.now_lbl.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(ctrl, text="Music").grid(row=1, column=0, sticky="w")
        self.ost_vol = tk.DoubleVar(value=70)
        ttk.Scale(ctrl, from_=0, to=100, variable=self.ost_vol,
                  command=lambda _=None: self.app.audio.set_ost_volume(self.ost_vol.get() / 100.0)
                  ).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(ctrl, text="Stop", width=6,
                   command=self.app.audio.stop_ost).grid(row=1, column=2)

        ttk.Label(ctrl, text="SFX").grid(row=2, column=0, sticky="w")
        self.sfx_vol = tk.DoubleVar(value=85)
        ttk.Scale(ctrl, from_=0, to=100, variable=self.sfx_vol,
                  command=lambda _=None: self.app.audio.set_sfx_volume(self.sfx_vol.get() / 100.0)
                  ).grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Button(ctrl, text="Stop", width=6,
                   command=self.app.audio.stop_sfx).grid(row=2, column=2)

        ttk.Button(ctrl, text="Stop all audio",
                   command=self.app.audio.stop_all).grid(row=3, column=0, columnspan=3,
                                                         sticky="ew", pady=(6, 0))
        self.app.audio.set_ost_volume(0.70)
        self.app.audio.set_sfx_volume(0.85)
        self.refresh()
        self._tick_now_playing()

    # -- list -------------------------------------------------------------- #
    def refresh(self):
        for w in self.holder.winfo_children():
            w.destroy()
        if not self.app.playlists:
            ttk.Label(self.holder, foreground="#888",
                      text="No playlists yet.\nCreate one, or Import a music pack."
                      ).pack(anchor="w", pady=8, padx=4)
            return
        for pl in self.app.playlists:
            row = ttk.Frame(self.holder)
            row.pack(fill="x", pady=2)
            cat = (pl.get("category") or "OST").upper()
            ttk.Button(row, text="▶", width=3,
                       command=lambda p=pl: self._play(p)).pack(side="left")
            n = len(pl.get("tracks", []))
            ttk.Label(row, text=f"[{cat}] {pl['name']}  ({n})",
                      width=26, anchor="w").pack(side="left")
            ttk.Button(row, text="Del", width=4,
                       command=lambda p=pl: self._delete(p)).pack(side="right")
            ttk.Button(row, text="Edit", width=5,
                       command=lambda p=pl: self._edit(p)).pack(side="right", padx=2)

    def _tick_now_playing(self):
        np = self.app.audio.now_playing()
        self.now_lbl.config(text=f"OST: {np['OST'] or '—'}    SFX: {np['SFX'] or '—'}")
        self.after(500, self._tick_now_playing)

    def _play(self, pl):
        if not pl.get("tracks"):
            self.app.set_status(f"{pl['name']} has no tracks")
            return
        self.app.audio.play(pl)

    def _delete(self, pl):
        self.app.playlists = [p for p in self.app.playlists if p is not pl]
        self.app.save_playlists()
        self.refresh()
        self.app.set_status(f"Removed playlist {pl['name']}")

    # -- editor ------------------------------------------------------------ #
    def _new(self):
        self._edit(None)

    def _edit(self, pl):
        creating = pl is None
        if creating:
            pl = audiomod.new_playlist("New playlist", "OST", [])
        win = tk.Toplevel(self)
        win.title("New playlist" if creating else f"Edit: {pl['name']}")
        win.geometry("460x420")
        win.columnconfigure(1, weight=1)

        ttk.Label(win, text="Name").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        name_e = ttk.Entry(win)
        name_e.insert(0, pl["name"])
        name_e.grid(row=0, column=1, sticky="ew", padx=8)

        ttk.Label(win, text="Type").grid(row=1, column=0, sticky="w", padx=8)
        cat_var = tk.StringVar(value=(pl.get("category") or "OST").upper())
        catf = ttk.Frame(win)
        catf.grid(row=1, column=1, sticky="w", padx=8)
        ttk.Radiobutton(catf, text="OST (music)", variable=cat_var, value="OST").pack(side="left")
        ttk.Radiobutton(catf, text="SFX", variable=cat_var, value="SFX").pack(side="left", padx=8)

        loop_var = tk.BooleanVar(value=pl.get("loop", True))
        shuf_var = tk.BooleanVar(value=pl.get("shuffle", False))
        optf = ttk.Frame(win)
        optf.grid(row=2, column=1, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(optf, text="Loop", variable=loop_var).pack(side="left")
        ttk.Checkbutton(optf, text="Shuffle", variable=shuf_var).pack(side="left", padx=8)

        ttk.Label(win, text="Tracks").grid(row=3, column=0, sticky="nw", padx=8, pady=6)
        listf = ttk.Frame(win)
        listf.grid(row=3, column=1, sticky="nsew", padx=8)
        win.rowconfigure(3, weight=1)
        lb = tk.Listbox(listf, height=8)
        lb.pack(side="left", fill="both", expand=True)
        for t in pl.get("tracks", []):
            lb.insert("end", os.path.basename(t))
        tracks = list(pl.get("tracks", []))

        def add_tracks():
            paths = filedialog.askopenfilenames(title="Add tracks", filetypes=AUDIO_TYPES)
            for p in paths:
                tracks.append(p)
                lb.insert("end", os.path.basename(p))

        def remove_sel():
            for i in reversed(lb.curselection()):
                lb.delete(i)
                del tracks[i]

        bf = ttk.Frame(win)
        bf.grid(row=4, column=1, sticky="w", padx=8, pady=4)
        ttk.Button(bf, text="Add files", command=add_tracks).pack(side="left")
        ttk.Button(bf, text="Remove selected", command=remove_sel).pack(side="left", padx=4)

        def save():
            name = name_e.get().strip() or "Untitled"
            pl.update({"name": name, "category": cat_var.get(),
                       "tracks": list(tracks),
                       "loop": loop_var.get(), "shuffle": shuf_var.get()})
            if creating:
                self.app.playlists.append(pl)
            self.app.save_playlists()
            self.refresh()
            self.app.set_status(f"Saved playlist {name}")
            win.destroy()

        ttk.Button(win, text="Save", command=save).grid(row=5, column=1, sticky="e",
                                                         padx=8, pady=8)

    # -- packs ------------------------------------------------------------- #
    def _import(self):
        path = filedialog.askopenfilename(title="Import music pack",
                                          filetypes=[("Music pack", "*.zip"), ("All files", "*.*")])
        if not path:
            return
        try:
            name, imported = packs.import_pack(path)
        except Exception as e:
            messagebox.showerror("Import failed", str(e))
            return
        existing = {p["name"] for p in self.app.playlists}
        for pl in imported:
            if pl["name"] in existing:
                pl["name"] = f"{pl['name']} ({name})"
            self.app.playlists.append(pl)
        self.app.save_playlists()
        self.refresh()
        self.app.set_status(f"Imported '{name}' — {len(imported)} playlist(s)")

    def _export(self):
        if not self.app.playlists:
            messagebox.showinfo("Nothing to export", "Create a playlist first.")
            return
        path = filedialog.asksaveasfilename(title="Export music pack",
                                            defaultextension=".zip",
                                            filetypes=[("Music pack", "*.zip")])
        if not path:
            return
        try:
            packs.export_pack(path, self.app.playlists, pack_name="Mothership Pack")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        self.app.set_status(f"Exported {len(self.app.playlists)} playlist(s) → {os.path.basename(path)}")
