from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#172554")
BLUE = colors.HexColor("#2563EB")
SLATE = colors.HexColor("#475569")
LIGHT_BLUE = colors.HexColor("#EFF6FF")
LIGHT_SLATE = colors.HexColor("#F8FAFC")
AMBER = colors.HexColor("#B45309")
LIGHT_AMBER = colors.HexColor("#FFF7ED")
BORDER = colors.HexColor("#CBD5E1")


def _register_fonts() -> tuple[str, str]:
    fonts_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    regular_name = "EUFundingVera"
    bold_name = "EUFundingVeraBold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular_name, fonts_dir / "Vera.ttf"))
        pdfmetrics.registerFont(TTFont(bold_name, fonts_dir / "VeraBd.ttf"))
    return regular_name, bold_name


def _money(value: float | None) -> str:
    if value is None:
        return "Not provided"
    numeric = float(value)
    if numeric >= 1_000_000:
        return f"EUR {numeric / 1_000_000:.1f}M"
    return f"EUR {numeric:,.0f}"


def _percentage(value: float | None) -> str:
    return "Not provided" if value is None else f"{float(value):.0%}"


def _date(value: object) -> str:
    if value is None:
        return "Not provided"
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return parsed.strftime("%d %b %Y")


def _status(value: object) -> str:
    return {"open": "Open now", "forthcoming": "Opening soon"}.get(
        str(value), "Check official page"
    )


def _text(value: object, fallback: str = "Not provided") -> str:
    rendered = str(value).strip() if value is not None else ""
    return rendered or fallback


def _reason(value: str) -> str:
    return {
        "Multilingual lexical and semantic match with the project description": (
            "The call covers topics that are similar to your project idea."
        ),
        "Lexical match": "The call uses terms that also appear in your project description.",
    }.get(value, value)


def _page_chrome(canvas: Any, document: BaseDocTemplate) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(BORDER)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFillColor(SLATE)
    canvas.setFont("EUFundingVera", 7.5)
    canvas.drawString(18 * mm, 10 * mm, "EU Funding Agents - decision-support report")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def _styles(regular: str, bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ClientTitle",
            parent=base["Title"],
            fontName=bold,
            fontSize=23,
            leading=28,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "ClientSubtitle",
            parent=base["Normal"],
            fontName=regular,
            fontSize=10,
            leading=15,
            textColor=SLATE,
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "heading": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=15,
            leading=19,
            textColor=NAVY,
            spaceBefore=5 * mm,
            spaceAfter=3 * mm,
        ),
        "call_title": ParagraphStyle(
            "CallTitle",
            parent=base["Heading3"],
            fontName=bold,
            fontSize=12.5,
            leading=16,
            textColor=NAVY,
            spaceAfter=1.5 * mm,
        ),
        "body": ParagraphStyle(
            "ClientBody",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#1E293B"),
        ),
        "small": ParagraphStyle(
            "ClientSmall",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=8,
            leading=11,
            textColor=SLATE,
        ),
        "label": ParagraphStyle(
            "ClientLabel",
            parent=base["BodyText"],
            fontName=bold,
            fontSize=7.5,
            leading=10,
            textColor=SLATE,
            spaceAfter=1 * mm,
        ),
        "link": ParagraphStyle(
            "ClientLink",
            parent=base["BodyText"],
            fontName=bold,
            fontSize=9,
            leading=12,
            textColor=BLUE,
        ),
        "warning": ParagraphStyle(
            "ClientWarning",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=8.5,
            leading=12,
            textColor=AMBER,
        ),
    }


