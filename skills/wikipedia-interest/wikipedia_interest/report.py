"""One-page PDF report from the structured Stage 4 result."""

import urllib.parse
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .environment import SKILL_ROOT
from .plot import FONT, plot_chart


FONT_NAME = "DejaVuInterest"
PAGE_WIDTH, PAGE_HEIGHT = landscape(A3)
INK = colors.HexColor("#142033")
MUTED = colors.HexColor("#536579")
BLUE = colors.HexColor("#2563EB")
LINE = colors.HexColor("#DCE4EB")

LABELS = {
    "uk": {"title": "ІНТЕРЕС ДО ТЕМИ У WIKIPEDIA", "topic": "Тема", "period": "Період",
           "summary": "Короткий висновок", "recommendation": "Наступна перевірка",
           "reliability": "Надійність і застереження", "assumptions": "Припущення та межі",
           "metrics": "Числа за мовними розділами", "language": "Мова / стаття",
           "mean": "Сер. / міс.", "change": "Рівні періоди", "trend": "Стійкий тренд",
           "agreement": "Оцінка", "confidence": "Надійність", "articles": "URL статей",
           "api": "URL даних Wikimedia", "sources": "Джерела", "views": "переглядів/міс",
           "no_growth": "Надійного сигналу зростання немає. Не обирайте продуктову інвестицію лише за цими переглядами.",
           "uncertain": "Напрям для частини мов невизначений. Уточніть відповідність статей і повноту даних перед пріоритизацією.",
           "growth": "Для наступної перевірки пріоритетні мовні аудиторії: {languages}. Це лише сигнал уваги до статей.",
           "growth_below_criterion": "Сигнал зростання є для: {languages}. Виконання заданих критеріїв не підтверджено; перевірте пороги перед пріоритизацією.",
           "next": "Проведіть інтерв'ю з користувачами цих мов і перевірте пропозицію на посадковій сторінці.",
           "limits": "Одна стаття на мову не охоплює всю тему. Перегляди не доводять попит, географію аудиторії чи готовність платити.",
           "no_topic": "Обрані статті"},
    "en": {"title": "WIKIPEDIA TOPIC INTEREST", "topic": "Topic", "period": "Period",
           "summary": "Short conclusion", "recommendation": "Next validation",
           "reliability": "Reliability and caveats", "assumptions": "Assumptions and limits",
           "metrics": "Figures by language edition", "language": "Language / article",
           "mean": "Avg. / month", "change": "Equal periods", "trend": "Robust trend",
           "agreement": "Assessment", "confidence": "Reliability", "articles": "Article URLs",
           "api": "Wikimedia data URLs", "sources": "Sources", "views": "views/month",
           "no_growth": "No reliable growth signal is present. Do not prioritize product investment from these views alone.",
           "uncertain": "Direction is uncertain for some editions. Check article matches and data completeness before prioritizing.",
           "growth": "Language audiences to investigate next: {languages}. This is only an article-attention signal.",
           "growth_below_criterion": "Growth is present for: {languages}. The specified criteria are not confirmed as met; review the thresholds before prioritizing.",
           "next": "Interview users of these languages and test the offer with a landing page.",
           "limits": "One article per language does not cover the whole topic. Views do not prove demand, geography, or willingness to pay.",
           "no_topic": "Selected articles"},
}

AGREEMENT_UK = {"sustained_growth": "Стійке зростання", "sustained_decline": "Стійкий спад",
                "no_convincing_change": "Без зміни", "uncertain": "Невизначено"}
AGREEMENT_EN = {"sustained_growth": "Sustained growth", "sustained_decline": "Sustained decline",
                "no_convincing_change": "No clear change", "uncertain": "Uncertain"}
