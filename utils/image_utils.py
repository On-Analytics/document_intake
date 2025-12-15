import base64
import io
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
            for page in pdf.pages:
                # Convert page to image with reasonable resolution
                # resolution=300 is good for OCR/Vision
                im = page.to_image(resolution=200).original
                
                # Convert PIL Image to base64
                buffered = io.BytesIO()
                im.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                images_base64.append(img_str)
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        return []

    return images_base64
