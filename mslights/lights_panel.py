"""'Lights' tab: instant colour presets, animated effects, brightness/speed."""

import tkinter as tk
from tkinter import ttk

from .colors import PRESETS
from .lights import tinytuya


class LightsPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=6)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.effect_rgb = ("ALERT RED", PRESETS["ALERT RED"])

        pf = ttk.LabelFrame(self, text="Instant", padding=6)
        pf.pack(fill="x")
        pf.columnconfigure(0, weight=1)
        for name, rgb in PRESETS.items():
            ttk.Button(pf, text=name,
                       command=lambda r=rgb: self._cue_colour(r)).pack(fill="x", pady=1)
        ttk.Button(pf, text="BLACKOUT", command=self._cue_blackout).pack(fill="x", pady=(6, 1))

        ef = ttk.LabelFrame(self, text="Effects", padding=6)
        ef.pack(fill="x", pady=(8, 0))
        ef.columnconfigure(0, weight=1)
        self.effect_lbl = ttk.Label(ef, text="Effect colour: ALERT RED")
        self.effect_lbl.pack(fill="x")
        pick = ttk.Frame(ef)
        pick.pack(fill="x", pady=2)
        for name, rgb in PRESETS.items():
            ttk.Button(pick, text=name.split()[0],
                       command=lambda n=name, r=rgb: self._set_effect_colour(n, r)
                       ).pack(side="left", expand=True, fill="x", padx=1)
        row = ttk.Frame(ef)
        row.pack(fill="x", pady=(6, 0))
        for label, kind in (("Flicker", "flicker"), ("Pulse", "pulse"), ("Strobe", "strobe")):
            ttk.Button(row, text=label,
                       command=lambda k=kind: self._cue_effect(k)
                       ).pack(side="left", expand=True, fill="x", padx=1)
        ttk.Button(ef, text="Stop effect",
                   command=lambda: self.app.run_bg(self.app.ctl.stop_effect)).pack(fill="x", pady=(6, 0))

        sf = ttk.LabelFrame(self, text="Controls", padding=6)
        sf.pack(fill="x", pady=(8, 0))
        sf.columnconfigure(1, weight=1)
        ttk.Label(sf, text="Brightness").grid(row=0, column=0, sticky="w")
        self.master_var = tk.DoubleVar(value=100)
        ttk.Scale(sf, from_=5, to=100, variable=self.master_var,
                  command=lambda _=None: setattr(self.app.ctl, "master", self.master_var.get() / 100.0)
                  ).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(sf, text="Effect speed").grid(row=1, column=0, sticky="w")
        self.speed_var = tk.DoubleVar(value=100)
        ttk.Scale(sf, from_=25, to=300, variable=self.speed_var,
                  command=lambda _=None: setattr(self.app.ctl, "speed", self.speed_var.get() / 100.0)
                  ).grid(row=1, column=1, sticky="ew", padx=4)

    def _check(self, devs):
        if tinytuya is None:
            self.app.set_status("tinytuya not installed — lights disabled")
            return False
        if not devs:
            self.app.set_status("No active bulbs selected")
            return False
        return True

    def _cue_colour(self, rgb):
        devs = self.app.active_devices()
        if self._check(devs):
            self.app.run_bg(self.app.ctl.apply_colour, devs, rgb)

    def _cue_blackout(self):
        devs = self.app.active_devices()
        if self._check(devs):
            self.app.run_bg(self.app.ctl.blackout, devs)

    def _set_effect_colour(self, name, rgb):
        self.effect_rgb = (name, rgb)
        self.effect_lbl.config(text=f"Effect colour: {name}")

    def _cue_effect(self, kind):
        devs = self.app.active_devices()
        if self._check(devs):
            self.app.ctl.start_effect(kind, devs, self.effect_rgb[1])
            self.app.set_status(f"effect '{kind}' on {len(devs)} bulb(s)")
