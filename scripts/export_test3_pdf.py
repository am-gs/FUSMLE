import base64
import html
import json
import mimetypes
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "artifacts" / "manifests" / "test3_nidhi_v1.json"
RUNTIME_PATH = ROOT / "vercel" / "uworld-api-deploy" / "gold_runtime.json"
IMAGE_ROOT = ROOT / "vercel" / "uworld-api-deploy"
EXPORT_DIR = ROOT / "artifacts" / "exports"
HTML_PATH = EXPORT_DIR / "test3_nidhi_v1_with_answers.html"
PDF_PATH = EXPORT_DIR / "test3_nidhi_v1_with_answers.pdf"
EXPORT_TITLE = "TEST 3 — Nidhi Personalized NBME-Style Reconstruction"


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


def load_questions():
    questions = json.loads(RUNTIME_PATH.read_text())
    return {question["id"]: question for question in questions}


def esc(value):
    text = "" if value is None else html.unescape(str(value))
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_table(table):
    html = ['<table class="nbme-table">']
    if table.get("title"):
        html.append(f"<caption>{esc(table['title'])}</caption>")
    html.append("<thead><tr>")
    for column in table.get("columns", []):
        html.append(f"<th>{esc(column)}</th>")
    html.append("</tr></thead><tbody>")
    for row in table.get("rows", []):
        html.append("<tr>")
        for cell in row:
            html.append(f"<td>{esc(cell)}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def render_question_text(question):
    text = esc(question.get("text", ""))
    for index, table in enumerate(question.get("tables") or []):
        text = text.replace(f"[[table:{index}]]", render_table(table))
    return text.replace("\n", "<br>")


def render_option_table(table, correct_option_id):
    correct_index = max(0, int(correct_option_id) - 1)
    html = ['<table class="nbme-table option-table"><thead><tr><th>Choice</th>']
    for column in table.get("columns", []):
        html.append(f"<th>{esc(column)}</th>")
    html.append("</tr></thead><tbody>")
    for index, row in enumerate(table.get("rows", [])):
        css = ' class="correct-option-row"' if index == correct_index else ""
        html.append(f"<tr{css}>")
        for cell in row:
            html.append(f"<td>{esc(cell)}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def option_letter(option, index):
    return option.get("letter") or chr(65 + index)


def option_text(option):
    text = option.get("text", "")
    letter = option.get("letter")
    prefix = f"{letter}) "
    if letter and text.startswith(prefix):
        return text[len(prefix) :]
    return text


def render_options(question, correct_option_id):
    if question.get("option_table"):
        return render_option_table(question["option_table"], correct_option_id)

    html = ['<ol class="options">']
    for index, option in enumerate(question.get("options", [])):
        css = ' class="correct-option"' if option.get("id") == correct_option_id else ""
        html.append(
            f'<li{css}><span class="option-letter">{esc(option_letter(option, index))}.</span> '
            f"{esc(option_text(option))}</li>"
        )
    html.append("</ol>")
    return "".join(html)


def find_correct_option(question):
    correct_id = question.get("correct_answer")
    for index, option in enumerate(question.get("options", [])):
        if option.get("id") == correct_id:
            return {
                "id": correct_id,
                "letter": option_letter(option, index),
                "text": option_text(option),
            }
    return {"id": correct_id, "letter": "?", "text": ""}


def image_data_uri(url):
    relative = url.lstrip("/")
    if relative.startswith("api/images_crop/"):
        file_path = IMAGE_ROOT / "images_crop" / relative.split("/")[-1]
    elif relative.startswith("api/images_pages/"):
        parts = relative.split("/")
        file_path = IMAGE_ROOT / "images_pages" / parts[-2] / parts[-1]
    elif relative.startswith("api/images/"):
        parts = relative.split("/")
        file_path = IMAGE_ROOT / "images_webp" / parts[-2] / parts[-1]
    else:
        return None
    if not file_path.exists():
        return None
    mime = mimetypes.guess_type(str(file_path))[0] or "image/webp"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_images(question):
    image_urls = question.get("imageUrls") or (
        [question.get("image_url")] if question.get("image_url") else []
    )
    html = []
    for url in image_urls:
        data_uri = image_data_uri(url)
        src = data_uri or esc(url)
        html.append(
            '<figure class="question-image">'
            f'<img src="{src}" alt="Question image">'
            "</figure>"
        )
    return "".join(html)


def explanation_html(question):
    explanation = html.unescape(question.get("explanation", ""))
    if not explanation:
        return ""
    explanation = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", explanation)
    explanation = explanation.replace("\r\n", "\n").replace("\r", "\n")
    explanation = explanation.replace("\n\n", "<br><br>").replace("\n", "<br>")
    return explanation


def build_html():
    manifest = load_manifest()
    questions_by_id = load_questions()
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{esc(EXPORT_TITLE)} — Answer Key PDF</title>",
        """
        <style>
        @page { size: Letter; margin: 0.55in; }
        body { font-family: Arial, Helvetica, sans-serif; color: #111; line-height: 1.38; font-size: 11px; }
        h1, h2, h3 { margin: 0 0 10px; }
        .cover { page-break-after: always; }
        .cover p { margin: 6px 0; }
        .block { page-break-before: always; }
        .question { break-inside: avoid; margin: 0 0 24px; padding: 0 0 18px; border-bottom: 1px solid #ddd; }
        .meta { color: #666; font-size: 10px; margin-bottom: 6px; }
        .stem { font-size: 11px; margin-bottom: 10px; }
        .options { margin: 0 0 10px 20px; padding: 0; }
        .options li { margin: 0 0 4px; }
        .option-letter { font-weight: 700; }
        .correct-option { background: #eef8ef; }
        .correct-option-row { background: #eef8ef; }
        .answer { margin: 8px 0 4px; font-weight: 700; color: #155724; }
        .explanation { margin-top: 6px; }
        .question-image { margin: 10px 0; }
        .question-image img { max-width: 100%; max-height: 480px; border: 1px solid #ccc; }
        .nbme-table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        .nbme-table th, .nbme-table td { border: 1px solid #bbb; padding: 6px; vertical-align: top; }
        .nbme-table caption { text-align: left; font-weight: 700; margin-bottom: 4px; }
        .block-summary { color: #444; font-size: 10px; margin-bottom: 18px; }
        </style>
        """,
        "</head><body>",
        "<section class='cover'>",
        f"<h1>{esc(EXPORT_TITLE)}</h1>",
        "<p>Printable answer key export from the frozen deterministic 120-question manifest.</p>",
        "<p>Contents: all 120 questions in fixed order, images inline, correct answer highlighted, and explanation beneath each item.</p>",
        f"<p>Source forms: {', '.join(manifest.get('source_forms', []))}</p>",
        f"<p>Proxy form: {esc(manifest.get('source_proxy_form', ''))}</p>",
        "</section>",
    ]

    absolute_index = 0
    for block in manifest["blocks"]:
        parts.append(f"<section class='block'><h2>Block {block['block']}</h2>")
        parts.append(
            "<div class='block-summary'>20 questions · 30 minutes in the app · fixed deterministic order</div>"
        )
        for block_index, question_id in enumerate(block["questionIds"], start=1):
            absolute_index += 1
            question = questions_by_id[question_id]
            correct = find_correct_option(question)
            parts.append("<article class='question'>")
            parts.append(
                f"<div class='meta'>Question {absolute_index} of 120 · Block {block['block']} Item {block_index} · "
                f"{esc(question.get('organ_system') or question.get('system') or '')}</div>"
            )
            parts.append(f"<div class='stem'>{render_question_text(question)}</div>")
            parts.append(render_images(question))
            parts.append(render_options(question, correct["id"]))
            parts.append(
                f"<div class='answer'>Correct answer: {esc(correct['letter'])}. {esc(correct['text'])}</div>"
            )
            parts.append(f"<div class='explanation'>{explanation_html(question)}</div>")
            parts.append("</article>")
        parts.append("</section>")

    parts.append("</body></html>")
    return "".join(parts)


def chrome_binary():
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(candidate)
        if path:
            return path

    playwright_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    playwright_candidates = []
    if playwright_cache.exists():
        for app_path in sorted(
            playwright_cache.glob(
                "chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
            )
        ):
            playwright_candidates.append(app_path)
        for shell_path in sorted(
            playwright_cache.glob(
                "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell"
            )
        ):
            playwright_candidates.append(shell_path)

    if playwright_candidates:
        return str(playwright_candidates[-1])

    raise RuntimeError("No Chrome/Chromium binary found for PDF export")


def pdf_escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_fallback_pdf(blocker_message):
    lines = [
        EXPORT_TITLE,
        "",
        "PDF generation was blocked in this environment.",
        blocker_message,
        "",
        f"HTML export is available at: {HTML_PATH}",
    ]
    y = 760
    content_lines = ["BT", "/F1 12 Tf"]
    for line in lines:
        content_lines.append(f"72 {y} Td ({pdf_escape(line)}) Tj")
        y -= 18
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("utf-8")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(content)} >> stream\n".encode("utf-8")
        + content
        + b"\nendstream endobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
    pdf.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("utf-8")
    )
    PDF_PATH.write_bytes(pdf)


def write_export_files():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(build_html(), encoding="utf-8")

    pdf_status = "not_attempted"
    pdf_blocker = None
    try:
        chrome = chrome_binary()
        subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--allow-file-access-from-files",
                "--no-pdf-header-footer",
                f"--print-to-pdf={PDF_PATH}",
                f"file://{HTML_PATH}",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        pdf_status = "success"
    except RuntimeError as exc:
        pdf_status = "blocked"
        pdf_blocker = str(exc)
    except subprocess.CalledProcessError as exc:
        pdf_status = "failed"
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        pdf_blocker = f"Chrome/Chromium failed during PDF export: {detail}"

    if pdf_blocker:
        write_fallback_pdf(pdf_blocker)

    print(f"HTML: {HTML_PATH}")
    print(f"HTML exists: {HTML_PATH.exists()}")
    print(f"PDF: {PDF_PATH}")
    print(f"PDF exists: {PDF_PATH.exists()}")
    print(f"PDF status: {pdf_status}")
    if pdf_blocker:
        print(f"PDF blocker: {pdf_blocker}")


if __name__ == "__main__":
    write_export_files()
