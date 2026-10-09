"""OCR an image with Tesseract. Video is never passed here.

UnstructuredImageLoader imports the PDF layout stack (pdfminer, then
unstructured-inference and torch) before it reads the file. That import
is what turned POST /scan into a 500. Tesseract is the OCR engine that
loader uses for plain text, which is all a screenshot scan needs.
"""

from __future__ import annotations

import io


def _extract(payload: bytes) -> str:
    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(payload))
    image.load()
    return pytesseract.image_to_string(image, lang="eng+spa")


def ocr_image(payload: bytes, suffix: str = ".png") -> str:
    """Return OCR text. Empty string means the image had no readable text.

    ``suffix`` is the extension the scan already chose. Pillow reads the
    bytes directly, so the extension is not used to pick a decoder.
    """
    del suffix
    if not payload:
        return ""
    try:
        text = _extract(payload)
    except OSError:
        return ""
    return str(text or "").strip()
