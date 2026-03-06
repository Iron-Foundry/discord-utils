from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ColorKey(Enum):
    ROTW = "rotw"
    SOTW = "sotw"
    BOTW = "botw"
    TEXT = "text"
    HIGHLIGHT_DATE = "highlight_date"


RGBTuple = tuple[int, int, int]


@dataclass
class CanvasLayout:
    constrain_left: int
    constrain_right: int
    constrain_top: int
    constrain_bottom: int
    pad_x: int
    pad_y: int
    _colors: dict[ColorKey, RGBTuple] = field(
        default_factory=lambda: {key: (0, 0, 0) for key in ColorKey}
    )
    _date_location: int = field(init=False)
    _otw_text_height: int = field(init=False)
    _type_height: int = field(init=False)

    def __post_init__(self) -> None:
        self._date_location = self.constrain_top + 45
        self._otw_text_height = 460 - 160
        self._type_height = self._otw_text_height - self.pad_y

    @property
    def colors(self) -> dict[ColorKey, RGBTuple]:
        return self._colors

    @colors.setter
    def colors(self, value: tuple[ColorKey, RGBTuple]) -> None:
        key, rgb = value
        if not isinstance(rgb, tuple) or len(rgb) != 3:
            raise TypeError(f"Expected RGB tuple of 3 ints, got {rgb!r}")
        if not all(isinstance(c, int) for c in rgb):
            raise TypeError(f"Expected RGB tuple of 3 ints, got {rgb!r}")
        if key not in self._colors:
            raise KeyError(f"Invalid color key: {key!r}")
        self._colors[key] = rgb

    @property
    def date_location(self) -> int:
        return self._date_location

    @property
    def otw_text_height(self) -> int:
        return self._otw_text_height

    @property
    def type_height(self) -> int:
        return self._type_height


@dataclass
class OTWEntry:
    label: str
    name: str
    icon_path: Path
    color_key: ColorKey
