#!/usr/bin/env python3
"""
Mothership Lights — a Linux GUI for driving Elgin / Tuya smart bulbs AND
audio as tabletop RPG lighting/sound cues (built with Mothership in mind).

Lights
  * Scan the local network for Tuya-based bulbs (Elgin Smart Color, etc.)
  * Record bulbs (device id / ip / local key / version) and pick an active rig
  * Instant colour presets + live animated effects (flicker, pulse, strobe)

Audio
  * A looping ambient "bed" (ship hum/drone) with fade in/out
  * Layered one-shot "stingers" (klaxon, clank, alarm)
  * Master volume
  * Link any track to a light cue so one tap fires light + sound together

Local control only for lights — no cloud/internet once keys are recorded.
Requires: python3-tk, tinytuya (lights), pygame (audio).
"""

import os
import sys
import json
import math
import time
import random
import threading
import queue

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import tinytuya
except ImportError:
    tinytuya = None

try:
    import pygame
except ImportError:
    pygame = None


# --------------------------------------------------------------------------- #
#  Config / persistence
# --------------------------------------------------------------------------- #
def _default_config_dir():
    """Per-OS config location: %APPDATA% on Windows, ~/.config elsewhere."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "MothershipLights")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg, "mothership_lights")


CONFIG_DIR = _default_config_dir()
DEVICES_FILE = os.path.join(CONFIG_DIR, "devices.json")
TRACKS_FILE = os.path.join(CONFIG_DIR, "tracks.json")


def _load_list(path):
    try:
        with open(path, "r") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except (OSError, ValueError):
        pass
    return []


def _save_list(path, items):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(items, fh, indent=2)
    os.replace(tmp, path)


def load_devices():
    return _load_list(DEVICES_FILE)


def save_devices(devices):
    _save_list(DEVICES_FILE, devices)


def load_tracks():
    return _load_list(TRACKS_FILE)


def save_tracks(tracks):
    _save_list(TRACKS_FILE, tracks)


# --------------------------------------------------------------------------- #
#  Colour helpers (pure functions — unit-testable without a display)
# --------------------------------------------------------------------------- #
def scale_rgb(rgb, factor):
    """Scale an (r,g,b) tuple by `factor` (0..1), clamped to 1..255."""
    factor = max(0.0, min(1.0, factor))
    return tuple(max(1, min(255, int(round(c * factor)))) for c in rgb)


PRESETS = {
    "Normal (warm)":   (255, 180, 90),
    "Hum blue":        (0, 60, 120),
    "Cold idle cyan":  (0, 130, 140),
    "Emergency amber": (255, 95, 0),
    "ALERT RED":       (255, 0, 0),
}
# cue names that can be used as audio-link triggers
CUE_NAMES = list(PRESETS.keys()) + ["BLACKOUT", "Flicker", "Pulse", "Strobe"]


# --------------------------------------------------------------------------- #
#  Bulb controller
# --------------------------------------------------------------------------- #
class Controller:
    """Owns live BulbDevice connections and the effect thread."""

    def __init__(self, status_cb=None):
        self._bulbs = {}
        self._status_cb = status_cb
        self._effect_thread = None
        self._stop = threading.Event()
        self.master = 1.0
        self.speed = 1.0

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)

    def get_bulb(self, dev):
        if tinytuya is None:
            raise RuntimeError("tinytuya is not installed")
        name = dev["name"]
        b = self._bulbs.get(name)
        if b is None:
            b = tinytuya.BulbDevice(dev["id"], dev["ip"], dev["key"])
            try:
                b.set_version(float(dev.get("version", 3.3)))
            except (TypeError, ValueError):
                b.set_version(3.3)
            b.set_socketPersistent(True)
            b.set_socketTimeout(2)
            self._bulbs[name] = b
        return b

    def drop_bulb(self, name):
        b = self._bulbs.pop(name, None)
        if b is not None:
            try:
                b.close()
            except Exception:
                pass

    def close_all(self):
        for name in list(self._bulbs):
            self.drop_bulb(name)

    def _push_colour(self, dev, rgb):
        b = self.get_bulb(dev)
        r, g, bl = scale_rgb(rgb, self.master)
        b.set_colour(r, g, bl, nowait=True)

    def _push_off(self, dev):
        self.get_bulb(dev).turn_off(nowait=True)

    def _push_on(self, dev):
        self.get_bulb(dev).turn_on(nowait=True)

    def apply_colour(self, devices, rgb):
        self.stop_effect()
        for dev in devices:
            try:
                self._push_on(dev)
                self._push_colour(dev, rgb)
            except Exception as e:
                self._status(f"{dev['name']}: {e}")

    def blackout(self, devices):
        self.stop_effect()
        for dev in devices:
            try:
                self._push_off(dev)
            except Exception as e:
                self._status(f"{dev['name']}: {e}")

    def blink_test(self, dev):
        try:
            for _ in range(3):
                self._push_on(dev)
                self._push_colour(dev, (255, 255, 255))
                time.sleep(0.25)
                self._push_off(dev)
                time.sleep(0.25)
            self._push_on(dev)
            self._status(f"{dev['name']}: blink OK")
        except Exception as e:
            self._status(f"{dev['name']}: {e}")

    def stop_effect(self):
        if self._effect_thread and self._effect_thread.is_alive():
            self._stop.set()
            self._effect_thread.join(timeout=1.5)
        self._stop.clear()
        self._effect_thread = None

    def start_effect(self, kind, devices, rgb):
        self.stop_effect()
        self._stop.clear()
        self._effect_thread = threading.Thread(
            target=self._run_effect, args=(kind, list(devices), tuple(rgb)),
            daemon=True,
        )
        self._effect_thread.start()

    def _write_all(self, devices, rgb):
        for dev in devices:
            try:
                self._push_colour(dev, rgb)
            except Exception:
                pass

    def _run_effect(self, kind, devices, rgb):
        try:
            for dev in devices:
                try:
                    self._push_on(dev)
                except Exception:
                    pass
            if kind == "flicker":
                self._loop_flicker(devices, rgb)
            elif kind == "pulse":
                self._loop_pulse(devices, rgb)
            elif kind == "strobe":
                self._loop_strobe(devices, rgb)
        finally:
            self._status(f"effect '{kind}' stopped")

    def _loop_flicker(self, devices, rgb):
        while not self._stop.is_set():
            roll = random.random()
            if roll < 0.12:
                level, hold = random.uniform(0.02, 0.12), random.uniform(0.04, 0.12)
            elif roll < 0.30:
                level, hold = random.uniform(0.25, 0.5), random.uniform(0.05, 0.15)
            else:
                level, hold = random.uniform(0.6, 1.0), random.uniform(0.08, 0.22)
            self._write_all(devices, scale_rgb(rgb, level))
            self._sleep(hold)

    def _loop_pulse(self, devices, rgb):
        t = 0.0
        while not self._stop.is_set():
            level = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(t))
            self._write_all(devices, scale_rgb(rgb, level))
            t += 0.15 * self.speed
            self._sleep(0.05)

    def _loop_strobe(self, devices, rgb):
        on = True
        while not self._stop.is_set():
            self._write_all(devices, rgb if on else scale_rgb(rgb, 0.02))
            on = not on
            self._sleep(0.12)

    def _sleep(self, base):
        self._stop.wait(base / max(0.25, self.speed))


# --------------------------------------------------------------------------- #
#  Audio engine  (pygame mixer)
# --------------------------------------------------------------------------- #
class AudioEngine:
    """Ambient bed via mixer.music (single looping stream) + layered stingers."""

    def __init__(self, status_cb=None):
        self._status_cb = status_cb
        self.ok = False
        self.master = 1.0          # 0..1
        self._sounds = {}          # path -> pygame.Sound (stinger cache)
        self._bed_path = None
        if pygame is not None:
            try:
                pygame.mixer.init()
                pygame.mixer.set_num_channels(16)
                self.ok = True
            except Exception as e:
                self._status(f"audio init failed: {e}")

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)

    def set_master(self, v):
        self.master = max(0.0, min(1.0, v))
        if self.ok:
            pygame.mixer.music.set_volume(self.master)

    def play_bed(self, path, fade_ms=800):
        if not self.ok:
            self._status("audio not available")
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.master)
            pygame.mixer.music.play(loops=-1, fade_ms=fade_ms)
            self._bed_path = path
            self._status(f"bed: {os.path.basename(path)}")
        except Exception as e:
            self._status(f"bed error: {e}")

    def stop_bed(self, fade_ms=800):
        if not self.ok:
            return
        try:
            if fade_ms:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
            self._bed_path = None
        except Exception as e:
            self._status(f"bed stop error: {e}")

    def play_stinger(self, path):
        if not self.ok:
            self._status("audio not available")
            return
        try:
            snd = self._sounds.get(path)
            if snd is None:
                snd = pygame.mixer.Sound(path)
                self._sounds[path] = snd
            snd.set_volume(self.master)
            snd.play()
            self._status(f"stinger: {os.path.basename(path)}")
        except Exception as e:
            self._status(f"stinger error: {e}")

    def stop_all(self):
        if not self.ok:
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.stop()
            self._bed_path = None
        except Exception:
            pass

    def shutdown(self):
        if self.ok:
            try:
                pygame.mixer.quit()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
#  GUI
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mothership Lights")
        self.geometry("820x600")
        self.minsize(740, 540)

        self.devices = load_devices()
        self.tracks = load_tracks()
        self.active = {d["name"]: tk.BooleanVar(value=True) for d in self.devices}
        self._msg_q = queue.Queue()
        self.ctl = Controller(status_cb=self._enqueue_status)
        self.audio = AudioEngine(status_cb=self._enqueue_status)

        self._build_ui()
        self._refresh_device_list()
        self._refresh_track_list()
        self.after(120, self._drain_status)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        missing = []
        if tinytuya is None:
            missing.append("tinytuya (lights)")
        if pygame is None:
            missing.append("pygame (audio)")
        if missing:
            messagebox.showwarning(
                "Missing libraries",
                "Not installed:\n  " + "\n  ".join(missing) +
                "\n\nInstall with:\n    pip install tinytuya pygame\n\n"
                "The app still runs; the missing feature just won't fire.",
            )

    # -- layout ------------------------------------------------------------ #
    def _build_ui(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._build_devices_panel(root)

        nb = ttk.Notebook(root)
        nb.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        lights_tab = ttk.Frame(nb, padding=6)
        audio_tab = ttk.Frame(nb, padding=6)
        nb.add(lights_tab, text="Lights")
        nb.add(audio_tab, text="Audio")
        self._build_cues_panel(lights_tab)
        self._build_audio_panel(audio_tab)

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, relief="sunken",
                  anchor="w", padding=4).pack(fill="x", side="bottom")

    def _build_devices_panel(self, root):
        frame = ttk.LabelFrame(root, text="Bulbs", padding=6)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        btns = ttk.Frame(frame)
        btns.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(btns, text="Scan network", command=self._scan).pack(side="left")
        ttk.Button(btns, text="Add manually", command=self._add_manual).pack(side="left", padx=4)

        canvas = tk.Canvas(frame, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.dev_holder = ttk.Frame(canvas)
        self.dev_holder.bind("<Configure>",
                             lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.dev_holder, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

    def _build_cues_panel(self, frame):
        frame.columnconfigure(0, weight=1)
        pf = ttk.LabelFrame(frame, text="Instant", padding=6)
        pf.pack(fill="x")
        pf.columnconfigure(0, weight=1)
        for name, rgb in PRESETS.items():
            ttk.Button(pf, text=name,
                       command=lambda n=name, r=rgb: self._cue_colour(n, r)).pack(fill="x", pady=1)
        ttk.Button(pf, text="BLACKOUT", command=self._cue_blackout).pack(fill="x", pady=(6, 1))

        ef = ttk.LabelFrame(frame, text="Effects", padding=6)
        ef.pack(fill="x", pady=(8, 0))
        ef.columnconfigure(0, weight=1)
        self.effect_rgb = ("ALERT RED", PRESETS["ALERT RED"])
        self.effect_colour_lbl = ttk.Label(ef, text="Effect colour: ALERT RED")
        self.effect_colour_lbl.pack(fill="x")
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
        ttk.Button(ef, text="Stop effect", command=self._cue_stop_effect).pack(fill="x", pady=(6, 0))

        sf = ttk.LabelFrame(frame, text="Controls", padding=6)
        sf.pack(fill="x", pady=(8, 0))
        sf.columnconfigure(1, weight=1)
        ttk.Label(sf, text="Brightness").grid(row=0, column=0, sticky="w")
        self.master_var = tk.DoubleVar(value=100)
        ttk.Scale(sf, from_=5, to=100, variable=self.master_var,
                  command=self._on_master).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(sf, text="Effect speed").grid(row=1, column=0, sticky="w")
        self.speed_var = tk.DoubleVar(value=100)
        ttk.Scale(sf, from_=25, to=300, variable=self.speed_var,
                  command=self._on_speed).grid(row=1, column=1, sticky="ew", padx=4)

    def _build_audio_panel(self, frame):
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        top = ttk.Frame(frame)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(top, text="Add bed (loop)",
                   command=lambda: self._add_track("bed")).pack(side="left")
        ttk.Button(top, text="Add stinger",
                   command=lambda: self._add_track("stinger")).pack(side="left", padx=4)
        ttk.Button(top, text="Stop bed", command=lambda: self.audio.stop_bed()).pack(side="right")
        ttk.Button(top, text="Stop all audio", command=self.audio.stop_all).pack(side="right", padx=4)

        canvas = tk.Canvas(frame, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.track_holder = ttk.Frame(canvas)
        self.track_holder.bind("<Configure>",
                               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.track_holder, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

        vf = ttk.Frame(frame)
        vf.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        vf.columnconfigure(1, weight=1)
        ttk.Label(vf, text="Volume").grid(row=0, column=0, sticky="w")
        self.vol_var = tk.DoubleVar(value=80)
        ttk.Scale(vf, from_=0, to=100, variable=self.vol_var,
                  command=self._on_volume).grid(row=0, column=1, sticky="ew", padx=4)
        self.audio.set_master(0.8)

    # -- device rows ------------------------------------------------------- #
    def _refresh_device_list(self):
        for w in self.dev_holder.winfo_children():
            w.destroy()
        if not self.devices:
            ttk.Label(self.dev_holder,
                      text="No bulbs yet.\nUse 'Scan network' or 'Add manually'.",
                      foreground="#888").pack(anchor="w", pady=8, padx=4)
            return
        for dev in self.devices:
            name = dev["name"]
            self.active.setdefault(name, tk.BooleanVar(value=True))
            row = ttk.Frame(self.dev_holder)
            row.pack(fill="x", pady=2)
            ttk.Checkbutton(row, variable=self.active[name]).pack(side="left")
            ttk.Label(row, text=f"{name}  ({dev['ip']})", width=26, anchor="w").pack(side="left")
            ttk.Button(row, text="Test", width=5,
                       command=lambda d=dev: self._run_bg(self.ctl.blink_test, d)).pack(side="right")
            ttk.Button(row, text="Del", width=4,
                       command=lambda d=dev: self._delete_device(d)).pack(side="right", padx=2)

    # -- track rows -------------------------------------------------------- #
    def _refresh_track_list(self):
        for w in self.track_holder.winfo_children():
            w.destroy()
        if not self.tracks:
            ttk.Label(self.track_holder,
                      text="No audio yet.\nAdd a looping bed and some stingers.",
                      foreground="#888").pack(anchor="w", pady=8, padx=4)
            return
        for tr in self.tracks:
            row = ttk.Frame(self.track_holder)
            row.pack(fill="x", pady=2)
            tag = "BED" if tr["kind"] == "bed" else "one-shot"
            ttk.Button(row, text="▶", width=3,
                       command=lambda t=tr: self._play_track(t)).pack(side="left")
            ttk.Label(row, text=f"{tr['name']}  [{tag}]", width=22, anchor="w").pack(side="left")
            link_var = tk.StringVar(value=tr.get("link") or "—")
            tr["_link_var"] = link_var
            combo = ttk.Combobox(row, textvariable=link_var, width=12, state="readonly",
                                 values=["—"] + CUE_NAMES)
            combo.pack(side="left", padx=4)
            combo.bind("<<ComboboxSelected>>", lambda e, t=tr: self._set_link(t))
            ttk.Button(row, text="Del", width=4,
                       command=lambda t=tr: self._delete_track(t)).pack(side="right")

    # -- helpers ----------------------------------------------------------- #
    def _active_devices(self):
        return [d for d in self.devices if self.active.get(d["name"], tk.BooleanVar()).get()]

    def _fire_linked_audio(self, cue_name):
        for tr in self.tracks:
            if (tr.get("link") or "—") != cue_name:
                continue
            if tr["kind"] == "bed":
                self.audio.play_bed(tr["path"])
            else:
                self.audio.play_stinger(tr["path"])

    def _play_track(self, tr):
        if tr["kind"] == "bed":
            self.audio.play_bed(tr["path"])
        else:
            self.audio.play_stinger(tr["path"])

    # -- light cue actions ------------------------------------------------- #
    def _cue_colour(self, name, rgb):
        devs = self._active_devices()
        self._fire_linked_audio(name)          # audio fires even if no bulbs
        if not self._check(devs):
            return
        self._run_bg(self.ctl.apply_colour, devs, rgb)

    def _cue_blackout(self):
        devs = self._active_devices()
        self._fire_linked_audio("BLACKOUT")
        if not self._check(devs):
            return
        self._run_bg(self.ctl.blackout, devs)

    def _set_effect_colour(self, name, rgb):
        self.effect_rgb = (name, rgb)
        self.effect_colour_lbl.config(text=f"Effect colour: {name}")

    def _cue_effect(self, kind):
        devs = self._active_devices()
        self._fire_linked_audio(kind.capitalize())
        if not self._check(devs):
            return
        self.ctl.start_effect(kind, devs, self.effect_rgb[1])
        self._set_status(f"effect '{kind}' running on {len(devs)} bulb(s)")

    def _cue_stop_effect(self):
        self._run_bg(self.ctl.stop_effect)

    def _on_master(self, _=None):
        self.ctl.master = self.master_var.get() / 100.0

    def _on_speed(self, _=None):
        self.ctl.speed = self.speed_var.get() / 100.0

    def _on_volume(self, _=None):
        self.audio.set_master(self.vol_var.get() / 100.0)

    def _check(self, devs):
        if tinytuya is None:
            self._set_status("tinytuya not installed — lights disabled")
            return False
        if not devs:
            self._set_status("No active bulbs selected")
            return False
        return True

    # -- scan / add / delete: bulbs --------------------------------------- #
    def _scan(self):
        if tinytuya is None:
            messagebox.showerror("tinytuya missing", "Install tinytuya first.")
            return
        self._set_status("Scanning network (~6s)…")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            found = tinytuya.deviceScan(False, 6)
        except Exception as e:
            self._enqueue_status(f"scan failed: {e}")
            return
        results = []
        for ip, info in (found or {}).items():
            results.append({
                "ip": info.get("ip", ip),
                "id": info.get("gwId") or info.get("id", ""),
                "version": str(info.get("version", "3.3")),
            })
        self._msg_q.put(("scan_results", results))

    def _open_scan_results(self, results):
        known = {d["id"] for d in self.devices}
        new = [r for r in results if r["id"] not in known]
        if not new:
            self._set_status(f"Scan done — {len(results)} device(s), none new")
            return
        win = tk.Toplevel(self)
        win.title("Scan results")
        win.geometry("580x360")
        ttk.Label(win, padding=8,
                  text="Found these Tuya devices. Name each and paste its LOCAL KEY, "
                       "then Save. (Keys come from the tinytuya wizard — see README.)"
                  ).pack(fill="x")
        holder = ttk.Frame(win, padding=8)
        holder.pack(fill="both", expand=True)
        rows = []
        for r in new:
            fr = ttk.Frame(holder)
            fr.pack(fill="x", pady=2)
            chk = tk.BooleanVar(value=True)
            ttk.Checkbutton(fr, variable=chk).pack(side="left")
            ttk.Label(fr, text=r["ip"], width=15).pack(side="left", padx=2)
            name_e = ttk.Entry(fr, width=15)
            name_e.insert(0, f"Bulb {len(self.devices)+len(rows)+1}")
            name_e.pack(side="left", padx=2)
            key_e = ttk.Entry(fr, width=24)
            key_e.pack(side="left", padx=2)
            rows.append((r, chk, name_e, key_e))

        def do_save():
            added = 0
            for r, chk, name_e, key_e in rows:
                key, name = key_e.get().strip(), name_e.get().strip()
                if not (chk.get() and key and name):
                    continue
                self.devices.append({"name": name, "id": r["id"], "ip": r["ip"],
                                     "key": key, "version": r["version"]})
                self.active[name] = tk.BooleanVar(value=True)
                added += 1
            save_devices(self.devices)
            self._refresh_device_list()
            self._set_status(f"Added {added} bulb(s)")
            win.destroy()

        ttk.Button(win, text="Save selected", command=do_save).pack(pady=8)

    def _add_manual(self):
        win = tk.Toplevel(self)
        win.title("Add bulb")
        fields = {}
        for i, (label, default) in enumerate(
                (("Name", ""), ("Device ID", ""), ("IP address", ""),
                 ("Local key", ""), ("Version", "3.3"))):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            e = ttk.Entry(win, width=30)
            e.insert(0, default)
            e.grid(row=i, column=1, padx=8, pady=4)
            fields[label] = e

        def do_add():
            name = fields["Name"].get().strip()
            dev = {"name": name, "id": fields["Device ID"].get().strip(),
                   "ip": fields["IP address"].get().strip(),
                   "key": fields["Local key"].get().strip(),
                   "version": fields["Version"].get().strip() or "3.3"}
            if not (dev["name"] and dev["id"] and dev["ip"] and dev["key"]):
                messagebox.showerror("Missing", "Name, ID, IP and key are required.")
                return
            self.devices.append(dev)
            self.active[name] = tk.BooleanVar(value=True)
            save_devices(self.devices)
            self._refresh_device_list()
            self._set_status(f"Added {name}")
            win.destroy()

        ttk.Button(win, text="Add", command=do_add).grid(row=5, column=0, columnspan=2, pady=10)

    def _delete_device(self, dev):
        if not messagebox.askyesno("Delete", f"Remove {dev['name']}?"):
            return
        self.ctl.drop_bulb(dev["name"])
        self.devices = [d for d in self.devices if d["name"] != dev["name"]]
        self.active.pop(dev["name"], None)
        save_devices(self.devices)
        self._refresh_device_list()
        self._set_status(f"Removed {dev['name']}")

    # -- add / delete: tracks --------------------------------------------- #
    def _add_track(self, kind):
        path = filedialog.askopenfilename(
            title=f"Choose {'looping bed' if kind == 'bed' else 'stinger'} audio",
            filetypes=[("Audio", "*.ogg *.mp3 *.wav *.flac"), ("All files", "*.*")])
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        self.tracks.append({"name": name, "path": path, "kind": kind, "link": None})
        save_tracks(self.tracks)
        self._refresh_track_list()
        self._set_status(f"Added {kind}: {name}")

    def _delete_track(self, tr):
        self.tracks = [t for t in self.tracks if t is not tr]
        save_tracks(self.tracks)
        self._refresh_track_list()
        self._set_status(f"Removed {tr['name']}")

    def _set_link(self, tr):
        val = tr["_link_var"].get()
        tr["link"] = None if val == "—" else val
        # strip the transient var before persisting
        save_tracks([{k: v for k, v in t.items() if not k.startswith("_")} for t in self.tracks])
        self._set_status(f"{tr['name']} → fires with {val}")

    # -- threading / status ------------------------------------------------ #
    def _run_bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def _enqueue_status(self, msg):
        self._msg_q.put(("status", msg))

    def _drain_status(self):
        try:
            while True:
                kind, payload = self._msg_q.get_nowait()
                if kind == "status":
                    self._set_status(payload)
                elif kind == "scan_results":
                    self._open_scan_results(payload)
        except queue.Empty:
            pass
        self.after(120, self._drain_status)

    def _set_status(self, msg):
        self.status.set(msg)

    def _on_close(self):
        try:
            self.ctl.stop_effect()
            self.ctl.close_all()
            self.audio.stop_all()
            self.audio.shutdown()
        finally:
            self.destroy()


def _selftest():
    """Headless smoke test — no display or audio hardware needed.

    Exercises colour math, config round-trip, the effect loop, and (if pygame
    is present) audio init/playback under the dummy driver. Exits 0 on success.
    Used by CI and to verify the packaged binary actually runs.
    """
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    assert scale_rgb((255, 255, 255), 0.5) == (128, 128, 128)
    assert scale_rgb((255, 0, 0), 0.0) == (1, 1, 1)

    import tempfile
    global CONFIG_DIR, DEVICES_FILE, TRACKS_FILE
    CONFIG_DIR = tempfile.mkdtemp()
    DEVICES_FILE = os.path.join(CONFIG_DIR, "devices.json")
    TRACKS_FILE = os.path.join(CONFIG_DIR, "tracks.json")
    save_devices([{"name": "B", "id": "i", "ip": "1.2.3.4", "key": "k", "version": "3.3"}])
    assert len(load_devices()) == 1
    save_tracks([{"name": "d", "path": "x", "kind": "bed", "link": "Hum blue"}])
    assert load_tracks()[0]["link"] == "Hum blue"

    frames = []
    c = Controller()
    c._write_all = lambda devs, rgb: frames.append(rgb)
    c._push_on = lambda dev: None
    c.start_effect("flicker", [{"name": "x"}], (255, 0, 0))
    time.sleep(0.4)
    c.stop_effect()
    assert len(frames) >= 2 and c._effect_thread is None

    if pygame is not None:
        a = AudioEngine()
        assert a.ok, "audio init failed under dummy driver"
        a.shutdown()

    print("selftest OK  (python %s, tinytuya=%s, pygame=%s)" % (
        sys.version.split()[0],
        getattr(tinytuya, "__version__", None),
        getattr(pygame, "version", None) and pygame.version.ver,
    ))


def main():
    if "--selftest" in sys.argv:
        _selftest()
        return
    App().mainloop()


if __name__ == "__main__":
    main()
