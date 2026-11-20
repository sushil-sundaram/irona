"""Dracula colour palette (https://draculatheme.com) shared by the plugin dialogs, HTML and PDF output."""

BACKGROUND = "#282a36"
CURRENT_LINE = "#44475a"
SELECTION = "#44475a"
FOREGROUND = "#f8f8f2"
COMMENT = "#6272a4"
CYAN = "#8be9fd"
GREEN = "#50fa7b"
ORANGE = "#ffb86c"
PINK = "#ff79c6"
PURPLE = "#bd93f9"
RED = "#ff5555"
YELLOW = "#f1fa8c"

# Slightly darker than BACKGROUND, for input fields and lists.
SURFACE = "#21222c"

# Severity -> colour, used everywhere results are listed.
SEVERITY_COLOURS = {
    "error": RED,
    "fail": RED,
    "warning": ORANGE,
    "warn": ORANGE,
    "pass": GREEN,
    "ok": GREEN,
    "info": CYAN,
}


def severity_colour(severity: str) -> str:
    return SEVERITY_COLOURS.get(str(severity).lower(), FOREGROUND)


def hex_to_rgb(colour: str) -> tuple:
    """'#rrggbb' -> (r, g, b) ints 0-255."""
    c = colour.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def hex_to_unit_rgb(colour: str) -> tuple:
    """'#rrggbb' -> (r, g, b) floats 0-1 (PDF colour space)."""
    return tuple(v / 255.0 for v in hex_to_rgb(colour))
