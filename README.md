# Mothership Lights

A small Linux GUI (pure Python) for driving Elgin / Tuya smart bulbs **and audio**
as tabletop RPG cues. Scan your network, record bulbs, fire instant colour presets
or live animated effects (flicker, pulse, strobe), run a looping ambient sound bed
with one-shot stingers, and link a light cue to audio so one tap does both.
**Local control only** for lights — once keys are recorded it needs no internet.

---

## 1. Install

You need Python 3, Tk, `tinytuya` (lights) and `pygame` (audio).

```bash
# Debian/Ubuntu/Mint
sudo apt install python3 python3-tk python3-pip

# Fedora
sudo dnf install python3 python3-tkinter python3-pip

# Arch
sudo pacman -S python tk python-pip

# then, on any distro:
pip install --user tinytuya pygame
```

Audio plays common formats (`.ogg`, `.mp3`, `.wav`, `.flac`). `.ogg` is the most
reliable for looping beds; if an `.mp3` won't load, convert it to `.ogg`.

Run it:

```bash
python3 mothership_lights.py
```

---

## 2. Get each bulb's LOCAL KEY (one-time, the fiddly part)

Scanning the network finds a bulb's **IP**, **device ID**, and **protocol
version** automatically — but Tuya encrypts local traffic, so you also need each
bulb's **local key**, which only comes from Tuya's cloud once. Do this once per
bulb; keys only change if you re-pair the bulb or a firmware update rotates them.

1. Pair every bulb in the **Smart Life** app (Tuya). Use Smart Life, not "Elgin
   Smart" — it's the same platform but less crippled and links cleanly to the
   Tuya developer console.
2. Create a free account at **iot.tuya.com** → *Cloud* → create a project
   (data center = the one your Smart Life account uses; for Brazil that's
   usually *Western America*).
3. In the project, *Devices* → *Link App Account* → scan the QR with Smart Life.
   Your bulbs now appear in the console.
4. Grab your project's **Client ID** and **Secret**, then run the tinytuya
   wizard, which pulls every device's id / ip / **key** / version into a local
   `devices.json`:

   ```bash
   python3 -m tinytuya wizard
   ```

5. Copy each bulb's `key` (and `id`, `ip`, `version`) from the wizard output.

More detail: https://github.com/jasonacox/tinytuya#setup-wizard

---

## 3. Record your bulbs in the app

Two ways:

- **Scan network** — finds bulbs and pre-fills IP / ID / version. Type a name
  and paste the **local key** from the wizard, then *Save selected*.
- **Add manually** — enter name / ID / IP / key / version by hand.

Saved bulbs live in `~/.config/mothership_lights/devices.json`. The checkbox next
to each bulb decides whether it's part of the active rig for cues. Use **Test**
to blink one bulb white so you can tell which is which.

---

## 4. Running cues at the table

**Instant** buttons snap all active bulbs to a colour immediately:

| Cue | Use it for |
|-----|-----------|
| Normal (warm) | station running normally |
| Hum blue | ambient dread / idle exploration |
| Cold idle cyan | dim, sterile corridor light |
| Emergency amber | systems degrading |
| ALERT RED | the moment it all goes wrong |
| BLACKOUT | hard cut to darkness |

**Effects** run continuously on a background thread. Pick an effect colour, then:

- **Flicker** — a failing panel: mostly lit with irregular dips and brief
  brown-outs. Great on *hum blue* for a dying ship, or *red* for a struggling
  alert.
- **Pulse** — slow breathing in/out. Ominous on red.
- **Strobe** — hard on/off. See the note on speed below.

**Controls:** *Brightness* scales everything; *Effect speed* tunes how fast
flicker/pulse/strobe move. **Stop effect** ends the animation and holds the last
frame; any Instant button also stops a running effect first.

---

## 5. Audio (the "Audio" tab)

- **Add bed (loop)** — pick a track that loops forever as the ambient bed (ship
  hum, engine drone, station rumble). Only one bed plays at a time; choosing a new
  one fades in over the old.
- **Add stinger** — pick a one-shot sound (klaxon, clank, alarm) that layers over
  the bed each time you fire it.
- **▶** plays a track; **Stop bed** fades the bed out; **Stop all audio** cuts
  everything; **Volume** is the master level.

### Linking audio to a light cue
Each track has a **"fires with"** dropdown. Set it to a light cue (e.g. the klaxon
→ *ALERT RED*, the drone → *Hum blue*) and that sound triggers automatically
whenever you press that light button — so one tap snaps the lights and plays the
sound together. Leave it on **—** for manual-only.

Suggested rig for Mothership: a low engine-drone **bed** linked to *Hum blue*, a
**klaxon** stinger linked to *ALERT RED*, and a metallic **clank** stinger left on
manual for when something moves in the vents.

---

## Phone control at the table
This is a desktop GUI, but because bulb control is just local network calls you can
also drive the same bulbs from a phone via Home Assistant's Tuya Local integration,
or a tiny local web page — ask and I'll build you that version.

---

## Building standalone apps (no Python needed to run)

The repo ships a PyInstaller spec that produces a single-file executable per OS.

**Linux** (needs system Tk — `sudo apt install python3-tk`):
```bash
./build_linux.sh          # -> dist/mothership-lights
```
A prebuilt Linux binary is also included in this package as `mothership-lights`.

**Windows** (run on a Windows machine with Python 3 from python.org, which
already bundles Tkinter):
```bat
build_windows.bat         :: -> dist\mothership-lights.exe
```

**Both, automatically, via GitHub Actions** — no Windows machine required.
Push this repo to GitHub; `.github/workflows/build.yml` builds Linux **and**
Windows binaries on every push and attaches them to any Release. Download them
from the run's *Artifacts* section.

> Note: PyInstaller can't cross-compile. A Windows `.exe` must be built on
> Windows (locally or via the GitHub Actions runner above); a Linux binary must
> be built on Linux. The CI workflow does both for you.

Verify any build with `mothership-lights --selftest` (or `.exe --selftest`),
which runs a headless check and prints the bundled library versions.

### Windows first-run notes
- The first network **Scan** may trigger a Windows Firewall prompt (UDP
  broadcast) — allow it on private networks.
- SmartScreen may warn about an unsigned binary; choose *More info -> Run anyway*,
  or build it yourself with the script above.

### If pip tries to compile pygame from source
Symptom: `WARNING, No "Setup" File Exists, Running "buildconfig/config.py"` and/or
`ERROR: Failed to build 'pygame'`. This means pip found no prebuilt wheel for your
Python version and is compiling from source (which fails on Python 3.13/3.14).
Fix — use the community edition, a drop-in replacement (`import pygame` still works):
```
python -m pip install --upgrade pip
python -m pip uninstall -y pygame
python -m pip install pygame-ce
```
This project already installs `pygame-ce` in its build scripts and requirements.

---

## Notes & limits

- **2.4 GHz Wi-Fi only** — these bulbs won't join a 5 GHz network.
- **Speed:** cheap Tuya bulbs take a fraction of a second per change, so flicker
  and pulse look atmospheric but strobe is chunky, not a crisp rave strobe.
- **Keys rotate** occasionally on firmware updates; if a bulb stops responding,
  re-run the wizard and update its key (Del it, Add it again).
- The app keeps one persistent socket per bulb for snappier cues; closing the
  window releases them.
