"""Image processing utilities: OCR text extraction, PDF stitching, compression, and edge VLM."""

import io
import logging
from typing import List

logger = logging.getLogger("pithon.image")

# Lazy-loaded OCR engine
_OCR_ENGINE = None

def get_ocr_engine():
    """Lazily initialize lightweight pytesseract or fallback."""
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE

    import shutil
    if shutil.which("tesseract"):
        try:
            _OCR_ENGINE = "pytesseract"
            logger.info("Initialized pytesseract edge OCR engine.")
            return _OCR_ENGINE
        except Exception as e:
            logger.debug(f"pytesseract not available: {e}")

    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
        logger.info("Initialized RapidOCR onnxruntime engine.")
        return _OCR_ENGINE
    except Exception as e2:
        logger.debug(f"RapidOCR not available: {e2}")

    return None


def extract_text_ocr(image_bytes: bytes) -> str:
    """Extract printed and handwritten text from image bytes using local OCR."""
    engine = get_ocr_engine()
    if engine is None:
        return "⚠️ Local OCR engine not available. Please install `rapidocr-onnxruntime` or `tesseract-ocr`."

    try:
        if engine == "pytesseract":
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img)
            return text.strip()
        else:
            result, _ = engine(image_bytes)
            if not result:
                return "ℹ️ No readable text detected in this image."
            lines = [line[1] for line in result if len(line) > 1 and line[1].strip()]
            return "\n".join(lines).strip()
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        return f"⚠️ Error processing image text: {e}"


def images_to_pdf(image_bytes_list: List[bytes]) -> bytes:
    """Stitch one or multiple images into a clean PDF document."""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow is required for image to PDF conversion.")

    if not image_bytes_list:
        raise ValueError("No images provided for PDF stitching.")

    pil_images = []
    for raw in image_bytes_list:
        try:
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            pil_images.append(im)
        except Exception as e:
            logger.warning(f"Skipping unreadable image in PDF conversion: {e}")

    if not pil_images:
        raise ValueError("Could not decode any of the provided images.")

    pdf_buffer = io.BytesIO()
    first_img = pil_images[0]
    rest_imgs = pil_images[1:] if len(pil_images) > 1 else []

    first_img.save(
        pdf_buffer,
        format="PDF",
        save_all=True,
        append_images=rest_imgs,
        resolution=100.0
    )
    return pdf_buffer.getvalue()


def compress_image(image_bytes: bytes, max_width: int = 1280, quality: int = 80) -> bytes:
    """Resize and compress image to optimized WebP format."""
    try:
        from PIL import Image
    except ImportError:
        return image_bytes

    try:
        im = Image.open(io.BytesIO(image_bytes))
        w, h = im.size
        if w > max_width:
            new_h = int(h * (max_width / w))
            im = im.resize((max_width, new_h), Image.Resampling.LANCZOS)

        out_buf = io.BytesIO()
        im.save(out_buf, format="WEBP", quality=quality, optimize=True)
        return out_buf.getvalue()
    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        return image_bytes


# NOTE: there is deliberately no image-understanding path here. The daemon runs
# a text-only GGUF via engine.LlamaEngine with no chat_format and no mmproj
# projector, so an OpenAI-style {"type": "image_url"} content array cannot be
# served -- a previous query_vision_model() helper that posted one was dead code
# that always failed. Khepri does "vision" via extract_text_ocr() plus the SLM
# reasoning over the extracted text. Adding a real VLM means shipping a mmproj
# GGUF and measuring it against the <2GB budget first; see README.