def _info_cell(label: str, value: str, styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    return [
        Paragraph(escape(label), styles["label"]),
        Paragraph(escape(value), styles["body"]),
    ]


def _profile_table(
    profile: Mapping[str, Any], styles: Mapping[str, ParagraphStyle], available_width: float
) -> Table:
    sectors = profile.get("sectors") or []
    sector_text = ", ".join(str(value) for value in sectors) if sectors else "Not provided"
    rows = [
        [
            _info_cell("COUNTRY", _text(profile.get("country")), styles),
            _info_cell("ORGANISATION", _text(profile.get("organisation_type")), styles),
        ],
        [
            _info_cell("PROJECT AREA", sector_text, styles),
            _info_cell("ESTIMATED BUDGET", _money(profile.get("requested_budget_eur")), styles),
        ],
    ]
    table = Table(rows, colWidths=[available_width / 2] * 2, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_SLATE),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _call_block(
    rank: int,
    item: Mapping[str, Any],
    styles: Mapping[str, ParagraphStyle],
    available_width: float,
) -> KeepTogether:
    programme = escape(_text(item.get("programme")))
    call_id = escape(_text(item.get("call_id")))
    title = escape(_text(item.get("title")))
    metadata = Table(
        [
            [
                _info_cell("DEADLINE", _date(item.get("deadline")), styles),
                _info_cell("TIME LEFT", f"{item.get('days_remaining', '?')} days", styles),
                _info_cell("CALL STATUS", _status(item.get("call_status")), styles),
            ],
            [
                _info_cell("TOTAL CALL BUDGET", _money(item.get("budget_eur")), styles),
                _info_cell("FUNDING RATE", _percentage(item.get("funding_rate")), styles),
                _info_cell("PROGRAMME", _text(item.get("programme")), styles),
            ],
        ],
        colWidths=[available_width / 3] * 3,
    )
    metadata.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_SLATE),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    reasons = item.get("reasons_for") or []
    reason_text = " ".join(_reason(str(value)) for value in reasons)
    url = escape(_text(item.get("official_url")), quote=True)
    warning = Table(
        [
            [
                Paragraph(
                    "<b>Eligibility check required.</b> The topic appears relevant, but applicant "
                    "and partnership rules must be confirmed on the official call page.",
                    styles["warning"],
                )
            ]
        ],
        colWidths=[available_width],
    )
    warning.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_AMBER),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#FDBA74")),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return KeepTogether(
        [
            Paragraph(f"{rank}. {title}", styles["call_title"]),
            Paragraph(f"{programme} - {call_id}", styles["small"]),
            Spacer(1, 2.5 * mm),
            metadata,
            Spacer(1, 2.5 * mm),
            Paragraph(f"<b>Why it may fit:</b> {escape(reason_text)}", styles["body"]),
            Spacer(1, 2 * mm),
            warning,
            Spacer(1, 2 * mm),
            Paragraph(f'<link href="{url}">Open the official EU call</link>', styles["link"]),
            Spacer(1, 6 * mm),
        ]
    )


def build_client_pdf(
    profile: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    max_calls: int = 5,
) -> bytes:
    """Build a polished, in-memory client report without persisting profile data."""
    if max_calls < 1:
        raise ValueError("max_calls must be at least 1")
    regular, bold = _register_fonts()
    styles = _styles(regular, bold)
    buffer = BytesIO()
    left_margin = right_margin = 18 * mm
    top_margin = 18 * mm
    bottom_margin = 22 * mm
    width, height = A4
    available_width = width - left_margin - right_margin
    document = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title="EU Funding Opportunity Report",
        author="EU Funding Agents",
        subject="Decision-support report for EU funding opportunities",
    )
    frame = Frame(
        left_margin,
        bottom_margin,
        available_width,
        height - top_margin - bottom_margin,
        id="client-report",
    )
    document.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_page_chrome)])

    story: list[Any] = [
        Spacer(1, 7 * mm),
        Paragraph("EU Funding Opportunity Report", styles["title"]),
        Paragraph(
            "A practical shortlist of current calls that may fit your project",
            styles["subtitle"],
        ),
        Paragraph("Project overview", styles["heading"]),
        _profile_table(profile, styles, available_width),
        Spacer(1, 4 * mm),
        Paragraph("PROJECT DESCRIPTION", styles["label"]),
        Paragraph(escape(_text(profile.get("description"))), styles["body"]),
        Spacer(1, 4 * mm),
        Table(
            [
                [
                    Paragraph(
                        "This report supports early opportunity screening. It does not confirm legal "
                        "eligibility, guarantee funding or replace the official call documents.",
                        styles["warning"],
                    )
                ]
            ],
            colWidths=[available_width],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_AMBER),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#FDBA74")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
        Paragraph("Recommended calls", styles["heading"]),
        Paragraph(
            f"Calls are listed from the strongest to the weakest match. Catalogue checked on "
            f"{escape(_text(report.get('as_of')))}.",
            styles["small"],
        ),
        Spacer(1, 4 * mm),
    ]
    recommendations: Sequence[Mapping[str, Any]] = report.get("recommendations") or []
    if recommendations:
        for rank, item in enumerate(recommendations[:max_calls], start=1):
            story.append(_call_block(rank, item, styles, available_width))
    else:
        story.append(Paragraph("No current matching calls were found.", styles["body"]))

    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph("Recommended next step", styles["heading"]),
            Table(
                [
                    [
                        Paragraph(
                            "Open the official page for your preferred call and confirm the applicant "
                            "type, partnership rules, funding rate, available budget and deadline.",
                            styles["body"],
                        )
                    ]
                ],
                colWidths=[available_width],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
                        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#93C5FD")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            ),
        ]
    )
    document.build(story)
    return buffer.getvalue()
