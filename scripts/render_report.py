"""Render the short implementation report and its editable component diagram."""

import html
import re
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]


def markup(text):
    paragraphs = []
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("# "):
            paragraphs.append("<h1>" + html.escape(line[2:]) + "</h1>")
        elif line.startswith("## "):
            paragraphs.append("<h2>" + html.escape(line[3:]) + "</h2>")
        else:
            escaped = html.escape(line)
            escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
            paragraphs.append("<p>" + escaped + "</p>")
    return "".join(paragraphs)


def main():
    docs = ROOT / "docs"
    text = (docs / "ARCHITECTURE_SUMMARY.md").read_text()
    first, second = text.split("## Самоулучшение и поставка", 1)
    second = "## Самоулучшение и поставка" + second
    fonts = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font = next((p for p in fonts if p.exists()), None)
    css = (
        "body{font-size:11pt;line-height:1.35}h1{font-size:19pt}"
        "h2{font-size:14pt;color:#174f70}p{margin:8pt 0}"
    )
    archive = None
    if font:
        archive = fitz.Archive(str(font.parent))
        css += "@font-face{font-family:Report;src:url(" + font.name + ")}body{font-family:Report}"
    report = fitz.open()
    page = report.new_page(width=595, height=842)
    _, scale = page.insert_htmlbox(
        fitz.Rect(36, 30, 559, 500), markup(first), css=css, archive=archive
    )
    assert scale > 0.8, "Report text became too small"
    svg = fitz.open(docs / "architecture-diagram.svg")
    diagram = fitz.open("pdf", svg.convert_to_pdf())
    page.show_pdf_page(fitz.Rect(36, 515, 559, 805), diagram, 0)
    page = report.new_page(width=595, height=842)
    _, scale = page.insert_htmlbox(
        fitz.Rect(36, 35, 559, 800), markup(second), css=css, archive=archive
    )
    assert scale > 0.8, "Report text became too small"
    for n, page in enumerate(report, 1):
        page.insert_text((535, 822), str(n), fontsize=9)
    report.subset_fonts()
    path = docs / "ARCHITECTURE_SUMMARY.pdf"
    report.save(path, garbage=4, deflate=True)
    print(f"{path}: {len(report)} pages")


if __name__ == "__main__":
    main()
