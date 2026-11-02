"""Draws the tray icon: a colored disc with a white "shrink" arrow; the color shows the state."""

from __future__ import annotations

from PIL import Image, ImageDraw

from . import status

ICON_SIZE = 64
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)
STATE_COLORS = {
    status.IDLE: (34, 160, 90, 255),
    status.COMPRESSING: (230, 140, 20, 255),
    status.PAUSED: (130, 130, 130, 255),
    status.ERROR: (210, 50, 50, 255),
}


def draw_tray_icon(state: str) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), TRANSPARENT)
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, ICON_SIZE - 2, ICON_SIZE - 2), fill=STATE_COLORS.get(state, STATE_COLORS[status.IDLE]))
    draw.rectangle((26, 12, 38, 30), fill=WHITE)              # arrow shaft
    draw.polygon([(16, 30), (48, 30), (32, 46)], fill=WHITE)  # arrow head
    draw.rectangle((16, 49, 48, 54), fill=WHITE)              # floor the arrow presses on
    return image
