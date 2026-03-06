from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def resize_keep_aspect(icon: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    orig_w, orig_h = icon.size
    target_w, target_h = target_size
    scale = min(target_w / orig_w, target_h / orig_h)
    new_size = (int(orig_w * scale), int(orig_h * scale))
    return icon.resize(new_size, Image.Resampling.LANCZOS)


def place_icon(
    base: Image.Image,
    icon_path: str | Path,
    position: tuple[int, int],
    size: tuple[int, int] | None = None,
    anchor: str = "tl",
    opacity: int = 255,
    rotate: int = 0,
    shadow: bool = False,
    shadow_offset: int = 6,
    shadow_opacity: int = 80,
) -> Image.Image:
    """Paste an icon onto the base image with optional transforms."""
    icon = Image.open(icon_path)

    if icon.mode != "RGBA":
        icon = icon.convert("RGBA")
    if size:
        icon = resize_keep_aspect(icon, size)
    if rotate != 0:
        icon = icon.rotate(rotate, expand=True, resample=Image.Resampling.BICUBIC)
    if opacity < 255:
        alpha = icon.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity / 255))
        icon.putalpha(alpha)

    x, y = position
    w, h = icon.size

    anchor_offsets = {
        "tl": (0, 0),
        "center": (-w // 2, -h // 2),
        "mm": (-w // 2, -h // 2),
        "tr": (-w, 0),
        "bl": (0, -h),
        "br": (-w, -h),
        "mt": (-w // 2, 0),
        "mb": (-w // 2, -h),
        "lm": (0, -h // 2),
        "rm": (-w, -h // 2),
    }

    ox, oy = anchor_offsets.get(anchor, (0, 0))
    paste_x = x + ox
    paste_y = y + oy

    if shadow:
        ellipse_w = int(w * 1.1)
        ellipse_h = int(h * 0.3)
        cx = paste_x + w // 2
        cy = paste_y + h + shadow_offset

        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.ellipse(
            [
                cx - ellipse_w // 2,
                cy - ellipse_h // 2,
                cx + ellipse_w // 2,
                cy + ellipse_h // 2,
            ],
            fill=(0, 0, 0, shadow_opacity),
        )
        base.paste(
            Image.alpha_composite(base.convert("RGBA"), overlay),
            (0, 0),
        )

    base.paste(icon, (paste_x, paste_y), icon)
    return base


def draw_text_shadow(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: object,
    anchor: str = "mm",
    layers: int = 20,
    spread: float = 0.2,
    max_alpha: int = 120,
) -> None:
    """Draw a soft shadow behind text."""
    x, y = xy
    for i in range(layers, 0, -1):
        offset = i * spread
        alpha = int(max_alpha * (layers - i) / layers)
        draw.text(
            (x - offset, y - offset),
            text,
            fill=(0, 0, 0, alpha),
            font=font,  # type: ignore[arg-type]
            anchor=anchor,
        )


def draw_underlined_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: object,
    fill: tuple[int, int, int],
    anchor: str = "mm",
    underline_offset: int = 8,
    underline_thickness: int = 6,
    underline_color: tuple[int, int, int] | None = None,
    underline_width_percent: float = 80,
    rounded: bool = True,
    use_baseline: bool = False,
) -> None:
    """Draw text with a decorative underline."""
    x, y = xy
    bbox = draw.textbbox(
        (x, y), text, font=font, anchor=anchor  # type: ignore[arg-type]
    )
    left, top, right, bottom = bbox

    text_width = right - left
    underline_width = text_width * (underline_width_percent / 100)
    underline_left = left + (text_width - underline_width) / 2
    underline_right = underline_left + underline_width

    line_y = (y if use_baseline else bottom) + underline_offset
    line_color = underline_color or fill

    if rounded:
        half = underline_thickness / 2
        draw.rounded_rectangle(
            [underline_left, line_y - half, underline_right, line_y + half],
            radius=half,
            fill=line_color,
        )
    else:
        draw.line(
            [(underline_left, line_y), (underline_right, line_y)],
            fill=line_color,
            width=underline_thickness,
        )

    draw.text(
        (x, y), text, font=font, fill=fill, anchor=anchor  # type: ignore[arg-type]
    )
