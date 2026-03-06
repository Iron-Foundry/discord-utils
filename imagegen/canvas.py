from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .drawing import draw_text_shadow, draw_underlined_text, place_icon
from .fonts import FontSet
from .layouts import EntrySlot, LayoutPreset
from .models import CanvasLayout, ColorKey, OTWEntry

BASE_DIR = Path(__file__).parent


class OTWCanvas:
    """Renders an Of The Week image onto the base background."""

    UNDERLINE_STYLE = {
        "underline_offset": 16,
        "underline_thickness": 2,
        "underline_color": (167, 168, 168),
        "underline_width_percent": 102,
        "rounded": False,
        "use_baseline": True,
    }

    def __init__(
        self,
        base_path: str,
        layout: CanvasLayout,
        fonts: FontSet,
        preset: LayoutPreset,
        date_text: str,
    ) -> None:
        self.base = Image.open(BASE_DIR / base_path)
        self.draw = ImageDraw.Draw(self.base)
        self.layout = layout
        self.fonts = fonts
        self.preset = preset
        self.date_text = date_text

    def _resolve_x(self, func: str) -> int:
        lo = self.layout
        positions = {
            "left": lo.constrain_left + lo.pad_x,
            "center": (lo.constrain_left + lo.constrain_right) // 2,
            "right": lo.constrain_right - lo.pad_x,
        }
        return positions[func]

    def _resolve_icon_x(self, func: str) -> int:
        lo = self.layout
        region_width = lo.constrain_right - lo.constrain_left
        positions = {
            "left": lo.constrain_left + region_width // 6,
            "center": (lo.constrain_left + lo.constrain_right) // 2,
            "right": lo.constrain_right - region_width // 6,
        }
        return positions[func]

    def _draw_entry(self, entry: OTWEntry, slot: EntrySlot) -> None:
        lo = self.layout
        text_x = self._resolve_x(slot.text_x_func)
        icon_x = self._resolve_icon_x(slot.icon_x_func)
        color = lo.colors[entry.color_key]
        text_y = lo.otw_text_height + slot.y_offset
        type_y = lo.type_height + slot.y_offset
        icon_y = lo.otw_text_height + lo.pad_y + 40 + slot.y_offset

        draw_text_shadow(
            self.draw,
            (text_x, text_y),
            entry.label,
            self.fonts.big,
            anchor=slot.text_anchor,
        )
        self.draw.text(
            (text_x, text_y),
            entry.label,
            font=self.fonts.big,
            fill=lo.colors[ColorKey.HIGHLIGHT_DATE],
            anchor=slot.text_anchor,
        )

        draw_text_shadow(
            self.draw,
            (text_x, type_y),
            entry.name,
            self.fonts.medium,
            anchor=slot.text_anchor,
            spread=0.1,
        )
        draw_underlined_text(
            self.draw,
            (text_x, type_y),
            entry.name,
            self.fonts.medium,
            fill=color,
            anchor=slot.text_anchor,
            **self.UNDERLINE_STYLE,
        )

        place_icon(
            self.base,
            entry.icon_path,
            (icon_x, icon_y),
            size=(150, 150),
            anchor="center",
            shadow=True,
            shadow_offset=2,
            shadow_opacity=40,
        )

    def _draw_date(self) -> None:
        lo = self.layout
        center_x = self.base.width / 2

        draw_text_shadow(
            self.draw,
            (center_x, lo.date_location),
            self.date_text,
            self.fonts.small,
            spread=0.05,
            max_alpha=120,
        )
        draw_underlined_text(
            self.draw,
            (center_x, lo.date_location),
            self.date_text,
            self.fonts.small,
            fill=(0, 0, 0),
            anchor="mm",
            underline_offset=30,
            underline_thickness=1,
            underline_color=lo.colors[ColorKey.HIGHLIGHT_DATE],
            underline_width_percent=90,
            rounded=True,
            use_baseline=True,
        )

    def render(self, entries: list[OTWEntry]) -> Image.Image:
        """Render entries onto the canvas and return the composed image."""
        if len(entries) != len(self.preset.slots):
            raise ValueError(
                f"{self.preset.layout_type.name} layout expects "
                f"{len(self.preset.slots)} entries, got {len(entries)}"
            )

        self._draw_date()
        for entry, slot in zip(entries, self.preset.slots):
            self._draw_entry(entry, slot)

        return self.base
