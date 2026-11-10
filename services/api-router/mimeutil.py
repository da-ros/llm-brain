"""MIME detection for uploads — python-magic on bytes, not file extension."""

from __future__ import annotations

import mimetypes

IMAGE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
}

VIDEO_MIMES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/mpeg",
    "video/x-matroska",
}

ALLOWED_MIMES = (
    {
        "application/pdf",
        "text/plain",
        "text/csv",
        "text/calendar",
        "text/x-vcalendar",
        "text/html",
        "application/xhtml+xml",
        "message/rfc822",
        "application/vnd.ms-outlook",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    | IMAGE_MIMES
    | VIDEO_MIMES
)


def detect_mime(content: bytes, filename: str | None = None) -> str:
    """Return the MIME type of `content` using python-magic."""
    try:
        import magic

        mime = magic.from_buffer(content, mime=True)
        if mime:
            return mime.split(";")[0].strip().lower()
    except Exception:
        pass

    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed.split(";")[0].strip().lower()
    return "application/octet-stream"


def is_allowed_upload_mime(mime_type: str) -> bool:
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime in ALLOWED_MIMES:
        return True
    return mime.startswith("video/")


def supported_types_message() -> str:
    return (
        "Supported types: text/plain, text/csv, text/calendar (ICS), application/pdf, "
        "text/html, message/rfc822, DOCX, Excel (xls/xlsx), "
        "image (png/jpeg/tiff/gif/webp/bmp/heic), video (mp4/webm/quicktime)"
    )
