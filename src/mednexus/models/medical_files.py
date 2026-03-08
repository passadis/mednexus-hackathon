"""Medical file classification model used by the Clinical Sorter."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FileType(StrEnum):
    """Recognised medical file categories."""

    PDF = "pdf"
    DICOM = "dicom"
    IMAGE = "image"         # JPEG / PNG (e.g., scanned X-ray)
    AUDIO = "audio"         # WAV / MP3 (patient recording)
    LAB_CSV = "lab_csv"
    TEXT = "text"           # TXT (transcripts, clinical notes)
    UNKNOWN = "unknown"


# Extension → FileType mapping
_EXT_MAP: dict[str, FileType] = {
    ".pdf": FileType.PDF,
    ".dcm": FileType.DICOM,
    ".dicom": FileType.DICOM,
    ".jpg": FileType.IMAGE,
    ".jpeg": FileType.IMAGE,
    ".png": FileType.IMAGE,
    ".bmp": FileType.IMAGE,
    ".tiff": FileType.IMAGE,
    ".wav": FileType.AUDIO,
    ".mp3": FileType.AUDIO,
    ".m4a": FileType.AUDIO,
    ".flac": FileType.AUDIO,
    ".csv": FileType.LAB_CSV,
    ".txt": FileType.TEXT,
}


class MedicalFile(BaseModel):
    """Metadata for a file discovered by the Clinical Sorter."""

    filename: str
    uri: str               # May be local path OR Azure Blob URI
    file_type: FileType = FileType.UNKNOWN
    patient_id: str = ""
    size_bytes: int = 0
    sha256: str = ""

    @classmethod
    def classify(cls, filename: str) -> FileType:
        """Determine FileType from the file extension."""
        import pathlib

        ext = pathlib.PurePath(filename).suffix.lower()
        return _EXT_MAP.get(ext, FileType.UNKNOWN)
