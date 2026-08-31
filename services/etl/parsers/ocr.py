"""OCR Parser.

Extracts text from images using Tesseract OCR.
Preprocesses images for better accuracy.
"""

from pathlib import Path

from services.etl.triples import Triple, extract_triples


class OcrParser:
    """Image OCR parser.

    Uses Tesseract via pytesseract for text extraction.
    Preprocesses images (grayscale, contrast) for better accuracy.
    """

    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}

    def supports(self, file_path: str) -> bool:
        """Check if file is a supported image type."""
        return Path(file_path).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str) -> list[Triple]:
        """Parse image and extract triples via OCR.

        Args:
            file_path: Path to image file

        Returns:
            List of extracted triples
        """
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter
        except ImportError:
            raise ImportError("pytesseract and Pillow are required for OCR")

        path = Path(file_path)
        filename = path.name

        try:
            # Open image
            img = Image.open(file_path)

            # Preprocess for better OCR
            img = self._preprocess(img)

            # OCR with both English and Spanish
            text = pytesseract.image_to_string(img, lang="eng+spa")

            if not text or not text.strip():
                return []

            # Extract triples
            return extract_triples(
                text=text,
                source_file=filename,
            )

        except Exception as e:
            raise ValueError(f"Error processing image: {str(e)}")

    def _preprocess(self, img):
        """Preprocess image for better OCR accuracy.

        Args:
            img: PIL Image object

        Returns:
            Preprocessed PIL Image
        """
        from PIL import ImageEnhance, ImageFilter

        # Convert to grayscale
        if img.mode != "L":
            img = img.convert("L")

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # Denoise slightly
        img = img.filter(ImageFilter.MedianFilter(size=3))

        return img
