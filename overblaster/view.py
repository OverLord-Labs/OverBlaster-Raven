"""Sky-to-display projection. Pure math, no framework."""

import math
from dataclasses import dataclass
from typing import Iterable, Optional, TypeVar

from . import config as C
from .game import angular_distance, az_delta


@dataclass(frozen=True)
class Projection:
    x: float  # display pixels, of the object's center
    y: float
    on_screen: bool  # center is inside the display
    side: Optional[str]  # "left" / "right" when off to the side, else None


def pixels_per_degree(width: float = C.DISPLAY_PX) -> float:
    return width / C.FOV_DEG


def project(
    az: float,
    el: float,
    view_az: float,
    view_el: float,
    width: float = C.DISPLAY_PX,
    height: float = C.DISPLAY_PX,
    margin: float = 0.0,
) -> Projection:
    """Where a sky bearing lands on the display for a head looking at (view_az, view_el).

    `margin` (px) widens the on-screen test so big sprites that are only partly
    visible still count as visible.
    """
    ppd = pixels_per_degree(width)
    dx = az_delta(az, view_az) * math.cos(math.radians(el)) * ppd
    x = width / 2.0 + dx
    y = height / 2.0 - (el - view_el) * ppd
    on = -margin <= x <= width + margin and -margin <= y <= height + margin
    side = None
    if not on:
        side = "right" if x > width + margin else "left" if x < -margin else None
    return Projection(x, y, on, side)


def size_class(radius_deg: float, width: float = C.DISPLAY_PX) -> int:
    """Sprite edge in px for an angular radius: the nearest of config.WORLD_BANDS.

    MediaViewer is fixed-size and reloads its image on every resize, so worlds
    are pre-rendered at a few sizes and the sprite is swapped at the band edges.
    All bands are multiples of 4 as MediaViewer requires.
    """
    px = radius_deg * 2.0 * pixels_per_degree(width)
    return min(C.WORLD_BANDS, key=lambda band: abs(band - px))


@dataclass(frozen=True)
class Pointer:
    """An arrow that points from the middle of the view toward something."""

    x: float  # where to draw it: on a ring around the center of the view
    y: float
    angle: float  # radians; 0 points right, and it grows clockwise on screen (y runs down)
    on_screen: bool  # the thing itself is already in view, so no arrow is needed


def pointer(
    az: float,
    el: float,
    view_az: float,
    view_el: float,
    width: float = C.DISPLAY_PX,
    height: float = C.DISPLAY_PX,
    ring: float = 250.0,
    margin: float = 0.0,
) -> Pointer:
    """Which way to turn your head to face a bearing, as a full 360 degree arrow.

    The direction is the real screen-space direction from the center of the view to the target, so
    it can point up, down, diagonally, or toward the shorter way round when the target is behind
    you. `margin` (px) is how far a big sprite may overhang the edge and still count as in view.
    """
    ppd = pixels_per_degree(width)
    dx = az_delta(az, view_az) * math.cos(math.radians(el)) * ppd
    dy = -(el - view_el) * ppd
    angle = math.atan2(dy, dx)
    cx, cy = width / 2.0, height / 2.0
    on = -margin <= cx + dx <= width + margin and -margin <= cy + dy <= height + margin
    return Pointer(cx + math.cos(angle) * ring, cy + math.sin(angle) * ring, angle, on)


T = TypeVar("T")


def closest(targets: Iterable[T], view_az: float, view_el: float) -> Optional[T]:
    """The target (anything with .az and .el) nearest to where the head is looking, or None."""
    return min(targets, key=lambda t: angular_distance(t.az, t.el, view_az, view_el), default=None)
