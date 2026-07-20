"""Colour math and the Mothership preset palette."""


def scale_rgb(rgb, factor):
    """Scale an (r,g,b) tuple by ``factor`` (0..1), clamped to 1..255.

    Floor is 1 (not 0) because some Tuya bulbs treat 0,0,0 as 'ignore';
    use a real turn_off() for true darkness.
    """
    factor = max(0.0, min(1.0, factor))
    return tuple(max(1, min(255, int(round(c * factor)))) for c in rgb)


PRESETS = {
    "Normal (warm)":   (255, 180, 90),
    "Hum blue":        (0, 60, 120),
    "Cold idle cyan":  (0, 130, 140),
    "Emergency amber": (255, 95, 0),
    "ALERT RED":       (255, 0, 0),
}

# names usable as triggers elsewhere (scenes/hotkeys in later steps)
CUE_NAMES = list(PRESETS.keys()) + ["BLACKOUT", "Flicker", "Pulse", "Strobe"]
