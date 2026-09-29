"""Upload validation (FV-12)."""
from __future__ import annotations

import io
import zipfile

import pytest

from finveritas.security import uploads
from finveritas.security.uploads import UploadRejected


def make_pdf(pages: int = 1) -> bytes:
    """Build a minimal, valid multi-page PDF by hand (no extra dependencies)."""
    objs: list[bytes] = []
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    for _ in range(pages):
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def make_xlsx(extra_bytes: int = 0) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        if extra_bytes:
            zf.writestr("xl/bomb.xml", b"0" * extra_bytes)
    return buf.getvalue()


def test_valid_pdf_is_accepted():
    assert uploads.validate_pdf(make_pdf(2), "income.pdf").kind == "pdf"


def test_executable_renamed_to_pdf_is_rejected():
    with pytest.raises(UploadRejected, match="not a valid PDF"):
        uploads.validate_pdf(b"MZ\x90\x00" + b"\x00" * 200, "invoice.pdf")


def test_html_payload_renamed_to_pdf_is_rejected():
    with pytest.raises(UploadRejected):
        uploads.validate_pdf(b"<html><script>alert(1)</script></html>", "statement.pdf")


def test_oversized_pdf_is_rejected(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_PDF_BYTES", 100)
    with pytest.raises(UploadRejected, match="exceeds"):
        uploads.validate_pdf(make_pdf(1), "big.pdf")


def test_pdf_page_limit(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_PDF_PAGES", 3)
    uploads.validate_pdf(make_pdf(3), "ok.pdf")
    with pytest.raises(UploadRejected, match="pages"):
        uploads.validate_pdf(make_pdf(4), "many.pdf")


def test_corrupt_pdf_is_rejected():
    with pytest.raises(UploadRejected, match="could not be opened"):
        uploads.validate_pdf(b"%PDF-1.4\n garbage garbage", "broken.pdf")


def test_too_many_pdfs_in_one_batch():
    pdf = make_pdf(1)
    with pytest.raises(UploadRejected, match="at most"):
        uploads.validate_pdf_batch([(pdf, f"f{i}.pdf") for i in range(uploads.MAX_PDF_FILES + 1)])


def test_path_components_are_stripped_from_filenames():
    assert uploads.validate_pdf(make_pdf(), "../../etc/passwd.pdf").filename == "passwd.pdf"
    assert uploads.validate_pdf(make_pdf(), "..\\..\\win.pdf").filename == "win.pdf"


def test_valid_csv_and_xlsx_are_accepted():
    assert uploads.validate_spreadsheet(b"period,revenue\n2024,100\n", "data.csv").kind == "csv"
    assert uploads.validate_spreadsheet(make_xlsx(), "data.xlsx").kind == "xlsx"


def test_binary_disguised_as_csv_is_rejected():
    with pytest.raises(UploadRejected, match="binary"):
        uploads.validate_spreadsheet(b"MZ\x00\x00\x00binary", "data.csv")


def test_csv_row_limit(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_CSV_ROWS", 10)
    with pytest.raises(UploadRejected, match="rows"):
        uploads.validate_spreadsheet(b"a,b\n" * 20, "big.csv")


def test_xlsx_with_wrong_magic_is_rejected():
    with pytest.raises(UploadRejected, match="does not match"):
        uploads.validate_spreadsheet(b"%PDF-1.4 not excel", "data.xlsx")


def test_xlsx_zip_bomb_is_rejected(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_XLSX_UNCOMPRESSED", 10_000)
    with pytest.raises(UploadRejected, match="zip bomb"):
        uploads.validate_spreadsheet(make_xlsx(extra_bytes=100_000), "bomb.xlsx")


def test_disallowed_extension_is_rejected():
    with pytest.raises(UploadRejected):
        uploads.validate_spreadsheet(b"#!/bin/sh\nrm -rf /", "script.sh")


@pytest.mark.parametrize("cell", ["=HYPERLINK(\"http://evil\")", "+1+1", "-2+3", "@SUM(A1)", "=cmd|' /C calc'!A0"])
def test_formula_injection_is_neutralised(cell):
    assert uploads.neutralize_csv_cell(cell).startswith("'")


def test_plain_values_are_unchanged():
    assert uploads.neutralize_csv_cell("Infosys") == "Infosys" and uploads.neutralize_csv_cell(42) == 42
