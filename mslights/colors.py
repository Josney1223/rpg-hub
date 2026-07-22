"""Colour math and the Mothership preset palette.

Each preset is tagged with a *mode*:
  ("white", kelvin)  -> use the bulb's white channel (brightest output)
  ("rgb",  (r,g,b))  -> use the colour LEDs (moodier, inherently dimmer)

White presets exist because RGB bulbs are far brighter on their dedicated white
channel than on the colour LEDs, so "full brightness" white must go through
colour-temperature, not rgb_color.
"""


def scale_rgb(rgb, factor):
    """Scale an (r,g,b) tuple by ``factor`` (0..1), clamped to 1..255."""
    factor = max(0.0, min(1.0, factor))
    return tuple(max(1, min(255, int(round(c * factor)))) for c in rgb)


def kelvin_to_pct(kelvin, warm=2700, cool=6500):
    """Map a colour temperature in K to 0..100 (0 = warmest)."""
    k = max(warm, min(cool, int(kelvin)))
    return int(round((k - warm) / float(cool - warm) * 100))


# name -> (mode, value)
PRESETS = {
    "Full white":      ("white", 4000),
    "Normal (warm)":   ("white", 2700),
    "Hum blue":        ("rgb", (0, 60, 120)),
    "Cold idle cyan":  ("rgb", (0, 130, 140)),
    "Emergency amber": ("rgb", (255, 95, 0)),
    "ALERT RED":       ("rgb", (255, 0, 0)),
}

# rgb-only subset, for things that only make sense in colour (effects)
COLOR_PRESETS = {name: spec[1] for name, spec in PRESETS.items() if spec[0] == "rgb"}

CUE_NAMES = list(PRESETS.keys()) + ["BLACKOUT", "Flicker", "Pulse", "Strobe"]
