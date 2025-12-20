from typing import List, Optional
from datetime import date

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class DocumentMetadata(BaseModel):
    document_number: str
    filename: str
    file_size: int
    file_path: str
    processed_date: Optional[date] = None


def _normalize_garbage_characters(text: str) -> str:
    if not text:
        return text

    result_chars: List[str] = []
    last_char: Optional[str] = None
    for ch in text:
        if ch == "\ufffd" and last_char == "\ufffd":
            continue
        result_chars.append(ch)
        last_char = ch

    return "".join(result_chars)
