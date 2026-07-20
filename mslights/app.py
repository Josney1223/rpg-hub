"""Main window: owns shared state (devices, playlists, controllers) and mounts
the Bulbs panel plus the Lights/Audio tabs."""

import queue
import threading

import tkinter as tk
from tkinter import ttk, messagebox

from . import config
from .lights import Controller, tinytuya
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
        self.active = {d["name"]: tk.BooleanVar(value=True) for d in self.devices}

        self._q = queue.Queue()
        self.ctl = Controller(status_cb=lambda m: self.enqueue(("status", m)))
        self.audio = AudioEngine(status_cb=lambda m: self.enqueue(("status", m)))

        self._build()
        self.after(120, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        missing = []
        if tinytuya is None:
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

    # -- shared helpers used by panels ------------------------------------ #
    def active_devices(self):
        return [d for d in self.devices if self.active.get(d["name"], tk.BooleanVar()).get()]

    def save_devices(self):
        config.save_json(config.DEVICES_FILE, self.devices)

    def save_playlists(self):
        clean = [{k: v for k, v in p.items() if not k.startswith("_")}
                 for p in self.playlists]
        config.save_json(config.PLAYLISTS_FILE, clean)

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
