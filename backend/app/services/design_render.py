from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from ..config import FONTS
from ..schemas import DesignData, DesignLayer
from .media import get_media, media_file


class DesignRenderError(RuntimeError):
    pass


def _font_path(font: str, bold: bool) -> Path:
    key = f"{font}_bold" if bold else font
    candidate = FONTS.get(key) or FONTS.get(font) or FONTS["sans"]
    if candidate.exists():
        return candidate
    return FONTS["sans"]


def _rgba(value: str) -> tuple[int, int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 6:
        value += "FF"
    if len(value) != 8:
        raise DesignRenderError(f"Invalid color value: {value}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4, 6))  # type: ignore[return-value]


def _apply_filter(image: Image.Image, filter_name: str) -> Image.Image:
    image = image.convert("RGBA")
    if filter_name == "grayscale":
        gray = ImageOps.grayscale(image)
        return Image.merge("RGBA", (gray, gray, gray, image.getchannel("A")))
    if filter_name == "sepia":
        sepia = ImageOps.colorize(ImageOps.grayscale(image), "#2B1D12", "#F4E4C1").convert("RGBA")
        sepia.putalpha(image.getchannel("A"))
        return sepia
    if filter_name == "warm":
        overlay = Image.new("RGBA", image.size, (255, 120, 30, 46))
        return Image.alpha_composite(image, overlay)
    if filter_name == "cool":
        overlay = Image.new("RGBA", image.size, (30, 90, 255, 46))
        return Image.alpha_composite(image, overlay)
    if filter_name == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=3))
    if filter_name == "high_contrast":
        rgb = ImageEnhance.Contrast(image.convert("RGB")).enhance(1.45)
        rgb = ImageEnhance.Color(rgb).enhance(1.15)
        result = rgb.convert("RGBA")
        result.putalpha(image.getchannel("A"))
        return result
    return image


