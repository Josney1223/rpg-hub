"""Main window: owns shared state (devices, playlists, controllers) and mounts
the Bulbs panel plus the Lights/Audio tabs."""

import queue
import threading

import tkinter as tk
from tkinter import ttk, messagebox

from . import config
from .lights import Controller, tinytuya
from .ha import HAController, HAClient
from .audio import AudioEngine, pygame
from .devices_panel import DevicesPanel
from .lights_panel import LightsPanel
from .audio_panel import AudioPanel


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mothership Lights")
        self.geometry("860x620")
        self.minsize(760, 560)

        self.devices = config.load_json(config.DEVICES_FILE, [])
        self.playlists = config.load_json(config.PLAYLISTS_FILE, [])
        self.custom_colors = config.load_json(config.COLORS_FILE, [])
        self.settings = config.load_settings()
        self.active = {d["name"]: tk.BooleanVar(value=True) for d in self.devices}

        self._q = queue.Queue()
        self._ha_client = None
        self.ctl = None
        self._build_controller()
        self.audio = AudioEngine(status_cb=lambda m: self.enqueue(("status", m)))

        self._build()
        self.after(120, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        missing = []
        if self.backend == "tuya" and tinytuya is None:
            missing.append("tinytuya (lights)")
        if pygame is None:
            missing.append("pygame-ce (audio)")
        if missing:
            messagebox.showwarning(
                "Missing libraries",
                "Not installed:\n  " + "\n  ".join(missing) +
                "\n\nInstall with:\n    pip install tinytuya pygame-ce\n\n"
                "The app still runs; the missing feature just won't fire.")

    def _build(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self.devices_panel = DevicesPanel(root, self)
        self.devices_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        nb = ttk.Notebook(root)
        nb.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.lights_panel = LightsPanel(nb, self)
        self.audio_panel = AudioPanel(nb, self)
        nb.add(self.lights_panel, text="Lights")
        nb.add(self.audio_panel, text="Audio")

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  anchor="w", padding=4).pack(fill="x", side="bottom")

    # -- backend / controller --------------------------------------------- #
    @property
    def backend(self):
        return self.settings.get("backend", "tuya")

    def _build_controller(self):
        if self.ctl is not None:
            try:
                self.ctl.close_all()
            except Exception:
                pass
        cb = lambda m: self.enqueue(("status", m))
        if self.backend == "ha":
            self._ha_client = HAClient(self.settings.get("ha_url", ""),
                                       self.settings.get("ha_token", ""))
            self.ctl = HAController(lambda: self._ha_client, status_cb=cb)
        else:
            self._ha_client = None
            self.ctl = Controller(status_cb=cb)

    def lights_ready(self):
        if self.backend == "ha":
            if not (self.settings.get("ha_url") and self.settings.get("ha_token")):
                return False, "Set Home Assistant URL and token in Settings"
            return True, ""
        if tinytuya is None:
            return False, "tinytuya not installed — lights disabled"
        return True, ""

    def open_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("460x260")
        win.columnconfigure(1, weight=1)

        ttk.Label(win, text="Light backend").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        backend_var = tk.StringVar(value=self.backend)
        bf = ttk.Frame(win)
        bf.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Radiobutton(bf, text="Home Assistant", variable=backend_var, value="ha").pack(side="left")
        ttk.Radiobutton(bf, text="Tuya (direct)", variable=backend_var, value="tuya").pack(side="left", padx=8)

        ttk.Label(win, text="HA URL").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        url_e = ttk.Entry(win)
        url_e.insert(0, self.settings.get("ha_url", ""))
        url_e.grid(row=1, column=1, sticky="ew", padx=8)

        ttk.Label(win, text="HA token").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        tok_e = ttk.Entry(win, show="•")
        tok_e.insert(0, self.settings.get("ha_token", ""))
        tok_e.grid(row=2, column=1, sticky="ew", padx=8)

        ttk.Label(win, foreground="#888", wraplength=430,
                  text="Long-Lived Access Token: HA → your profile → Security → "
                       "Long-lived access tokens → Create.").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 6))

        def test():
            try:
                c = HAClient(url_e.get().strip(), tok_e.get().strip())
                r = c.ping()
                self.set_status(f"HA OK: {r.get('message', 'connected')}")
            except Exception as e:
                self.set_status(f"HA test failed: {e}")

        def save():
            self.settings["backend"] = backend_var.get()
            self.settings["ha_url"] = url_e.get().strip()
            self.settings["ha_token"] = tok_e.get().strip()
            config.save_settings(self.settings)
            self._build_controller()
            self.devices_panel.rebuild()
            self.set_status(f"Backend: {self.backend}")
            win.destroy()

        bar = ttk.Frame(win)
        bar.grid(row=4, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(bar, text="Test HA", command=test).pack(side="left", padx=4)
        ttk.Button(bar, text="Save", command=save).pack(side="left")

    # -- shared helpers used by panels ------------------------------------ #
    def active_devices(self):
        return [d for d in self.devices if self.active.get(d["name"], tk.BooleanVar()).get()]

    def save_devices(self):
        config.save_json(config.DEVICES_FILE, self.devices)

    def save_playlists(self):
        clean = [{k: v for k, v in p.items() if not k.startswith("_")}
                 for p in self.playlists]
        config.save_json(config.PLAYLISTS_FILE, clean)

    def save_colors(self):
        config.save_json(config.COLORS_FILE, self.custom_colors)

    def run_bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def set_status(self, msg):
        self.status.set(msg)

    def enqueue(self, item):
        self._q.put(item)

    def _drain(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "status":
                    self.set_status(payload)
                elif kind == "scan_results":
                    self.devices_panel.open_scan_results(payload)
                elif kind == "ha_lights":
                    self.devices_panel.open_ha_lights(payload)
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def _on_close(self):
        try:
            self.ctl.stop_effect()
            self.ctl.close_all()
            self.audio.shutdown()
        finally:
            self.destroy()


def main():
    App().mainloop()