REASONS_UK = {
    "the two trend signals disagree or one is unavailable": "сигнали не узгоджуються або одного бракує",
    "fewer than 12 completed months": "менше 12 повних місяців",
    "missing monthly observations": "пропущені місяці",
    "the previous period has zero views": "нульова база попереднього періоду",
    "previous-period mean monthly views are below 100": "менше 100 переглядів на місяць у базі",
    "article equivalence is uncertain": "відповідність статей непевна",
    "one month contributes a large share": "один місяць має великий внесок",
    "a repeated yearly pattern may affect the comparison": "можлива сезонність",
    "fewer than 24 completed months": "менше 24 повних місяців",
    "an incomplete period was excluded": "неповний період виключено",
    "article title history may split views": "історія назви може розділяти перегляди",
    "signals agree across at least 24 complete months without quality warnings":
        "сигнали узгоджені за 24+ повні місяці без застережень",
}


def _register_font():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT)))


def _fit(text: str, width: float, size: float) -> str:
    if pdfmetrics.stringWidth(text, FONT_NAME, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", FONT_NAME, size) > width:
        text = text[:-1]
    return text + "…"


def _wrap(text: str, width: float, size: float) -> list[str]:
    lines = []
    current = ""
    for word in text.split():
        proposal = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(proposal, FONT_NAME, size) <= width:
            current = proposal
            continue
        if current:
            lines.append(current)
            current = ""
        while pdfmetrics.stringWidth(word, FONT_NAME, size) > width:
            cut = len(word)
            while cut > 1 and pdfmetrics.stringWidth(word[:cut], FONT_NAME, size) > width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _draw_wrapped(pdf, text: str, x: float, y: float, width: float,
                  size: float = 9.5, line_height: float = 13, color=INK) -> float:
    pdf.setFont(FONT_NAME, size)
    pdf.setFillColor(color)
    for line in _wrap(text, width, size):
        pdf.drawString(x, y, line)
        y -= line_height
    return y


def _fmt_pct(value) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def _fmt_number(value) -> str:
    return "—" if value is None else f"{value:,.1f}".replace(",", " ")


def _recommendation(metrics: list[dict], labels: dict) -> str:
    reliable_growth = [item for item in metrics
              if item["metrics"]["agreement"] == "sustained_growth"
              and item["reliability"]["level"] != "низька"]
    growth = [item["language"] for item in reliable_growth
              if item["criterion_evaluation"] is None
              or item["criterion_evaluation"]["status"] == "met"]
    if growth:
        return labels["growth"].format(languages=", ".join(growth))
    if reliable_growth:
        return labels["growth_below_criterion"].format(
            languages=", ".join(item["language"] for item in reliable_growth))
    if any(item["metrics"]["agreement"] == "uncertain" for item in metrics):
        return labels["uncertain"]
    return labels["no_growth"]


def _reliability_note(item: dict, language: str) -> str:
    reasons = item["reliability"]["reasons"]
    if language == "uk":
        reasons = [REASONS_UK.get(reason, reason) for reason in reasons]
    return f"{item['language']}: {item['reliability']['level']} — {'; '.join(reasons)}"


def _source_lines(pdf, entries: list[tuple[str, str]], x: float, y: float,
                  width: float, bottom: float = 36) -> float:
    size, line_height = 7.7, 9.5
    for label, url in entries:
        visible = urllib.parse.unquote(url)
        prefix = f"{label}  "
        full = prefix + visible
        lines = _wrap(full, width, size)
        for line in lines:
            if y < bottom:
                raise ValueError("Too many source URLs for a readable one-page report; shorten the period")
            pdf.setFont(FONT_NAME, size)
            pdf.setFillColor(BLUE)
            pdf.drawString(x, y, line)
            pdf.linkURL(url, (x, y - 2, x + min(width, pdfmetrics.stringWidth(line, FONT_NAME, size)), y + 9))
            y -= line_height
        y -= 2
    return y


def report_pdf(analysis: dict, chart_path: Path, output: Path, language: str = "uk") -> dict:
    if analysis.get("status") != "analyzed" or not analysis.get("metrics"):
        raise ValueError("Report input must be an analyzed JSON result")
    if language not in LABELS:
        raise ValueError("Report language must be uk or en")
    if len(analysis["metrics"]) > 6:
        raise ValueError("One-page report supports at most six languages")
    if output.resolve() == chart_path.resolve():
        raise ValueError("Chart and PDF outputs must be different files")
    if output.resolve().is_relative_to(SKILL_ROOT) or chart_path.resolve().is_relative_to(SKILL_ROOT):
        raise ValueError("Chart and PDF outputs must be outside the skill directory")
    labels = LABELS[language]
    _register_font()
    chart_result = plot_chart(analysis, chart_path, language)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)
    pdf.setTitle(labels["title"])
    pdf.setAuthor("Wikipedia Interest Skill")

    margin = 40
    pdf.setFillColor(INK)
    pdf.setFont(FONT_NAME, 18)
    pdf.drawString(margin, 795, labels["title"])
    topic = analysis["request"].get("topic") or ", ".join(item["title"] for item in analysis["metrics"])
    request_line = (f"{labels['topic']}: {topic or labels['no_topic']}   |   "
                    f"{labels['period']}: {analysis['request']['start']} — {analysis['request']['end']}   |   "
                    f"{analysis['request']['access']} / {analysis['request']['agent']} / monthly")
    pdf.setFont(FONT_NAME, 9.5)
    pdf.setFillColor(MUTED)
    pdf.drawString(margin, 770, _fit(request_line, PAGE_WIDTH - 2 * margin, 9.5))
    pdf.setStrokeColor(LINE)
    pdf.line(margin, 760, PAGE_WIDTH - margin, 760)
    pdf.drawImage(str(chart_path), margin, 455, width=720, height=293, mask="auto")

    x, y, panel_width = 790, 742, 360
    pdf.setFont(FONT_NAME, 12)
    pdf.setFillColor(INK)
    pdf.drawString(x, y, labels["summary"])
    y -= 22
    y = _draw_wrapped(pdf, _recommendation(analysis["metrics"], labels), x, y, panel_width,
                      size=9.6, line_height=14)
    y -= 7
    pdf.setFont(FONT_NAME, 11)
    pdf.setFillColor(INK)
    pdf.drawString(x, y, labels["recommendation"])
    y -= 18
    audiences = ", ".join(item["language"] for item in analysis["metrics"])
    next_step = labels["next"].replace("цих мов", f"мов {audiences}").replace("these languages", f"{audiences} language audiences")
    y = _draw_wrapped(pdf, next_step, x, y, panel_width, size=9.2, line_height=13)
    y -= 7
    pdf.setFont(FONT_NAME, 11)
    pdf.setFillColor(INK)
    pdf.drawString(x, y, labels["reliability"])
    y -= 18
    for item in analysis["metrics"]:
        y = _draw_wrapped(pdf, _reliability_note(item, language), x, y, panel_width,
                          size=8.7, line_height=11.5)
    y -= 6
    pdf.setFont(FONT_NAME, 11)
    pdf.setFillColor(INK)
    pdf.drawString(x, y, labels["assumptions"])
    y -= 18
    y = _draw_wrapped(pdf, labels["limits"], x, y, panel_width, size=8.7, line_height=11.5)
    for alternative in analysis.get("alternatives", []):
        base = next(item for item in analysis["metrics"] if item["language"] == alternative["language"])
        changed = alternative["analysis"]
        note = (f"{alternative['language']} {alternative['excluded_date']}: "
                f"{_fmt_pct(base['metrics']['comparison']['percent_change'])} → "
                f"{_fmt_pct(changed['metrics']['comparison']['percent_change'])}; "
                f"{_fmt_pct(base['metrics']['robust_trend']['percent_change_over_span'])} → "
                f"{_fmt_pct(changed['metrics']['robust_trend']['percent_change_over_span'])}. "
                f"{(AGREEMENT_UK if language == 'uk' else AGREEMENT_EN)[base['metrics']['agreement']]} → "
                f"{(AGREEMENT_UK if language == 'uk' else AGREEMENT_EN)[alternative['alternative_agreement']]}. "
                f"{alternative['reason']}")
        y -= 5
        y = _draw_wrapped(pdf, note, x, y, panel_width, size=8.4, line_height=11)
    if y < 460:
        raise ValueError("Report notes do not fit on one readable page")

    pdf.setFont(FONT_NAME, 12)
    pdf.setFillColor(INK)
    pdf.drawString(margin, 433, labels["metrics"])
    comparison = analysis["metrics"][0]["metrics"]["comparison"]
    if comparison["previous_start"] and comparison["current_start"]:
        period_text = (f"{comparison['previous_start']}–{comparison['previous_end']}  →  "
                       f"{comparison['current_start']}–{comparison['current_end']}")
        pdf.setFont(FONT_NAME, 8.4)
        pdf.setFillColor(MUTED)
        pdf.drawString(margin, 416, period_text)
    columns = [(margin, labels["language"], 225), (280, labels["mean"], 118),
               (407, labels["change"], 141), (558, labels["trend"], 142),
               (713, labels["agreement"], 255), (985, labels["confidence"], 165)]
    pdf.setFillColor(colors.HexColor("#EDF3F8"))
    pdf.rect(margin, 382, PAGE_WIDTH - 2 * margin, 24, fill=1, stroke=0)
    pdf.setFillColor(MUTED)
    pdf.setFont(FONT_NAME, 8.4)
    for col_x, header, _ in columns:
        pdf.drawString(col_x + 5, 390, header)
    agreement_names = AGREEMENT_UK if language == "uk" else AGREEMENT_EN
    for index, item in enumerate(analysis["metrics"]):
        row_y = 357 - index * 26
        if index % 2:
            pdf.setFillColor(colors.HexColor("#F7F9FB"))
            pdf.rect(margin, row_y - 7, PAGE_WIDTH - 2 * margin, 24, fill=1, stroke=0)
        values = [f"{item['language']}: {item['title']}",
                  _fmt_number(item["metrics"]["level_and_variability"]["mean_monthly_views"]),
                  _fmt_pct(item["metrics"]["comparison"]["percent_change"]),
                  _fmt_pct(item["metrics"]["robust_trend"]["percent_change_over_span"]),
                  agreement_names[item["metrics"]["agreement"]], item["reliability"]["level"]]
        pdf.setFont(FONT_NAME, 9.1)
        pdf.setFillColor(INK)
        for (col_x, _, col_width), value in zip(columns, values):
            pdf.drawString(col_x + 5, row_y, _fit(value, col_width - 10, 9.1))
    last_row_y = 357 - (len(analysis["metrics"]) - 1) * 26
    source_top = min(253, last_row_y - 24)
    pdf.setStrokeColor(LINE)
    pdf.line(margin, source_top + 16, PAGE_WIDTH - margin, source_top + 16)
    pdf.setFont(FONT_NAME, 10.5)
    pdf.setFillColor(INK)
    pdf.drawString(margin, source_top, labels["sources"])
    article_entries = [(item["language"], item["url"]) for item in analysis["metrics"]]
    api_entries = [(item["language"], url) for item in analysis["metrics"] for url in item["sources"]]
    pdf.setFont(FONT_NAME, 9.2)
    pdf.drawString(margin, source_top - 20, labels["articles"])
    pdf.drawString(605, source_top - 20, labels["api"])
    _source_lines(pdf, article_entries, margin, source_top - 36, 535)
    _source_lines(pdf, api_entries, 605, source_top - 36, 545)
    pdf.setFillColor(MUTED)
    pdf.setFont(FONT_NAME, 7.5)
    footer = "Wikipedia Pageviews · Одна сторінка · Дані та метод: JSON аналізу" if language == "uk" else "Wikipedia Pageviews · One page · Data and method: analysis JSON"
    pdf.drawString(margin, 18, footer)
    pdf.showPage()
    pdf.save()
    document = pdfium.PdfDocument(str(output))
    pages = len(document)
    document.close()
    if pages != 1:
        raise ValueError(f"Expected one PDF page, got {pages}")
    return {"status": "ok", "pdf": str(output.resolve()), "chart": chart_result["chart"],
            "pages": pages, "languages": [item["language"] for item in analysis["metrics"]]}
