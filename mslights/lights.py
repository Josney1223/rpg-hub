"""Tuya/Elgin bulb control: connections, instant cues, animated effects."""

import time
import math
import random
import threading

from .colors import scale_rgb

try:
    import tinytuya
except ImportError:
    tinytuya = None


class Controller:
    """Owns live BulbDevice connections and the single effect thread."""

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

    # -- connections ------------------------------------------------------- #
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

    # -- primitive writes -------------------------------------------------- #
    def _push_colour(self, dev, rgb):
        r, g, bl = scale_rgb(rgb, self.master)
        self.get_bulb(dev).set_colour(r, g, bl, nowait=True)

    def _push_off(self, dev):
        self.get_bulb(dev).turn_off(nowait=True)

    def _push_on(self, dev):
        self.get_bulb(dev).turn_on(nowait=True)

    # -- one-shot cues ----------------------------------------------------- #
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

    # -- animated effects -------------------------------------------------- #
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
            {"flicker": self._loop_flicker,
             "pulse": self._loop_pulse,
             "strobe": self._loop_strobe}.get(kind, lambda *a: None)(devices, rgb)
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
