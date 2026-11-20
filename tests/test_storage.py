import io
import zipfile
from pathlib import Path

import pytest
from docx import Document as new_docx

from services.storage import UploadRejected, default_title, detect_type, save_upload


def docx_bytes() -> bytes:
    buffer = io.BytesIO()
    new_docx().save(buffer)
    return buffer.getvalue()


def test_valid_pdf_and_docx_are_stored_under_random_names(tmp_path):
    for name, data, kind in [("a.pdf", b"%PDF-1.7 ...", "pdf"), ("b.DOCX", docx_bytes(), "docx")]:
        path, file_type = save_upload(name, data, upload_dir=str(tmp_path))
        assert file_type == kind and Path(path).parent == tmp_path and Path(path).read_bytes() == data
        assert Path(path).stem not in name


def test_traversal_in_file_name_cannot_escape_the_upload_folder(tmp_path):
    path, _ = save_upload("../../etc/passwd.pdf", b"%PDF-1.7", upload_dir=str(tmp_path / "up"))
    assert Path(path).resolve().parent == (tmp_path / "up").resolve()


@pytest.mark.parametrize("name,data", [
    ("virus.exe", b"MZ..."), ("fake.pdf", b"<html>not a pdf</html>"), ("fake.docx", b"%PDF-1.7"),
    ("broken.docx", b"PK\x03\x04 broken"), ("empty.pdf", b""),
])
def test_bad_uploads_are_rejected(tmp_path, name, data):
    with pytest.raises(UploadRejected):
        save_upload(name, data, upload_dir=str(tmp_path))


def test_zip_that_is_not_word_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(UploadRejected):
        detect_type("x.docx", buffer.getvalue())


def test_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.MAX_UPLOAD_BYTES", 100)
    with pytest.raises(UploadRejected):
        save_upload("big.pdf", b"%PDF-" + b"0" * 200, upload_dir=str(tmp_path))


def test_default_title():
    assert default_title("C:\\Users\\Nedas\\atostogu_tvarka.pdf") == "atostogu_tvarka"
    assert default_title("../../x/report.final.docx") == "report.final"
    assert len(default_title("a" * 500 + ".pdf")) == 200
