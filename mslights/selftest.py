"""Headless smoke test — no display or audio hardware required.

Run via:  mothership-lights --selftest
Exercises colour math, config I/O, the effect loop, audio playlist auto-advance
with concurrent OST+SFX, and music-pack export/import. Exits non-zero on failure.
"""

import os
import sys
import time
import wave
import struct
import math
import tempfile


def _make_wav(path, seconds=0.3, freq=440, rate=8000):
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(int(seconds * rate)):
            w.writeframes(struct.pack("<h", int(3000 * math.sin(i * 2 * math.pi * freq / rate))))


def run():
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    from . import colors, config, lights, audio, packs

    # 1) colour math
    assert colors.scale_rgb((255, 255, 255), 0.5) == (128, 128, 128)
    assert colors.scale_rgb((255, 0, 0), 0.0) == (1, 1, 1)
    print("colors OK")

    # 2) config: point everything at a temp dir and round-trip
    tmp = tempfile.mkdtemp()
    config.CONFIG_DIR = tmp
    config.DEVICES_FILE = os.path.join(tmp, "devices.json")
    config.PLAYLISTS_FILE = os.path.join(tmp, "playlists.json")
    config.PACKS_DIR = os.path.join(tmp, "packs")
    config.save_json(config.DEVICES_FILE, [{"name": "B", "id": "i", "ip": "1.2.3.4",
                                            "key": "k", "version": "3.3"}])
    assert len(config.load_json(config.DEVICES_FILE, [])) == 1
    print("config OK")

    # 3) light effect loop renders frames then stops cleanly
    frames = []
    c = lights.Controller()
    c._write_all = lambda devs, rgb: frames.append(rgb)
    c._push_on = lambda dev: None
    c.start_effect("flicker", [{"name": "x"}], (255, 0, 0))
    time.sleep(0.4)
    c.stop_effect()
    assert len(frames) >= 2 and c._effect_thread is None
    print(f"effects OK ({len(frames)} frames)")

    # 4) audio: OST + SFX playlists play concurrently and auto-advance
    w1 = os.path.join(tmp, "ost1.wav"); _make_wav(w1, 0.3, 330)
    w2 = os.path.join(tmp, "ost2.wav"); _make_wav(w2, 0.3, 392)
    w3 = os.path.join(tmp, "sfx1.wav"); _make_wav(w3, 0.3, 880)
    eng = audio.AudioEngine()
    if eng.ok:
        # count track starts on the OST slot to prove auto-advance deterministically
        plays = {"n": 0}
        _orig = eng.ost._play_current
        def _counting():
            plays["n"] += 1
            return _orig()
        eng.ost._play_current = _counting

        eng.play(audio.new_playlist("Bed", "OST", [w1, w2], loop=True))
        eng.play(audio.new_playlist("Alarm", "SFX", [w3], loop=True))
        time.sleep(0.2)
        import pygame
        assert pygame.mixer.music.get_busy(), "OST should be playing right after start"
        assert eng.sfx.channel.get_busy(), "SFX should be playing concurrently"
        assert eng.now_playing() == {"OST": "Bed", "SFX": "Alarm"}
        # with 0.3s tracks, ~1s should start at least a 2nd track (advance/loop)
        time.sleep(1.0)
        assert plays["n"] >= 2, f"OST should auto-advance; only {plays['n']} track start(s)"
        eng.set_ost_volume(0.4)
        eng.stop_ost()
        time.sleep(0.1)
        eng.stop_all()
        eng.shutdown()
        print(f"audio OK (concurrent OST+SFX, auto-advance x{plays['n']}, volume, stop)")
    else:
        print("audio SKIPPED (mixer unavailable)")

    # 6) HA backend: controller emits correct service calls (fake client)
    from . import ha
    calls = []

    class FakeClient:
        base = "http://x"
        token = "t"
        def call(self, domain, service, payload):
            calls.append((domain, service, payload)); return {}
        def list_lights(self):
            return [{"entity_id": "light.a", "name": "A"}]
        def ping(self):
            return {"message": "API running."}

    hc = ha.HAController(lambda: FakeClient())
    devs = [{"name": "A", "entity_id": "light.a"}]
    hc.apply_colour(devs, (255, 0, 0))
    assert calls[-1][0:2] == ("light", "turn_on")
    assert calls[-1][2]["rgb_color"] == [255, 0, 0]
    hc.blackout(devs)
    assert calls[-1][1] == "turn_off"
    calls.clear()
    hc.start_effect("flicker", devs, (255, 0, 0))
    time.sleep(0.4)
    hc.stop_effect()
    assert len(calls) >= 2 and all(c[1] == "turn_on" for c in calls)
    assert hc._effect_thread is None
    print(f"HA backend OK ({len(calls)} effect calls)")

    # 5+) music pack export -> import round-trip
    pl = audio.new_playlist("Corridors", "OST", [w1, w2], loop=True, shuffle=False)
    zip_path = os.path.join(tmp, "pack.zip")
    packs.export_pack(zip_path, [pl], pack_name="Test Pack")
    assert os.path.getsize(zip_path) > 0
    name, imported = packs.import_pack(zip_path)
    assert name == "Test Pack"
    assert len(imported) == 1 and imported[0]["name"] == "Corridors"
    for t in imported[0]["tracks"]:
        assert os.path.isfile(t), f"extracted track missing: {t}"
    print("packs OK (export/import round-trip)")

    try:
        import tinytuya
        tv = tinytuya.__version__
    except Exception:
        tv = None
    try:
        import pygame
        pv = pygame.version.ver
    except Exception:
        pv = None
    print("selftest OK  (python %s, tinytuya=%s, pygame=%s)"
          % (sys.version.split()[0], tv, pv))


if __name__ == "__main__":
    run()
