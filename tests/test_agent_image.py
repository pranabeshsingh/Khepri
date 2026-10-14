import io
import pytest
from PIL import Image, ImageDraw
from pithon.agent.image_tools import extract_text_ocr, images_to_pdf, compress_image

def _create_sample_image(text: str = "Test Image Text") -> bytes:
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 35), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def test_extract_text_ocr():
    img_bytes = _create_sample_image("Pithon OCR Verification")
    text = extract_text_ocr(img_bytes)
    assert "Pithon" in text or "OCR" in text or "Verification" in text

def test_images_to_pdf():
    img1 = _create_sample_image("Page 1")
    img2 = _create_sample_image("Page 2")
    pdf_bytes = images_to_pdf([img1, img2])
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100

def test_compress_image():
    # Large image
    img = Image.new("RGB", (2000, 1000), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    compressed = compress_image(raw_bytes, max_width=800, quality=70)
    assert len(compressed) < len(raw_bytes)
    # Check it can be re-opened
    im_out = Image.open(io.BytesIO(compressed))
    assert im_out.width <= 800
