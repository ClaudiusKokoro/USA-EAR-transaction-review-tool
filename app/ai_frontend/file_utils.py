"""Local file reading helpers used before content is sent to an LLM provider."""

from __future__ import annotations

from pathlib import Path


def _try_import(name: str):
    try:
        module = __import__(name)
        return module
    except Exception:
        return None


def extract_text(filename: str, data: bytes, max_chars: int = 60000) -> tuple[str, str]:
    """Return (extracted_text, note). Unsupported binaries can still be uploaded."""

    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".xml", ".html", ".htm", ".py", ".yaml", ".yml"}:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")
        return text[:max_chars], f"Read as plain text ({len(text):,} characters)."
    if suffix == ".pdf":
        pdf_module = _try_import("pypdf")
        if pdf_module is None:
            return "", "PDF text extraction needs pypdf (pip install pypdf); the raw file was kept instead."
        try:
            reader = pdf_module.PdfReader(__import__("io").BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages)
            return text[:max_chars], f"Extracted PDF text ({len(reader.pages)} pages)."
        except Exception as exc:
            return "", f"PDF text extraction failed: {exc}"
    if suffix == ".docx":
        docx_module = _try_import("docx")
        if docx_module is None:
            return "", "DOCX text extraction needs python-docx (pip install python-docx)."
        try:
            import io

            document = docx_module.Document(io.BytesIO(data))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            return text[:max_chars], "Extracted DOCX text."
        except Exception as exc:
            return "", f"DOCX text extraction failed: {exc}"
    if suffix in {".xlsx", ".xls"}:
        try:
            import io

            import pandas as pd

            excel_file = io.BytesIO(data)
            sheets = pd.read_excel(excel_file, sheet_name=None, engine="openpyxl" if suffix == ".xlsx" else "xlrd")
            parts = []
            for name, frame in sheets.items():
                parts.append(f"Sheet: {name}\n" + frame.to_csv(index=False))
            return ("\n\n".join(parts))[:max_chars], "Extracted Excel sheet content."
        except Exception as exc:
            return "", f"Excel text extraction failed: {exc}"
    if suffix in {".doc"}:
        return "", "Legacy .doc files cannot be parsed locally; upload the original file instead."
    return (
        "",
        f"No local text extraction for file type {suffix or 'unknown'}; upload the original file instead.",
    )
