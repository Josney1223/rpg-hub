"""Audio engine.

Two independent playback slots run concurrently:
  * OST slot  — the ambient/music layer, via pygame.mixer.music (streamed).
  * SFX slot  — the effects layer, via a reserved mixer Channel.

Each slot plays a *playlist*: a named list of tracks. A slot advances through
its tracks automatically (a small monitor thread polls get_busy), looping the
playlist when ``loop`` is set. Because OST uses the music stream and SFX uses a
reserved channel, one of each can play at the same time without interfering.

A playlist is a plain dict:
    {"name": str, "category": "OST"|"SFX",
     "tracks": [abs_path, ...], "loop": bool, "shuffle": bool}
"""

import time
import random
import threading

try:
    import pygame
except ImportError:
    pygame = None


def new_playlist(name, category="OST", tracks=None, loop=True, shuffle=False):
    return {"name": name, "category": category.upper(),
            "tracks": list(tracks or []), "loop": bool(loop), "shuffle": bool(shuffle)}


class _Slot:
    """Plays one playlist, on either the music stream or a channel."""

    def __init__(self, kind):
        self.kind = kind            # "music" or "channel"
        self.channel = None         # set for "channel" slots
        self.volume = 0.8
        self.name = None            # currently-playing playlist name
        self._tracks = []
        self._idx = 0
        self._loop = True
        self._stop = threading.Event()
        self._thread = None
        self._sounds = {}           # path -> Sound cache (channel slots)

    def start(self, playlist):
        self.stop(fade_ms=200)
        tracks = list(playlist.get("tracks") or [])
        if not tracks:
            return
        if playlist.get("shuffle"):
            random.shuffle(tracks)
        self._tracks = tracks
        self._idx = 0
        self._loop = playlist.get("loop", True)
        self.name = playlist.get("name")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _play_current(self):
        path = self._tracks[self._idx]
        if self.kind == "music":
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
        else:
            snd = self._sounds.get(path)
            if snd is None:
                snd = pygame.mixer.Sound(path)
                self._sounds[path] = snd
            snd.set_volume(self.volume)
            self.channel.play(snd)

    def _busy(self):
        if self.kind == "music":
            return pygame.mixer.music.get_busy()
        return bool(self.channel and self.channel.get_busy())

    def _run(self):
        try:
            self._play_current()
        except Exception:
            self.name = None
            return
        self._stop.wait(0.4)                 # let playback spin up
        while not self._stop.is_set():
            if not self._busy():
                self._idx += 1
                if self._idx >= len(self._tracks):
                    if self._loop:
                        self._idx = 0
                    else:
                        break
                try:
                    self._play_current()
                except Exception:
                    break
                self._stop.wait(0.3)
            self._stop.wait(0.15)

    def stop(self, fade_ms=600):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.name = None
        if pygame is None:
            return
        try:
            if self.kind == "music":
                pygame.mixer.music.fadeout(fade_ms) if fade_ms else pygame.mixer.music.stop()
            elif self.channel:
                self.channel.fadeout(fade_ms) if fade_ms else self.channel.stop()
        except Exception:
            pass

    def set_volume(self, v):
        self.volume = max(0.0, min(1.0, v))
        if pygame is None:
            return
        try:
            if self.kind == "music":
                pygame.mixer.music.set_volume(self.volume)
            elif self.channel:
                self.channel.set_volume(self.volume)
        except Exception:
            pass


class AudioEngine:
    def __init__(self, status_cb=None):
        self._status_cb = status_cb
        self.ok = False
        self.ost = _Slot("music")
        self.sfx = _Slot("channel")
        if pygame is not None:
            try:
                pygame.mixer.init()
                pygame.mixer.set_num_channels(16)
                pygame.mixer.set_reserved(1)          # keep channel 0 for SFX
                self.sfx.channel = pygame.mixer.Channel(0)
                self.ok = True
            except Exception as e:
                self._status(f"audio init failed: {e}")

    def _status(self, msg):
        if self._status_cb:
            self._status_cb(msg)

    def play(self, playlist):
        if not self.ok:
            self._status("audio not available")
            return
        cat = (playlist.get("category") or "OST").upper()
        slot = self.ost if cat == "OST" else self.sfx
        slot.start(playlist)
        self._status(f"{cat}: {playlist.get('name')}")

    def stop_ost(self):
        self.ost.stop()

    def stop_sfx(self):
        self.sfx.stop()

    def stop_all(self):
        self.ost.stop(0)
        self.sfx.stop(0)

    def set_ost_volume(self, v):
        self.ost.set_volume(v)

    def set_sfx_volume(self, v):
        self.sfx.set_volume(v)

    def now_playing(self):
        return {"OST": self.ost.name, "SFX": self.sfx.name}

    def shutdown(self):
        self.stop_all()
        if self.ok:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
