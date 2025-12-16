import base64
import io
import os
from typing import List
import pdfplumber
from PIL import Image

def convert_pdf_to_images(pdf_path: str) -> List[str]:
    """
    Convert PDF pages to base64 encoded JPEG images.
    """
    images_base64 = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            max_pages = int(os.getenv("VISION_MAX_PAGES", "2"))
            resolution = int(os.getenv("VISION_PDF_RESOLUTION", "150"))
            jpeg_quality = int(os.getenv("VISION_JPEG_QUALITY", "70"))

            pages = pdf.pages[:max_pages] if max_pages > 0 else pdf.pages
            for page in pages:
                # Convert page to image with reasonable resolution
                # resolution=300 is good for OCR/Vision
                im = page.to_image(resolution=resolution).original
                
                # Convert PIL Image to base64
                buffered = io.BytesIO()
                im.save(buffered, format="JPEG", quality=jpeg_quality, optimize=True)
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                images_base64.append(img_str)
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        return []

    return images_base64
