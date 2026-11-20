import io
import uuid
import zipfile
from pathlib import Path, PureWindowsPath

from app_config import MAX_UPLOAD_BYTES, UPLOAD_DIR

MAX_UNPACKED_BYTES = 200 * 1024 * 1024        # a DOCX is a ZIP; refuse "zip bombs"
_SIGNATURES = {"pdf": b"%PDF-", "docx": b"PK\x03\x04"}


class UploadRejected(ValueError):
    """The upload is not acceptable; the message is safe to show to the user."""


def detect_type(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in _SIGNATURES:
        raise UploadRejected("Palaikomi tik PDF ir DOCX failai.")
    if not data.startswith(_SIGNATURES[extension]):
        raise UploadRejected("Failo turinys neatitinka jo plėtinio.")
    if extension == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
                unpacked = sum(info.file_size for info in archive.infolist())
        except zipfile.BadZipFile as exc:
            raise UploadRejected("DOCX failas sugadintas.") from exc
        if "word/document.xml" not in names:
            raise UploadRejected("Tai ne Word dokumentas.")
        if unpacked > MAX_UNPACKED_BYTES:
            raise UploadRejected("Išskleistas dokumentas per didelis.")
    return extension


def default_title(filename: str) -> str:
    """Title shown in the UI: the file name without any folders, at most 200 characters."""
    name = PureWindowsPath(filename).name          # also strips Windows-style 'C:\\dir\\' prefixes
    return (Path(name).stem or "document")[:200]


def save_upload(filename: str, data: bytes, upload_dir: str = UPLOAD_DIR) -> tuple[str, str]:
    """Validate and store the bytes under a random name. Returns (stored_path, 'pdf' | 'docx')."""
    if not data:
        raise UploadRejected("Failas tuščias.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected(f"Failas didesnis nei {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    file_type = detect_type(filename, data)
    folder = Path(upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}.{file_type}"      # never build the path from the user's file name
    stored.write_bytes(data)
    return str(stored), file_type
