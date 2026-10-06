"""Deterministic PDF export of saved evidence; never calls an AI provider."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak

from app.schemas import AnalysisContent, AssessmentContent, CompanyProfile

FONT_DIR = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("TenderSans", str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("TenderSansBold", str(FONT_DIR / "VeraBd.ttf")))
pdfmetrics.registerFontFamily("TenderSans", normal="TenderSans", bold="TenderSansBold",
                            italic="TenderSans", boldItalic="TenderSansBold")


def build_report(filename: str, page_count: int | None, analysis: AnalysisContent,
                 assessment: AssessmentContent | None = None, profile: CompanyProfile | None = None,
                 analysis_updated: str | None = None, assessment_updated: str | None = None) -> bytes:
    stream = BytesIO()
    styles = getSampleStyleSheet()
    base = dict(fontName="TenderSans", textColor=colors.HexColor("#343b35"), leading=15,
                fontSize=10, spaceAfter=8, splitLongWords=True)
    body = ParagraphStyle("TenderBody", **base)
    muted = ParagraphStyle("TenderMuted", parent=body, fontSize=8, leading=12,
                           textColor=colors.HexColor("#596159"))
    title = ParagraphStyle("TenderTitle", parent=body, fontName="TenderSansBold", fontSize=26, leading=32)
    heading = ParagraphStyle("TenderHeading", parent=body, fontName="TenderSansBold", fontSize=16,
                             leading=22, spaceBefore=16, keepWithNext=True,
                             backColor=colors.HexColor("#e5eadf"), borderPadding=8)
    sub = ParagraphStyle("TenderSub", parent=body, fontName="TenderSansBold", fontSize=11,
                         keepWithNext=True, spaceBefore=10)
    story = []

    def add(value, style=body):
        # User/model strings must never become ReportLab XML markup or file references.
        story.append(Paragraph(escape(str(value)).replace("\n", "<br/>"), style))

    def refs(numbers):
        valid = list(dict.fromkeys(n for n in numbers if n > 0 and (page_count is None or n <= page_count)))
        add("Source PDF pages: " + (", ".join(map(str, valid)) if valid else "No valid page citation; verify manually."), muted)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d8d0c2"))
        canvas.line(18*mm, 16*mm, 192*mm, 16*mm)
        canvas.setFont("TenderSans", 8)
        canvas.setFillColor(colors.HexColor("#596159"))
        canvas.drawString(18*mm, 11*mm, "TenderLens / Evidence-first procurement brief")
        canvas.drawRightString(192*mm, 11*mm, f"Report page {doc.page}")
        canvas.restoreState()

    add("TENDERLENS / PROCUREMENT INTELLIGENCE", muted)
    add("Tender assessment report", title)
    add(filename, sub)
    add(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Uploaded PDF: {page_count or 'unknown'} pages", muted)
    add(f"Analysis saved: {analysis_updated or 'unknown'}", muted)
    add("This report exports saved AI findings and self-reported company information. It is not independent compliance verification, legal advice, a probability of winning, or confirmation that bidding is still open. Page references refer to the uploaded PDF, not this report. Verify original clauses, dates and completeness.", muted)
    add("01 / Tender overview", heading)
    add(analysis.overview.label, sub)
    add(analysis.overview.detail)
    refs(analysis.overview.page_numbers)
    sections = [("Important dates", "important_dates"), ("Eligibility", "eligibility"),
                ("Mandatory requirements", "mandatory_requirements"), ("Required documents", "required_documents"),
                ("Financial conditions", "financial_conditions"), ("Deliverables", "deliverables"), ("Risks", "risks")]
    for label, field in sections:
        add(label, heading)
        findings = getattr(analysis, field)
        if not findings:
            add("No supported findings in the saved analysis.", muted)
        for finding in findings:
            add(finding.label, sub)
            add(finding.detail)
            refs(finding.page_numbers)
    story.append(PageBreak())
    add("02 / Company fit", heading)
    if assessment is None:
        add("No company assessment included. Run an assessment and export again for company fit, gaps and the submitted profile.")
    else:
        add(assessment.company_name, sub)
        add(f"Recommendation: {assessment.recommendation.replace('_', ' ').title()}")
        add(f"Requirements matched: {assessment.score}% | Evidence coverage: {assessment.coverage}%")
        add(f"Evaluated: {assessment.evaluated_on} | Assessment saved: {assessment_updated or 'unknown'}", muted)
        add(assessment.summary)
        add("Match = met / total assessed requirements. Coverage = (met + unmet) / total. These figures are based on saved analysis, not the tender's official technical scoring rubric. Unknown required conditions need review; confirmed required-condition gaps block a Bid.", muted)
        for item in assessment.comparisons:
            add(f"{item.label} / {item.status.upper()}", sub)
            add("Tender condition: " + item.requirement)
            refs(item.page_numbers)
            add("Required condition: " + ("Yes" if item.mandatory else "No"), muted)
            add("Assessment: " + item.reason)
            add("Gap: " + (item.missing_information or ("No information gap identified." if item.status == "met" else item.reason)))
            if item.profile_evidence:
                add("Submitted evidence excerpt: " + item.profile_evidence)
            for entry in item.entered_information:
                add(f"Entered / {entry.field.replace('_', ' ')}: {entry.value or 'Not provided'}", muted)
            if item.suggested_input:
                add("Answer template (fill truthfully): " + item.suggested_input)
        story.append(PageBreak())
        add("03 / Submitted company snapshot", heading)
        if profile:
            for field, value in profile.model_dump().items():
                add(field.replace("_", " ").title(), sub)
                add(value or "Not provided")
        else:
            add("Profile snapshot unavailable.", muted)
    document = SimpleDocTemplate(stream, pagesize=(210*mm, 297*mm), leftMargin=18*mm,
        rightMargin=18*mm, topMargin=18*mm, bottomMargin=24*mm,
        title="TenderLens assessment report", author="TenderLens")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
