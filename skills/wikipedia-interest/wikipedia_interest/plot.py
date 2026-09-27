"""Render the analyzed monthly series as a shareable PNG chart."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .environment import SKILL_ROOT


FONT = SKILL_ROOT / "assets" / "DejaVuSans.ttf"
COLORS = ["#2563EB", "#D97706", "#059669", "#DC2626", "#7C3AED", "#0891B2"]


def _font(size: int):
    return ImageFont.truetype(str(FONT), size)


def _label(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def _dashed(draw, start, end, fill, width=3, dash=12, gap=8):
    x1, y1 = start
    x2, y2 = end
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if not length:
        return
    position = 0
    while position < length:
        stop = min(position + dash, length)
        draw.line((x1 + (x2 - x1) * position / length,
                   y1 + (y2 - y1) * position / length,
                   x1 + (x2 - x1) * stop / length,
                   y1 + (y2 - y1) * stop / length), fill=fill, width=width)
        position += dash + gap


def plot_chart(analysis: dict, output: Path, language: str = "uk") -> dict:
    if analysis.get("status") != "analyzed" or not analysis.get("series"):
        raise ValueError("Chart input must be an analyzed JSON result")
    if language not in {"uk", "en"}:
        raise ValueError("Chart language must be uk or en")
    if output.resolve().is_relative_to(SKILL_ROOT):
        raise ValueError("Chart output must be outside the skill directory")
    series = analysis["series"]
    if len(series) > len(COLORS):
        raise ValueError("Chart supports at most six language series")
    dates = [point["date"] for point in series[0]["points"]]
    if not dates or any([point["date"] for point in row["points"]] != dates for row in series):
        raise ValueError("All chart series must cover the same months")
    all_views = [point["views"] for row in series for point in row["points"]
                 if point["views"] is not None]
    maximum = max(all_views, default=0)
    ceiling = max(1, int(maximum * 1.12 + 0.5))
    excluded = {item["language"]: item["excluded_date"] for item in analysis.get("alternatives", [])}
    incomplete = sorted({point["date"] for row in series for point in row["points"]
                         if not point["complete"]})

    width, height = 1600, 650
    left, right, top, bottom = 135, 42, 200 if len(series) > 4 else 165, 100
    plot_width, plot_height = width - left - right, height - top - bottom
    canvas = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(canvas)
    title_font, label_font, small_font = _font(35), _font(24), _font(20)
    heading = "Перегляди статей Wikipedia" if language == "uk" else "Wikipedia article views"
    units = "Перегляди / місяць" if language == "uk" else "Views / month"
    draw.text((left, 32), heading, font=title_font, fill="#142033")
    draw.text((left, 82), f"{dates[0]} — {dates[-1]}  ·  {units}", font=label_font, fill="#526276")

    legend_x, legend_y = left, 127
    for index, row in enumerate(series):
        color = COLORS[index]
        label = f"{row['language']}: {row['title']}"
        if len(label) > 28:
            label = label[:27] + "…"
        draw.line((legend_x, legend_y + 12, legend_x + 34, legend_y + 12), fill=color, width=5)
        draw.text((legend_x + 43, legend_y - 3), label, font=small_font, fill="#253347")
        legend_x += max(215, int(draw.textbbox((0, 0), label, font=small_font)[2]) + 72)
        if legend_x > width - 300:
            legend_x, legend_y = left, legend_y + 29

    def x_at(index):
        return left + plot_width * (index / (len(dates) - 1) if len(dates) > 1 else 0.5)

    def y_at(value):
        return top + plot_height * (1 - value / ceiling)

    for index in range(5):
        value = ceiling * index / 4
        y = y_at(value)
        draw.line((left, y, width - right, y), fill="#E3E8EE", width=2)
        draw.text((35, y - 12), _label(round(value)), font=small_font, fill="#59697B")
    draw.line((left, top, left, top + plot_height), fill="#78889A", width=2)
    draw.line((left, top + plot_height, width - right, top + plot_height), fill="#78889A", width=2)
    tick_indices = sorted({round(index * (len(dates) - 1) / min(6, len(dates) - 1))
                           for index in range(min(6, len(dates) - 1) + 1)}) if len(dates) > 1 else [0]
    for index in tick_indices:
        x = x_at(index)
        draw.line((x, top + plot_height, x, top + plot_height + 7), fill="#78889A", width=2)
        draw.text((x - 47, top + plot_height + 18), dates[index][:7], font=small_font, fill="#59697B")

    for row_index, row in enumerate(series):
        color = COLORS[row_index]
        previous = None
        for index, point in enumerate(row["points"]):
            if point["views"] is None:
                previous = None
                continue
            coordinate = (x_at(index), y_at(point["views"]))
            if previous is not None:
                if point["complete"] and previous[1]:
                    draw.line((*previous[0], *coordinate), fill=color, width=4)
                else:
                    _dashed(draw, previous[0], coordinate, color, width=3)
            x, y = coordinate
            if not point["complete"]:
                draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline=color, fill="white", width=4)
            else:
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)
            if excluded.get(row["language"]) == point["date"]:
                draw.line((x - 12, y - 12, x + 12, y + 12), fill="#7C3AED", width=5)
                draw.line((x - 12, y + 12, x + 12, y - 12), fill="#7C3AED", width=5)
            previous = (coordinate, point["complete"])

    note_parts = []
    if incomplete:
        note_parts.append(("Порожнє коло: неповний місяць" if language == "uk"
                           else "Hollow point: incomplete month"))
    if excluded:
        note_parts.append(("Хрест: виключений пік в альтернативі" if language == "uk"
                           else "Cross: peak excluded in alternative"))
    if any(point["missing"] for row in series for point in row["points"]):
        note_parts.append(("Розрив: немає даних" if language == "uk" else "Gap: missing data"))
    if note_parts:
        draw.text((left, height - 36), "  ·  ".join(note_parts), font=small_font, fill="#59697B")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    return {"status": "ok", "chart": str(output.resolve()), "languages": [row["language"] for row in series],
            "marked_incomplete": incomplete,
            "marked_excluded": [{"language": lang, "date": day} for lang, day in excluded.items()]}
