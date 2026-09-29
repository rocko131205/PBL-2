"""Upload validation — size, real file type (magic bytes), and parser limits.

The browser-side `type=[...]` filter only checks the file extension, which an
attacker controls. These checks run on the server before any parser touches
the bytes, limiting parser-exploit and resource-exhaustion (DoS) exposure.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 150
MAX_PDF_FILES = 4
MAX_SHEET_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 5000
MAX_XLSX_UNCOMPRESSED = 50 * 1024 * 1024  # zip-bomb guard
MAX_FILENAME_LEN = 200

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"                            # .xlsx
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"      # legacy .xls


class UploadRejected(ValueError):
    """Raised with a user-safe message when an upload fails validation."""


@dataclass(frozen=True)
class ValidatedFile:
    data: bytes
    filename: str
    kind: str  # "pdf" | "csv" | "xlsx" | "xls"


def _safe_name(filename: str) -> str:
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable())
    if not name or len(name) > MAX_FILENAME_LEN:
        raise UploadRejected("File name is missing or too long.")
    return name


def validate_pdf(data: bytes, filename: str) -> ValidatedFile:
    name = _safe_name(filename)
    if not name.lower().endswith(".pdf"):
        raise UploadRejected(f"'{name}' is not a .pdf file.")
    if len(data) == 0:
        raise UploadRejected(f"'{name}' is empty.")
    if len(data) > MAX_PDF_BYTES:
        raise UploadRejected(f"'{name}' exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB limit.")
    # Real PDFs start with %PDF- (spec allows it within the first 1 KB).
    if _PDF_MAGIC not in data[:1024]:
        raise UploadRejected(f"'{name}' is not a valid PDF (content does not match its extension).")

    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
    except Exception:
        raise UploadRejected(f"'{name}' could not be opened as a PDF (corrupt or encrypted).") from None
    if pages > MAX_PDF_PAGES:
        raise UploadRejected(f"'{name}' has {pages} pages; the limit is {MAX_PDF_PAGES}.")
    return ValidatedFile(data, name, "pdf")


def validate_pdf_batch(files: list[tuple[bytes, str]]) -> list[ValidatedFile]:
    if len(files) > MAX_PDF_FILES:
        raise UploadRejected(f"Upload at most {MAX_PDF_FILES} PDFs at a time.")
    return [validate_pdf(data, name) for data, name in files]


def validate_spreadsheet(data: bytes, filename: str) -> ValidatedFile:
    name = _safe_name(filename)
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext not in {"csv", "xlsx", "xls"}:
        raise UploadRejected("Only .csv, .xlsx and .xls files are accepted.")
    if len(data) == 0:
        raise UploadRejected(f"'{name}' is empty.")
    if len(data) > MAX_SHEET_BYTES:
        raise UploadRejected(f"'{name}' exceeds the {MAX_SHEET_BYTES // (1024 * 1024)} MB limit.")

    if ext == "csv":
        if b"\x00" in data[:8192]:
            raise UploadRejected(f"'{name}' looks like a binary file, not CSV text.")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
            except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes any byte
                raise UploadRejected(f"'{name}' is not readable text.") from None
        if text.count("\n") > MAX_CSV_ROWS:
            raise UploadRejected(f"'{name}' has more than {MAX_CSV_ROWS} rows.")
    elif ext == "xlsx":
        if not data.startswith(_ZIP_MAGIC):
            raise UploadRejected(f"'{name}' is not a valid .xlsx file (content does not match its extension).")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                total = sum(i.file_size for i in zf.infolist())
                if "[Content_Types].xml" not in zf.namelist():
                    raise UploadRejected(f"'{name}' is not a valid Excel workbook.")
        except zipfile.BadZipFile:
            raise UploadRejected(f"'{name}' is corrupt.") from None
        if total > MAX_XLSX_UNCOMPRESSED:
            raise UploadRejected(f"'{name}' expands to more than {MAX_XLSX_UNCOMPRESSED // (1024 * 1024)} MB (possible zip bomb).")
    else:  # xls
        if not data.startswith(_OLE_MAGIC):
            raise UploadRejected(f"'{name}' is not a valid .xls file (content does not match its extension).")
    return ValidatedFile(data, name, ext)


def neutralize_csv_cell(value: object) -> object:
    """Prevent CSV/formula injection when user data is written back to a sheet."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
