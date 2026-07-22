"""Home Assistant backend.

HAClient   — thin REST wrapper (stdlib urllib, no extra deps) around HA's API.
HAController — same interface as lights.Controller, but drives HA `light.*`
               entities via service calls instead of talking to bulbs directly.

Devices in this backend are dicts of the form {"name": str, "entity_id": str}.
Auth uses a Long-Lived Access Token (HA profile -> Security -> create token).
"""

import json
import math
import time
import random
import threading
import urllib.request
import urllib.error

from .colors import scale_rgb


class HAClient:
    def __init__(self, base_url, token):
        self.base = (base_url or "").rstrip("/")
        self.token = token or ""

    def _req(self, method, path, payload=None, timeout=6):
        url = self.base + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
            return json.loads(body) if body else None

    def ping(self):
        """Return HA's API banner, or raise. Used by the Test button."""
        return self._req("GET", "/api/")

    def list_lights(self):
        states = self._req("GET", "/api/states")
        out = []
        for s in states or []:
            eid = s.get("entity_id", "")
            if eid.startswith("light."):
                out.append({"entity_id": eid,
                            "name": s.get("attributes", {}).get("friendly_name", eid)})
        return out

    def call(self, domain, service, payload):
        return self._req("POST", f"/api/services/{domain}/{service}", payload)


class HAController:
    """Light controller that routes to Home Assistant service calls."""

    def __init__(self, get_client, status_cb=None):
        self._get_client = get_client        # callable -> HAClient (or None)
        self._status_cb = status_cb
        self._effect_thread = None
        self._stop = threading.Event()
        self.master = 1.0
        self.speed = 1.0
        self._no_transition = False          # set if the bulb rejects `transition`

    # -- interface parity with lights.Controller --------------------------- #
    def drop_bulb(self, name):
        pass

    def close_all(self):
        self.stop_effect()

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)

    def _client(self):
        c = self._get_client() if self._get_client else None
        if c is None or not c.base or not c.token:
            self._status("Home Assistant not configured (Settings)")
            return None
        return c

    @staticmethod
    def _entities(devices):
        return [d["entity_id"] for d in devices if d.get("entity_id")]

    def _bri(self, level):
        return max(1, min(255, int(round(level * self.master * 255))))

    def _send_on(self, c, payload, transition=None):
        """turn_on with optional transition; if the bulb rejects transition,
        retry once without it and stop using it thereafter."""
        p = dict(payload)
        if transition is not None and not self._no_transition:
            p["transition"] = transition
        try:
            c.call("light", "turn_on", p)
        except Exception as e:
            if "transition" in p:
                self._no_transition = True
                p.pop("transition", None)
                c.call("light", "turn_on", p)   # may raise; caller handles
            else:
                raise

    def _turn_on(self, c, entities, rgb, level=1.0, transition=None):
        self._send_on(c, {
            "entity_id": entities,
            "rgb_color": [int(rgb[0]), int(rgb[1]), int(rgb[2])],
            "brightness": self._bri(level),
        }, transition)

    # -- one-shot cues ----------------------------------------------------- #
    def apply_colour(self, devices, rgb):
        self.stop_effect()
        c = self._client()
        if not c:
            return
        ents = self._entities(devices)
        if not ents:
            return
        try:
            self._turn_on(c, ents, rgb, 1.0)
        except Exception as e:
            self._status(f"HA: {e}")

    def apply_white(self, devices, kelvin):
        """Use the bulb's white channel (brightest) at colour temperature K."""
        self.stop_effect()
        c = self._client()
        if not c:
            return
        ents = self._entities(devices)
        if not ents:
            return
        try:
            self._send_on(c, {
                "entity_id": ents,
                "color_temp_kelvin": int(kelvin),
                "brightness": self._bri(1.0),
            })
        except Exception as e:
            self._status(f"HA: {e}")

    def blackout(self, devices):
        self.stop_effect()
        c = self._client()
        if not c:
            return
        try:
            c.call("light", "turn_off", {"entity_id": self._entities(devices)})
        except Exception as e:
            self._status(f"HA: {e}")

    def blink_test(self, dev):
        c = self._client()
        if not c or not dev.get("entity_id"):
            return
        eid = dev["entity_id"]
        try:
            for _ in range(3):
                self._turn_on(c, [eid], (255, 255, 255), 1.0)
                time.sleep(0.25)
                c.call("light", "turn_off", {"entity_id": eid})
                time.sleep(0.25)
            self._turn_on(c, [eid], (255, 255, 255), 1.0)
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
        c = self._client()
        if not c:
            return
        ents = self._entities(devices)
        if not ents:
            return
        self._stop.clear()
        self._effect_thread = threading.Thread(
            target=self._run_effect, args=(kind, c, ents, tuple(rgb)), daemon=True)
        self._effect_thread.start()

    def _run_effect(self, kind, c, ents, rgb):
        try:
            {"flicker": self._loop_flicker,
             "pulse": self._loop_pulse,
             "strobe": self._loop_strobe}.get(kind, lambda *a: None)(c, ents, rgb)
        finally:
            self._status(f"effect '{kind}' stopped")

    def _write(self, c, ents, rgb, level, transition=None):
        try:
            self._turn_on(c, ents, rgb, level, transition)
        except Exception:
            pass

    def _loop_flicker(self, c, ents, rgb):
        # abrupt by design; over HA it's paced by request latency
        while not self._stop.is_set():
            roll = random.random()
            if roll < 0.12:
                level, hold = random.uniform(0.02, 0.12), random.uniform(0.08, 0.16)
            elif roll < 0.30:
                level, hold = random.uniform(0.25, 0.5), random.uniform(0.08, 0.18)
            else:
                level, hold = random.uniform(0.6, 1.0), random.uniform(0.12, 0.28)
            self._write(c, ents, rgb, level)
            self._sleep(hold)

    def _loop_pulse(self, c, ents, rgb):
        # Smooth: let the bulb fade via `transition`. If the bulb rejects
        # transition, self._no_transition flips and we fall back to stepping.
        t = 0.0
        while not self._stop.is_set():
            if self._no_transition:
                level = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(t))
                self._write(c, ents, rgb, level)
                t += 0.2 * self.speed
                self._sleep(0.12)
            else:
                period = max(0.6, 1.6 / max(0.25, self.speed))
                self._write(c, ents, rgb, 1.0, transition=period)
                self._sleep(period)
                if self._stop.is_set():
                    break
                self._write(c, ents, rgb, 0.15, transition=period)
                self._sleep(period)

    def _loop_strobe(self, c, ents, rgb):
        on = True
        while not self._stop.is_set():
            self._write(c, ents, rgb, 1.0 if on else 0.02)
            on = not on
            self._sleep(0.13)

    def _sleep(self, base):
        self._stop.wait(base / max(0.25, self.speed))
