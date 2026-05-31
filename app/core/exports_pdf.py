"""PDF exporters for chat, brief, and library conversations.

Three exporters, each returning bytes. Arabic handling is the load-bearing
complexity here:

  1. Noto Naskh TTFs are registered with ReportLab on first use. Without
     this, AR text falls back to Helvetica which has no Arabic glyphs and
     renders as tofu boxes.
  2. Every AR string passes through shape_arabic() which: NFC-normalizes
     (PDFs sourced from Word arrive NFD; Noto Naskh only ships glyphs for
     the COMPOSED codepoints), strips zero-width / bidi markers, runs
     arabic_reshaper for contextual joining, then bidi.algorithm to reorder
     for ReportLab's LTR draw pass.
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
from io import BytesIO
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.exports import (
    _COMPLIANCE_CHROME,
    _compliance_check_strings,
    format_dual_date,
    resolve_compliance_lang,
)

logger = logging.getLogger(__name__)

CHAT_ACCENT = colors.HexColor("#00D4AA")
LIB_ACCENT = colors.HexColor("#60A5FA")
GREY_DARK = colors.HexColor("#1F2937")
GREY_MED = colors.HexColor("#6B7280")
GREY_LIGHT = colors.HexColor("#9CA3AF")
HEADER_BG = colors.HexColor("#374151")
RULE = colors.HexColor("#E0E0E0")

FONT_DIR = Path(__file__).parent.parent / "fonts"
AR_FONT_REGULAR = "NotoNaskhArabic-Regular"
AR_FONT_BOLD = "NotoNaskhArabic-Bold"

_ARABIC_RE = re.compile(r"[؀-ۿ]")
_STRIP_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    "☀-➿️]+",
    flags=re.UNICODE,
)

_fonts_registered = False


def register_arabic_fonts() -> bool:
    """Register Noto Naskh with ReportLab. Idempotent — safe to call per-export."""
    global _fonts_registered
    if _fonts_registered:
        return True
    reg = FONT_DIR / "NotoNaskhArabic-Regular.ttf"
    bold = FONT_DIR / "NotoNaskhArabic-Bold.ttf"
    if not reg.is_file() or not bold.is_file():
        logger.warning("Noto Naskh TTFs not found in %s — AR text will tofu.", FONT_DIR)
        return False
    try:
        pdfmetrics.registerFont(TTFont(AR_FONT_REGULAR, str(reg)))
        pdfmetrics.registerFont(TTFont(AR_FONT_BOLD, str(bold)))
        registerFontFamily(
            AR_FONT_REGULAR,
            normal=AR_FONT_REGULAR, bold=AR_FONT_BOLD,
            italic=AR_FONT_REGULAR, boldItalic=AR_FONT_BOLD,
        )
        _fonts_registered = True
        return True
    except Exception as e:
        logger.warning("Font registration failed: %s", e)
        return False


def is_arabic(s: str) -> bool:
    return bool(_ARABIC_RE.search(s or ""))


def strip_emojis(text: str) -> str:
    return _STRIP_EMOJI_RE.sub("", text) if text else text


def shape_arabic(text: str) -> str:
    """NFC → strip zero-width → reshape → bidi reorder. Pure no-op on non-AR."""
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    text = text.translate({
        0x200B: None, 0x200C: None, 0x200D: None,
        0x200E: None, 0x200F: None, 0xFEFF: None,
    }).strip()
    if not text or not _ARABIC_RE.search(text):
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception as e:
        logger.warning("Arabic shaping failed: %s", e)
        return text


def _sanitize_inline(text: str) -> str:
    """Strip markdown markup, HTML-escape, and replace angle brackets that
    would otherwise be interpreted as ReportLab tags."""
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*]\s+", "- ", text, flags=re.MULTILINE)
    return text.replace("<", "(").replace(">", ")")


def _split_chat_blocks(content: str):
    lines = content.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        if line.startswith("|") and i + 1 < n:
            sep = lines[i + 1].strip()
            if sep.startswith("|") and re.match(r"^\|[\s\-:|]+\|?\s*$", sep):
                header = [c.strip() for c in line.strip().strip("|").split("|")]
                rows = [header]
                j = i + 2
                while j < n and lines[j].strip().startswith("|"):
                    rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                    j += 1
                yield "table", rows
                i = j
                continue
        stripped = line.strip()
        if stripped:
            yield "para", stripped
        i += 1


def _build_styles(noto: bool):
    base = getSampleStyleSheet()
    ar_font = AR_FONT_REGULAR if noto else "Helvetica"
    ar_bold = AR_FONT_BOLD if noto else "Helvetica-Bold"
    return {
        "title_chat": ParagraphStyle(
            "title_chat", parent=base["Heading1"], fontSize=24, spaceAfter=12,
            textColor=CHAT_ACCENT,
        ),
        "title_lib": ParagraphStyle(
            "title_lib", parent=base["Heading1"], fontSize=24, spaceAfter=8,
            textColor=LIB_ACCENT,
        ),
        "title_brief": ParagraphStyle(
            "title_brief", parent=base["Heading1"], fontSize=22, spaceAfter=10,
            textColor=CHAT_ACCENT,
        ),
        "body_en": ParagraphStyle(
            "body_en", parent=base["Normal"], fontSize=11, leading=16,
        ),
        "body_ar": ParagraphStyle(
            "body_ar", parent=base["Normal"], fontName=ar_font,
            fontSize=11, leading=18, alignment=TA_RIGHT,
        ),
        "role": ParagraphStyle(
            "role", parent=base["Normal"], fontSize=11, textColor=CHAT_ACCENT,
            fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=4,
        ),
        "role_lib": ParagraphStyle(
            "role_lib", parent=base["Normal"], fontSize=11, textColor=LIB_ACCENT,
            fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontSize=18, textColor=GREY_DARK, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=14, textColor=GREY_DARK,
            spaceBefore=10, spaceAfter=6,
        ),
        "h1_ar": ParagraphStyle(
            "h1_ar", parent=base["Heading1"], fontName=ar_bold, fontSize=18,
            textColor=GREY_DARK, alignment=TA_RIGHT, spaceAfter=8,
        ),
        "h2_ar": ParagraphStyle(
            "h2_ar", parent=base["Heading2"], fontName=ar_bold, fontSize=14,
            textColor=GREY_DARK, alignment=TA_RIGHT, spaceBefore=10, spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["Normal"], fontSize=10, textColor=GREY_MED,
        ),
        "sources": ParagraphStyle(
            "sources", parent=base["Normal"], fontSize=9, textColor=GREY_MED,
        ),
        "sources_ar": ParagraphStyle(
            "sources_ar", parent=base["Normal"], fontName=ar_font, fontSize=9,
            textColor=GREY_MED, alignment=TA_RIGHT,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"], fontSize=8, textColor=GREY_LIGHT,
            alignment=TA_CENTER,
        ),
        "ar_font": ar_font, "ar_bold": ar_bold,
    }


def _doc(buffer: BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )


def _para(text: str, styles: dict, default_style: str = "body_en"):
    """Build a Paragraph. AR strings get shape_arabic + RTL style."""
    if is_arabic(text):
        return Paragraph(shape_arabic(text), styles["body_ar"])
    return Paragraph(text, styles[default_style])


def _table_block(payload: list[list[str]], styles: dict) -> Table:
    """Render a markdown table as a styled ReportLab Table."""
    table_is_ar = any(is_arabic(" ".join(r)) for r in payload)
    cell_style = styles["body_ar"] if table_is_ar else styles["body_en"]
    header_font = styles["ar_bold"] if table_is_ar else "Helvetica-Bold"
    rows: list[list[Paragraph]] = []
    for ri, row in enumerate(payload):
        cells = []
        for cell in row:
            text = shape_arabic(cell) if table_is_ar else cell
            if ri == 0:
                style = ParagraphStyle(
                    f"th_{ri}", parent=cell_style,
                    fontName=header_font, textColor=colors.white,
                )
            else:
                style = cell_style
            cells.append(Paragraph(text, style))
        rows.append(cells)
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), header_font),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _bytes(buf: BytesIO) -> bytes:
    buf.seek(0)
    return buf.getvalue()


def export_chat_pdf(messages: list[dict], date_format: str = "dual") -> bytes:
    noto = register_arabic_fonts()
    styles = _build_styles(noto)
    buf = BytesIO()
    doc = _doc(buf)
    story: list = [
        Paragraph("TadqeeqAI Chat Export", styles["title_chat"]),
        Paragraph(
            f"Generated: {format_dual_date(lang='en', mode=date_format, with_time=True)}",
            styles["meta"],
        ),
        HRFlowable(width="100%", thickness=1, color=RULE),
        Spacer(1, 16),
    ]
    for msg in messages:
        role = "You" if msg.get("role") == "user" else "TadqeeqAI"
        story.append(Paragraph(role, styles["role"]))
        content = _sanitize_inline(msg.get("content", ""))
        for kind, payload in _split_chat_blocks(content):
            if kind == "table":
                story.append(_table_block(payload, styles))
                story.append(Spacer(1, 6))
            else:
                story.append(_para(payload, styles))
        if msg.get("sources"):
            srcs = ", ".join(s.get("article", "") for s in msg["sources"][:5])
            label = f"Sources: {srcs}"
            if is_arabic(label):
                story.append(Paragraph(shape_arabic(label), styles["sources_ar"]))
            else:
                story.append(Paragraph(label, styles["sources"]))
        story.append(Spacer(1, 8))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Generated by TadqeeqAI", styles["footer"]))
    doc.build(story)
    return _bytes(buf)


def export_library_pdf(
    messages: list[dict],
    category_label: str = "",
    clause_title: str = "",
    date_format: str = "dual",
) -> bytes:
    noto = register_arabic_fonts()
    styles = _build_styles(noto)
    buf = BytesIO()
    doc = _doc(buf)
    header_label = clause_title or category_label or "Clause Library"
    story: list = [
        Paragraph("TadqeeqAI · Clause Library Discussion", styles["title_lib"]),
        Paragraph(f"<b>Topic:</b> {html.escape(header_label)}", styles["meta"]),
    ]
    if category_label and clause_title:
        story.append(Paragraph(f"<b>Category:</b> {html.escape(category_label)}", styles["meta"]))
    story.extend([
        Paragraph(
            f"Generated: {format_dual_date(lang='en', mode=date_format, with_time=True)}",
            styles["meta"],
        ),
        HRFlowable(width="100%", thickness=1, color=RULE),
        Spacer(1, 16),
    ])
    for msg in messages:
        label = "Question" if msg.get("role") == "user" else "Response"
        story.append(Paragraph(label, styles["role_lib"]))
        content = _sanitize_inline(msg.get("content", ""))
        for kind, payload in _split_chat_blocks(content):
            if kind == "table":
                story.append(_table_block(payload, styles))
                story.append(Spacer(1, 6))
            else:
                story.append(_para(payload, styles))
        if msg.get("sources"):
            lines: list[str] = []
            for s in msg["sources"]:
                line = "• " + s.get("article", "")
                if s.get("title"):
                    line += f": {s['title']}"
                lines.append(line)
            for line in lines:
                if is_arabic(line):
                    story.append(Paragraph(shape_arabic(line), styles["sources_ar"]))
                else:
                    story.append(Paragraph(line, styles["sources"]))
        story.append(Spacer(1, 8))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Generated by TadqeeqAI · Clause Library", styles["footer"]))
    doc.build(story)
    return _bytes(buf)


def export_compliance_pdf(
    result: dict,
    date_format: str = "dual",
    lang: str = "auto",
) -> bytes:
    """Render a compliance result as PDF — v3.2 .comp-card structure."""
    noto = register_arabic_fonts()
    styles = _build_styles(noto)
    buf = BytesIO()
    doc = _doc(buf)

    chrome_lang = resolve_compliance_lang(result, lang)
    is_ar = chrome_lang == "ar"
    chrome = _COMPLIANCE_CHROME[chrome_lang]
    score = int(result.get("score", 0))
    if score >= 80:
        score_color = colors.HexColor("#3FB950")
    elif score >= 50:
        score_color = colors.HexColor("#FFBD2E")
    else:
        score_color = colors.HexColor("#FF453A")

    def _ar_style(parent_key: str, **overrides) -> ParagraphStyle:
        base = styles[parent_key]
        return ParagraphStyle(
            f"{parent_key}_compl_ar",
            parent=base,
            fontName=styles["ar_font"],
            alignment=TA_RIGHT,
            **overrides,
        )

    title_style = (
        ParagraphStyle("compl_title_ar", parent=styles["title_brief"], fontName=styles["ar_bold"],
                       alignment=TA_RIGHT, textColor=colors.HexColor("#2DD4BF"))
        if is_ar
        else styles["title_brief"]
    )
    meta_style = _ar_style("meta") if is_ar else styles["meta"]
    score_style = ParagraphStyle(
        "compl_score", parent=styles["body_en"], fontSize=14, leading=18,
        textColor=score_color, fontName=("Helvetica-Bold" if not is_ar else styles["ar_bold"]),
        alignment=(TA_RIGHT if is_ar else TA_LEFT),
    )
    name_style = ParagraphStyle(
        "compl_name", parent=styles["body_en"], fontSize=13, leading=18,
        fontName=("Helvetica-Bold" if not is_ar else styles["ar_bold"]),
        alignment=(TA_RIGHT if is_ar else TA_LEFT),
    )
    reg_style = _ar_style("sources") if is_ar else styles["sources"]
    detail_style = styles["body_ar"] if is_ar else styles["body_en"]

    title_text = shape_arabic(chrome["title"]) if is_ar else chrome["title"]
    story: list = [Paragraph(title_text, title_style)]

    doc_line = f"{chrome['doc_label']}: {result.get('filename', '')}"
    gen_line = (
        f"{chrome['gen_label']}: "
        f"{format_dual_date(lang=chrome_lang, mode=date_format, with_time=True)}"
    )
    score_line = f"{chrome['score_word']}: {score}% ({chrome['score_label']})"

    if is_ar:
        story.append(Paragraph(shape_arabic(doc_line), meta_style))
        story.append(Paragraph(shape_arabic(gen_line), meta_style))
        story.append(Paragraph(shape_arabic(score_line), score_style))
    else:
        story.append(Paragraph(doc_line, meta_style))
        story.append(Paragraph(gen_line, meta_style))
        story.append(Paragraph(score_line, score_style))

    story.append(HRFlowable(width="100%", thickness=1, color=RULE))
    story.append(Spacer(1, 14))

    for check in result.get("checks", []):
        is_pass = check.get("status") == "compliant"
        status_label = chrome["pass" if is_pass else "warn"]
        icon = "✓" if is_pass else "⚠"
        strings = _compliance_check_strings(check, chrome_lang)
        name_line = f"{icon} {strings['name']} ({status_label})"
        reg_line = f"{chrome['reg_label']}: {strings['regulation']}"
        if is_ar:
            story.append(Paragraph(shape_arabic(name_line), name_style))
            story.append(Paragraph(shape_arabic(reg_line), reg_style))
            if strings["detail"]:
                story.append(Paragraph(shape_arabic(strings["detail"]), detail_style))
        else:
            story.append(Paragraph(name_line, name_style))
            story.append(Paragraph(reg_line, reg_style))
            if strings["detail"]:
                story.append(Paragraph(_sanitize_inline(strings["detail"]), detail_style))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 8))
    story.append(Paragraph(chrome["footer"], styles["footer"]))
    doc.build(story)
    return _bytes(buf)


def export_brief_pdf(text: str, date_format: str = "dual") -> bytes:
    noto = register_arabic_fonts()
    styles = _build_styles(noto)
    buf = BytesIO()
    doc = _doc(buf)
    sections = [s.strip() for s in re.split(r"\n\s*---\s*\n", text or "") if s.strip()]
    if not sections:
        sections = [text or ""]
    story: list = []
    for idx, section_text in enumerate(sections):
        if idx > 0:
            story.append(PageBreak())
        section_is_ar = is_arabic(section_text)
        title = "الملخص التنفيذي" if section_is_ar else "Executive Brief"
        if section_is_ar:
            story.append(Paragraph(shape_arabic(title), styles["h1_ar"]))
        else:
            story.append(Paragraph(title, styles["title_brief"]))
        story.append(Paragraph(
            f"Generated: {format_dual_date(lang='en', mode=date_format, with_time=True)}",
            styles["meta"],
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=RULE))
        story.append(Spacer(1, 12))
        for raw in strip_emojis(section_text).split("\n"):
            line = raw.rstrip()
            if not line.strip():
                continue
            ar = is_arabic(line)
            if line.startswith("# "):
                body = line[2:].strip()
                style = styles["h1_ar"] if ar else styles["h1"]
                story.append(Paragraph(shape_arabic(body) if ar else body, style))
            elif line.startswith("## "):
                body = line[3:].strip()
                style = styles["h2_ar"] if ar else styles["h2"]
                story.append(Paragraph(shape_arabic(body) if ar else body, style))
            elif re.match(r"^[\-\*]\s+", line):
                body = "• " + re.sub(r"^[\-\*]\s+", "", line).strip()
                story.append(_para(_sanitize_inline(body), styles))
            else:
                story.append(_para(_sanitize_inline(line), styles))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Generated by TadqeeqAI", styles["footer"]))
    doc.build(story)
    return _bytes(buf)
