"""'Lights' tab: presets, saved custom colours (+ picker), effects, controls."""

import tkinter as tk
from tkinter import ttk, colorchooser, simpledialog

from .colors import PRESETS, COLOR_PRESETS
from .lights import tinytuya


def _hex(rgb):
    return "#%02x%02x%02x" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


class LightsPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.effect_rgb = ("ALERT RED", COLOR_PRESETS["ALERT RED"])
        self._last_cue = None          # ("rgb", rgb) | ("white", kelvin) | None
        self._effect_running = False
        self._bri_after = None

        # -- Instant: built-in presets --------------------------------------
        pf = ttk.LabelFrame(self, text="Instant", padding=6)
        pf.pack(fill="x")
        pf.columnconfigure(0, weight=1)
        for name, spec in PRESETS.items():
            ttk.Button(pf, text=name,
                       command=lambda s=spec: self._cue_preset(s)).pack(fill="x", pady=1)
        ttk.Button(pf, text="BLACKOUT", command=self._cue_blackout).pack(fill="x", pady=(6, 1))

        # -- Saved custom colours ------------------------------------------
        cf = ttk.LabelFrame(self, text="My colours", padding=6)
        cf.pack(fill="x", pady=(8, 0))
        cf.columnconfigure(0, weight=1)
        self.colours_holder = ttk.Frame(cf)
        self.colours_holder.pack(fill="x")
        ttk.Button(cf, text="＋ Pick & save colour",
                   command=self._add_custom).pack(fill="x", pady=(4, 0))

        # -- Effects --------------------------------------------------------
        ef = ttk.LabelFrame(self, text="Effects", padding=6)
        ef.pack(fill="x", pady=(8, 0))
        ef.columnconfigure(1, weight=1)
        ttk.Label(ef, text="Colour").grid(row=0, column=0, sticky="w")
        self.effect_choice = tk.StringVar(value="ALERT RED")
        self.effect_combo = ttk.Combobox(ef, textvariable=self.effect_choice,
                                         state="readonly")
        self.effect_combo.grid(row=0, column=1, sticky="ew", padx=4)
        self.effect_combo.bind("<<ComboboxSelected>>", self._on_effect_choice)
        self.effect_swatch = tk.Label(ef, width=3, bg=_hex(self.effect_rgb[1]),
                                      relief="sunken")
        self.effect_swatch.grid(row=0, column=2, padx=(0, 2))
        row = ttk.Frame(ef)
        row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        for label, kind in (("Flicker", "flicker"), ("Pulse", "pulse"), ("Strobe", "strobe")):
            ttk.Button(row, text=label,
                       command=lambda k=kind: self._cue_effect(k)
                       ).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(ef, text="Stop effect",
                   command=self._stop_effect).grid(row=2, column=0, columnspan=3,
                                                    sticky="ew", pady=(6, 0))

        # -- Controls -------------------------------------------------------
        sf = ttk.LabelFrame(self, text="Controls", padding=6)
        sf.pack(fill="x", pady=(8, 0))
        sf.columnconfigure(1, weight=1)
        ttk.Label(sf, text="Brightness").grid(row=0, column=0, sticky="w")
        self.master_var = tk.DoubleVar(value=100)
        ttk.Scale(sf, from_=5, to=100, variable=self.master_var,
                  command=self._on_brightness).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(sf, text="Effect speed").grid(row=1, column=0, sticky="w")
        self.speed_var = tk.DoubleVar(value=100)
        ttk.Scale(sf, from_=25, to=300, variable=self.speed_var,
                  command=self._on_speed).grid(row=1, column=1, sticky="ew", padx=4)

        self._rebuild_colours()

    # -- colour choices (presets + custom) -------------------------------- #
    def _effect_choices(self):
        """Ordered {name: rgb} of everything usable as an effect colour."""
        choices = dict(COLOR_PRESETS)
        for c in self.app.custom_colors:
            choices[c["name"]] = tuple(c["rgb"])
        return choices

    def _rebuild_colours(self):
        # swatch buttons for saved colours
        for w in self.colours_holder.winfo_children():
            w.destroy()
        if not self.app.custom_colors:
            ttk.Label(self.colours_holder, foreground="#888",
                      text="No saved colours yet.").pack(anchor="w")
        for c in self.app.custom_colors:
            rgb = tuple(c["rgb"])
            row = ttk.Frame(self.colours_holder)
            row.pack(fill="x", pady=1)
            tk.Label(row, width=3, bg=_hex(rgb), relief="sunken").pack(side="left", padx=(0, 4))
            ttk.Button(row, text=c["name"],
                       command=lambda r=rgb: self._cue_preset(("rgb", r))).pack(side="left")
            ttk.Button(row, text="Del", width=4,
                       command=lambda cc=c: self._delete_custom(cc)).pack(side="right")
            ttk.Button(row, text="→ Fx", width=5,
                       command=lambda n=c["name"], r=rgb: self._set_effect_colour(n, r)
                       ).pack(side="right", padx=2)
        # refresh the effect-colour dropdown values
        names = list(self._effect_choices().keys())
        self.effect_combo["values"] = names
        if self.effect_choice.get() not in names:
            self.effect_choice.set(names[0] if names else "")
            self._on_effect_choice()

    def _add_custom(self):
        res = colorchooser.askcolor(title="Pick a colour",
                                    initialcolor=_hex(self.effect_rgb[1]))
        if not res or not res[0]:
            return
        rgb = [int(round(v)) for v in res[0]]
        name = simpledialog.askstring("Name", "Name this colour:",
                                      initialvalue=res[1], parent=self)
        if not name:
            return
        # replace if the name already exists
        self.app.custom_colors = [c for c in self.app.custom_colors if c["name"] != name]
        self.app.custom_colors.append({"name": name, "rgb": rgb})
        self.app.save_colors()
        self._rebuild_colours()
        self.app.set_status(f"Saved colour '{name}'")

    def _delete_custom(self, c):
        self.app.custom_colors = [x for x in self.app.custom_colors if x is not c]
        self.app.save_colors()
        self._rebuild_colours()
        self.app.set_status(f"Removed colour '{c['name']}'")

    # -- checks / levels -------------------------------------------------- #
    def _check(self, devs):
        ok, msg = self.app.lights_ready()
        if not ok:
            self.app.set_status(msg)
            return False
        if not devs:
            self.app.set_status("No active bulbs selected")
            return False
        return True

    def _push_levels(self):
        self.app.ctl.master = self.master_var.get() / 100.0
        self.app.ctl.speed = self.speed_var.get() / 100.0

    # -- instant cues ----------------------------------------------------- #
    def _cue_preset(self, spec):
        mode, value = spec
        devs = self.app.active_devices()
        if not self._check(devs):
            return
        self._push_levels()
        self._effect_running = False
        self._last_cue = (mode, value)
        if mode == "white":
            self.app.run_bg(self.app.ctl.apply_white, devs, value)
        else:
            self.app.run_bg(self.app.ctl.apply_colour, devs, value)

    def _cue_blackout(self):
        devs = self.app.active_devices()
        if self._check(devs):
            self._last_cue = None
            self._effect_running = False
            self.app.run_bg(self.app.ctl.blackout, devs)

    # -- effect colour ---------------------------------------------------- #
    def _set_effect_colour(self, name, rgb):
        self.effect_rgb = (name, tuple(rgb))
        self.effect_choice.set(name)
        self.effect_swatch.config(bg=_hex(rgb))
        self.app.set_status(f"Effect colour: {name}")

    def _on_effect_choice(self, _=None):
        name = self.effect_choice.get()
        rgb = self._effect_choices().get(name)
        if rgb:
            self.effect_rgb = (name, tuple(rgb))
            self.effect_swatch.config(bg=_hex(rgb))

    def _cue_effect(self, kind):
        devs = self.app.active_devices()
        if self._check(devs):
            self._push_levels()
            self._effect_running = True
            self.app.ctl.start_effect(kind, devs, self.effect_rgb[1])
            self.app.set_status(f"effect '{kind}' ({self.effect_rgb[0]}) on {len(devs)} bulb(s)")

    def _stop_effect(self):
        self._effect_running = False
        self.app.run_bg(self.app.ctl.stop_effect)

    # -- live brightness / speed ------------------------------------------ #
    def _on_speed(self, _=None):
        self.app.ctl.speed = self.speed_var.get() / 100.0

    def _on_brightness(self, _=None):
        self.app.ctl.master = self.master_var.get() / 100.0
        if self._bri_after is not None:
            try:
                self.after_cancel(self._bri_after)
            except Exception:
                pass
        self._bri_after = self.after(150, self._reapply_brightness)

    def _reapply_brightness(self):
        self._bri_after = None
        if self._effect_running or self._last_cue is None:
            return
        devs = self.app.active_devices()
        ok, _ = self.app.lights_ready()
        if not (ok and devs):
            return
        mode, value = self._last_cue
        if mode == "white":
            self.app.run_bg(self.app.ctl.apply_white, devs, value)
        else:
            self.app.run_bg(self.app.ctl.apply_colour, devs, value)