def _image_layer(layer: DesignLayer) -> Image.Image:
    if not layer.media_id:
        raise DesignRenderError("Image layer is missing a media reference")
    media = get_media(layer.media_id)
    if not media:
        raise DesignRenderError(f"Media asset {layer.media_id} no longer exists")
    if media["kind"] != "image":
        raise DesignRenderError("Only image assets can be used on a design image layer")
    try:
        source = Image.open(media_file(media))
        source.load()
    except (OSError, ValueError) as exc:
        raise DesignRenderError(f"Could not read image asset: {exc}") from exc
    source = source.convert("RGBA")
    source = _apply_filter(source, layer.filter)

    width, height = max(1, round(layer.width)), max(1, round(layer.height))
    if layer.fit == "cover":
        layer_image = ImageOps.fit(
            source, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
        )
    else:
        contained = ImageOps.contain(
            source, (width, height), method=Image.Resampling.LANCZOS
        )
        layer_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layer_image.paste(
            contained,
            ((width - contained.width) // 2, (height - contained.height) // 2),
            contained,
        )

    if layer.border_width > 0:
        draw = ImageDraw.Draw(layer_image)
        draw.rectangle(
            [0, 0, width - 1, height - 1],
            outline=_rgba(layer.border_color),
            width=layer.border_width,
        )
    if layer.rotation:
        layer_image = layer_image.rotate(
            layer.rotation, resample=Image.Resampling.BICUBIC, expand=True
        )
    return layer_image


def _shape_layer(layer: DesignLayer) -> Image.Image:
    width, height = max(1, round(layer.width)), max(1, round(layer.height))
    layer_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer_image)
    fill = _rgba(layer.fill)
    outline = _rgba(layer.border_color) if layer.border_width > 0 else None
    if layer.shape == "ellipse":
        draw.ellipse(
            [0, 0, width - 1, height - 1],
            fill=fill,
            outline=outline,
            width=max(1, layer.border_width),
        )
    elif layer.shape == "rounded_rect":
        draw.rounded_rectangle(
            [0, 0, width - 1, height - 1],
            radius=min(layer.radius, width / 2, height / 2),
            fill=fill,
            outline=outline,
            width=max(1, layer.border_width),
        )
    elif layer.shape == "line":
        draw.line(
            [(0, height // 2), (width, height // 2)],
            fill=fill if fill[3] else _rgba(layer.border_color),
            width=max(1, layer.border_width or round(layer.height)),
        )
    else:
        draw.rectangle(
            [0, 0, width - 1, height - 1],
            fill=fill,
            outline=outline,
            width=max(1, layer.border_width),
        )
    if layer.rotation:
        layer_image = layer_image.rotate(
            layer.rotation, resample=Image.Resampling.BICUBIC, expand=True
        )
    return layer_image


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> tuple[list[str], int]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    if not lines:
        lines = [""]
    return lines, max(
        1,
        round(
            sum(
                (font.size if hasattr(font, "size") else layer_size(font))
                for _ in lines
            )
        ),
    )


def layer_size(font: ImageFont.FreeTypeFont) -> int:
    try:
        return font.size
    except AttributeError:
        return 32


def _text_layer(layer: DesignLayer) -> Image.Image:
    width = max(20, round(layer.width))
    font = ImageFont.truetype(str(_font_path(layer.font, layer.bold)), layer.font_size)
    measure = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    measure_draw = ImageDraw.Draw(measure)
    padding = layer.padding
    max_text_width = max(10, width - padding * 2)
    lines, _ = _wrap_text(measure_draw, layer.text or " ", font, max_text_width)
    line_height = max(layer.font_size, round(layer.font_size * layer.line_height))
    text_height = line_height * len(lines)
    block_height = max(1, text_height + padding * 2)
    layer_image = Image.new("RGBA", (width, block_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer_image)

    background = _rgba(layer.background_color)
    if background[3] > 0 and padding > 0:
        draw.rounded_rectangle(
            [0, 0, width - 1, block_height - 1],
            radius=max(0, min(layer.radius, block_height / 2)),
            fill=background,
        )

    color = _rgba(layer.color)
    for index, line in enumerate(lines):
        if not line:
            continue
        line_width = draw.textlength(line, font=font)
        if layer.align == "center":
            x = (width - line_width) / 2
        elif layer.align == "right":
            x = width - padding - line_width
        else:
            x = padding
        y = padding + index * line_height
        if layer.shadow:
            draw.text(
                (x + 3, y + 4),
                line,
                font=font,
                fill=(0, 0, 0, 170),
                anchor="lt",
            )
        if layer.stroke_width > 0:
            draw.text(
                (x, y),
                line,
                font=font,
                fill=color,
                stroke_width=layer.stroke_width,
                stroke_fill=_rgba(layer.stroke_color),
                anchor="lt",
            )
        else:
            draw.text((x, y), line, font=font, fill=color, anchor="lt")
    return layer_image


def render_design(data: DesignData | dict[str, Any], output: Path, scale: float = 1.0) -> tuple[int, int]:
    if not isinstance(data, DesignData):
        data = DesignData.model_validate(data)
    if data.width * data.height * scale * scale > 45_000_000:
        raise DesignRenderError("Requested export is too large")
    canvas = Image.new("RGBA", (data.width, data.height), _rgba(data.background))
    for layer in data.layers:
        if layer.opacity <= 0:
            continue
        if layer.type == "image":
            layer_image = _image_layer(layer)
        elif layer.type == "shape":
            layer_image = _shape_layer(layer)
        else:
            layer_image = _text_layer(layer)
        if layer.opacity < 1:
            alpha = layer_image.getchannel("A").point(
                lambda value: round(value * layer.opacity)
            )
            layer_image.putalpha(alpha)
        canvas.alpha_composite(layer_image, (round(layer.x), round(layer.y)))

    if scale != 1:
        canvas = canvas.resize(
            (max(1, round(data.width * scale)), max(1, round(data.height * scale))),
            Image.Resampling.LANCZOS,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        background = Image.new("RGB", canvas.size, _rgba(data.background)[:3])
        background.paste(canvas, mask=canvas.getchannel("A"))
        background.save(output, "JPEG", quality=92, optimize=True)
    else:
        canvas.save(output, "PNG", optimize=True)
    try:
        with Image.open(output) as check:
            check.verify()
    except OSError as exc:
        raise DesignRenderError("Exported image failed validation") from exc
    return canvas.size


TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "sale-square",
        "name": "Sale Announcement",
        "category": "Promotion",
        "width": 1080,
        "height": 1080,
        "aspect": "1:1",
        "description": "Bold discount announcement for feed placements.",
    },
    {
        "id": "product-square",
        "name": "Product Spotlight",
        "category": "Product",
        "width": 1080,
        "height": 1080,
        "aspect": "1:1",
        "description": "Clean product-led layout with a large image well.",
    },
    {
        "id": "story-promo",
        "name": "Story Promotion",
        "category": "Social",
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "description": "Vertical promo with clear headline and CTA.",
    },
    {
        "id": "reel-cover",
        "name": "Reels Cover",
        "category": "Social",
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "description": "Vertical cover designed for Reels and Shorts.",
    },
    {
        "id": "event-poster",
        "name": "Event Poster",
        "category": "Event",
        "width": 1080,
        "height": 1350,
        "aspect": "4:5",
        "description": "Editorial event layout for feed and print preview.",
    },
    {
        "id": "youtube-thumb",
        "name": "YouTube Thumbnail",
        "category": "Video",
        "width": 1280,
        "height": 720,
        "aspect": "16:9",
        "description": "High-contrast thumbnail with short, readable copy.",
    },
    {
        "id": "landscape-banner",
        "name": "Landscape Banner",
        "category": "Display",
        "width": 1920,
        "height": 1080,
        "aspect": "16:9",
        "description": "Wide brand banner for web and presentation use.",
    },
    {
        "id": "business-ad",
        "name": "Business Advertisement",
        "category": "Brand",
        "width": 1080,
        "height": 1080,
        "aspect": "1:1",
        "description": "Brand-first service advertisement with contact CTA.",
    },
]


def _template_colors(brand: dict | None) -> tuple[str, str, str]:
    colors = (brand or {}).get("colors") or ["#D7FF4F", "#F6F2E8", "#141414"]
    cleaned = [color for color in colors if isinstance(color, str) and color.startswith("#")]
    accent = cleaned[0] if cleaned else "#D7FF4F"
    secondary = cleaned[1] if len(cleaned) > 1 else "#F6F2E8"
    return accent, secondary, "#111214"


def template_data(
    template_id: str,
    brand: dict | None = None,
    campaign: dict | None = None,
) -> dict[str, Any]:
    template = next((item for item in TEMPLATES if item["id"] == template_id), None)
    if not template:
        raise DesignRenderError("Unknown design template")
    width, height = template["width"], template["height"]
    accent, secondary, dark = _template_colors(brand)
    brand_name = (brand or {}).get("name") or "YOUR BRAND"
    product = (campaign or {}).get("product") or "Your product"
    offer = (campaign or {}).get("offer") or "A better way to get more from every day."
    cta = (campaign or {}).get("cta") or "Shop now"
    headline = (campaign or {}).get("name") or "Make your next move"
    if template_id == "sale-square":
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": dark},
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": 24, "fill": accent},
            {"type": "text", "text": "LIMITED OFFER", "x": 72, "y": 78, "width": 760, "height": 60, "font_size": 30, "bold": True, "color": accent, "align": "left"},
            {"type": "text", "text": "SALE", "x": 64, "y": 150, "width": 920, "height": 300, "font_size": 230, "bold": True, "color": secondary, "align": "left"},
            {"type": "text", "text": offer, "x": 72, "y": 500, "width": 760, "height": 220, "font_size": 52, "color": secondary, "align": "left", "line_height": 1.2},
            {"type": "shape", "shape": "rect", "x": 72, "y": 790, "width": 310, "height": 92, "fill": accent, "radius": 6},
            {"type": "text", "text": cta.upper(), "x": 92, "y": 812, "width": 270, "height": 50, "font_size": 32, "bold": True, "color": dark, "align": "center"},
            {"type": "text", "text": brand_name.upper(), "x": 72, "y": 930, "width": 900, "height": 50, "font_size": 26, "bold": True, "color": accent, "align": "left"},
        ]
    elif template_id == "product-square":
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": dark},
            {"type": "shape", "shape": "rounded_rect", "x": 70, "y": 70, "width": 940, "height": 590, "fill": "#1D2020", "radius": 24},
            {"type": "text", "text": "DROP A PRODUCT IMAGE HERE", "x": 250, "y": 340, "width": 580, "height": 80, "font_size": 24, "bold": True, "color": "#777C72", "align": "center"},
            {"type": "text", "text": product, "x": 72, "y": 710, "width": 800, "height": 130, "font_size": 66, "bold": True, "color": secondary, "align": "left"},
            {"type": "text", "text": offer, "x": 72, "y": 850, "width": 780, "height": 120, "font_size": 32, "color": "#AFB3A8", "align": "left"},
            {"type": "text", "text": f"{brand_name.upper()}  •  {cta.upper()}", "x": 72, "y": 990, "width": 900, "height": 40, "font_size": 24, "bold": True, "color": accent, "align": "left"},
        ]
    elif template_id in {"story-promo", "reel-cover"}:
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": dark},
            {"type": "shape", "shape": "ellipse", "x": 430, "y": 240, "width": 600, "height": 600, "fill": "#1B1E1C"},
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": 16, "height": height, "fill": accent},
            {"type": "text", "text": brand_name.upper(), "x": 80, "y": 110, "width": 900, "height": 60, "font_size": 30, "bold": True, "color": accent, "align": "left"},
            {"type": "text", "text": headline, "x": 74, "y": 960, "width": 900, "height": 330, "font_size": 92, "bold": True, "color": secondary, "align": "left", "line_height": 1.05},
            {"type": "text", "text": offer, "x": 80, "y": 1340, "width": 820, "height": 220, "font_size": 40, "color": "#AFB3A8", "align": "left"},
            {"type": "shape", "shape": "rect", "x": 80, "y": 1620, "width": 360, "height": 100, "fill": accent, "radius": 4},
            {"type": "text", "text": cta.upper(), "x": 100, "y": 1646, "width": 320, "height": 40, "font_size": 30, "bold": True, "color": dark, "align": "center"},
            {"type": "text", "text": "SWIPE UP / TAP TO LEARN MORE", "x": 80, "y": 1780, "width": 900, "height": 40, "font_size": 22, "color": "#777C72", "align": "left"},
        ]
    elif template_id == "event-poster":
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": "#0E0F0E"},
            {"type": "text", "text": brand_name.upper(), "x": 80, "y": 70, "width": 900, "height": 40, "font_size": 24, "bold": True, "color": accent, "align": "left"},
            {"type": "text", "text": "EVENT", "x": 76, "y": 140, "width": 920, "height": 160, "font_size": 150, "bold": True, "color": secondary, "align": "left"},
            {"type": "text", "text": headline, "x": 80, "y": 350, "width": 850, "height": 480, "font_size": 88, "bold": True, "color": secondary, "align": "left", "line_height": 1.1},
            {"type": "shape", "shape": "line", "x": 80, "y": 900, "width": 920, "height": 2, "fill": accent, "border_width": 3},
            {"type": "text", "text": offer, "x": 80, "y": 960, "width": 800, "height": 190, "font_size": 36, "color": "#AFB3A8", "align": "left"},
            {"type": "text", "text": f"{cta.upper()}  →", "x": 80, "y": 1220, "width": 600, "height": 60, "font_size": 34, "bold": True, "color": accent, "align": "left"},
        ]
    elif template_id == "youtube-thumb":
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": dark},
            {"type": "shape", "shape": "rect", "x": 740, "y": 0, "width": 540, "height": height, "fill": accent},
            {"type": "text", "text": headline.upper(), "x": 60, "y": 120, "width": 660, "height": 380, "font_size": 78, "bold": True, "color": secondary, "align": "left", "line_height": 1.05},
            {"type": "text", "text": product.upper(), "x": 60, "y": 540, "width": 660, "height": 80, "font_size": 30, "bold": True, "color": accent, "align": "left"},
            {"type": "text", "text": "NEW", "x": 820, "y": 250, "width": 380, "height": 180, "font_size": 130, "bold": True, "color": dark, "align": "center"},
            {"type": "text", "text": brand_name.upper(), "x": 820, "y": 440, "width": 380, "height": 60, "font_size": 26, "bold": True, "color": dark, "align": "center"},
        ]
    elif template_id == "landscape-banner":
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": dark},
            {"type": "shape", "shape": "ellipse", "x": 1240, "y": -160, "width": 900, "height": 900, "fill": "#1B1E1C"},
            {"type": "shape", "shape": "rect", "x": 100, "y": 100, "width": 8, "height": 880, "fill": accent},
            {"type": "text", "text": brand_name.upper(), "x": 160, "y": 150, "width": 800, "height": 50, "font_size": 28, "bold": True, "color": accent, "align": "left"},
            {"type": "text", "text": headline, "x": 156, "y": 300, "width": 1050, "height": 300, "font_size": 100, "bold": True, "color": secondary, "align": "left", "line_height": 1.05},
            {"type": "text", "text": offer, "x": 160, "y": 650, "width": 850, "height": 140, "font_size": 38, "color": "#AFB3A8", "align": "left"},
            {"type": "text", "text": f"{cta.upper()}  →", "x": 160, "y": 850, "width": 500, "height": 50, "font_size": 30, "bold": True, "color": accent, "align": "left"},
        ]
    else:
        layers = [
            {"type": "shape", "shape": "rect", "x": 0, "y": 0, "width": width, "height": height, "fill": dark},
            {"type": "text", "text": brand_name.upper(), "x": 72, "y": 80, "width": 900, "height": 50, "font_size": 28, "bold": True, "color": accent, "align": "left"},
            {"type": "text", "text": headline, "x": 68, "y": 260, "width": 900, "height": 300, "font_size": 90, "bold": True, "color": secondary, "align": "left", "line_height": 1.05},
            {"type": "shape", "shape": "line", "x": 72, "y": 620, "width": 860, "height": 2, "fill": accent, "border_width": 3},
            {"type": "text", "text": offer, "x": 72, "y": 680, "width": 800, "height": 200, "font_size": 38, "color": "#AFB3A8", "align": "left"},
            {"type": "text", "text": f"{cta.upper()}  →", "x": 72, "y": 930, "width": 600, "height": 60, "font_size": 34, "bold": True, "color": accent, "align": "left"},
        ]
    return {
        **DesignData(width=width, height=height, background=dark, layers=[]).model_dump(),
        "layers": [
            {
                "id": f"tpl-{index}",
                "opacity": 1,
                "rotation": 0,
                "line_height": 1.15,
                "padding": 0,
                "shadow": False,
                "stroke_width": 0,
                "stroke_color": "#000000",
                "border_width": 0,
                "border_color": "#00000000",
                "font": "sans",
                **layer,
            }
            for index, layer in enumerate(layers)
        ],
    }
