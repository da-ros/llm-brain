"""Tesseract OCR for photos and scanned PDFs.

Unstructured's image and PDF partition modules load the unstructured_inference
package as soon as they are imported, before any OCR strategy is chosen.
That package is the layout model this image does not install. These helpers
read pixels with Pillow and Tesseract and never load it.
"""

from __future__ import annotations

from exceptions import LoaderError

_LANG = "eng+spa"
_heif_ready = False
# Tesseract saves the picture under its Pillow format name. HEIF is not one of those.
_TESSERACT_FORMATS = {"PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP", "PPM", "PBM", "PGM", "JPEG2000"}


def _prepare_heif() -> None:
    """Let Pillow open HEIC photos. Other formats do not need this."""
    global _heif_ready
    if _heif_ready:
        return
    try:
        from pi_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass
    _heif_ready = True


def _for_tesseract(image):
    """Hand Tesseract a PNG when Pillow's format is one it cannot save."""
    if not isinstance(image.format, str) or image.format in _TESSERACT_FORMATS:
        return image
    converted = image.convert("RGB") if image.mode not in {"RGB", "L"} else image.copy()
    converted.format = "PNG"
    return converted


def _read_image(image) -> str:
    # The installed wheel is unstructured.pytesseract. Its import name is
    # unstructured_pytesseract, and it does not provide a pytesseract module.
    import unstructured_pytesseract

    return str(unstructured_pytesseract.image_to_string(image, lang=_LANG) or "").strip()


def _frame_count(image) -> int:
    count = getattr(image, "n_frames", 1)
    if isinstance(count, int) and count > 1:
        return count
    return 1


def ocr_image(file_path: str) -> str:
    """Return the words in one photo. A multi-frame note keeps every frame."""
    _prepare_heif()
    try:
        from PIL import Image

        with Image.open(file_path) as image:
            image.load()
            count = _frame_count(image)
            if count == 1:
                return _read_image(_for_tesseract(image))
            parts: list[str] = []
            for index in range(count):
                image.seek(index)
                image.load()
                frame = image.copy()
                frame.format = "PNG"
                text = _read_image(_for_tesseract(frame))
                if text:
                    parts.append(text)
            return "\n\n".join(parts)
    except Exception as exc:
        raise LoaderError(f"Tesseract OCR failed: {exc}") from exc


def ocr_pdf(file_path: str) -> list[tuple[int, str]]:
    """OCR each page of a PDF that has no embedded text. Page numbers start at 1."""
    try:
        from pdf2image import convert_from_path

        pages = convert_from_path(file_path)
    except Exception as exc:
        raise LoaderError(f"PDF OCR failed: {exc}") from exc
    found: list[tuple[int, str]] = []
    for number, image in enumerate(pages, start=1):
        try:
            text = _read_image(image)
        except Exception as exc:
            raise LoaderError(f"PDF OCR failed: {exc}") from exc
        if text:
            found.append((number, text))
    return found
