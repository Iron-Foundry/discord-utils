from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LayoutType(Enum):
    SINGLE = 1
    DOUBLE = 2
    TRIPLE = 3


@dataclass
class EntrySlot:
    """Defines where an entry is placed on the canvas."""

    text_anchor: str
    text_x_func: str
    icon_x_func: str
    y_offset: int = 0


@dataclass
class LayoutPreset:
    layout_type: LayoutType
    slots: list[EntrySlot] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.slots) != self.layout_type.value:
            raise ValueError(
                f"{self.layout_type.name} layout requires "
                f"{self.layout_type.value} slot(s), "
                f"got {len(self.slots)}"
            )


SINGLE_LAYOUT = LayoutPreset(
    layout_type=LayoutType.SINGLE,
    slots=[
        EntrySlot(
            text_anchor="mm",
            text_x_func="center",
            icon_x_func="center",
        ),
    ],
)

DOUBLE_LAYOUT = LayoutPreset(
    layout_type=LayoutType.DOUBLE,
    slots=[
        EntrySlot(
            text_anchor="lm",
            text_x_func="left",
            icon_x_func="left",
        ),
        EntrySlot(
            text_anchor="rm",
            text_x_func="right",
            icon_x_func="right",
        ),
    ],
)

TRIPLE_LAYOUT = LayoutPreset(
    layout_type=LayoutType.TRIPLE,
    slots=[
        EntrySlot(
            text_anchor="lm", text_x_func="left", icon_x_func="left", y_offset=-40
        ),
        EntrySlot(
            text_anchor="mm",
            text_x_func="center",
            icon_x_func="center",
            y_offset=110,
        ),
        EntrySlot(
            text_anchor="rm", text_x_func="right", icon_x_func="right", y_offset=-40
        ),
    ],
)
