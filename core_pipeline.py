from pathlib import Path
from typing import List, Optional, Iterator
from datetime import date

from dotenv import load_dotenv
from langchain_core.documents import Document
from pydantic import BaseModel
from langchain_community.document_loaders import TextLoader, PDFPlumberLoader, Docx2txtLoader


load_dotenv()

BASE_DIR = Path(__file__).parent
DOCUMENTS_DIR = BASE_DIR / "documents"


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
        if ch == "�" and last_char == "�":
            continue
        result_chars.append(ch)
        last_char = ch

    return "".join(result_chars)


def load_documents(documents_dir: Optional[Path] = None) -> Iterator[Document]:
    """Yield documents one by one from the directory (Lazy Loading)."""
    base_dir = documents_dir or DOCUMENTS_DIR
    
    if not base_dir.exists() or not base_dir.is_dir():
        return

    for file_path in sorted(base_dir.iterdir()):
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()

        try:
            if suffix == ".txt":
                loader = TextLoader(str(file_path), encoding="utf-8")
            elif suffix == ".pdf":
                loader = PDFPlumberLoader(str(file_path))
            elif suffix == ".docx":
                loader = Docx2txtLoader(str(file_path))
            else:
                continue

            loaded_docs = loader.load()

            for d in loaded_docs:
                d.metadata = {**d.metadata, "source": str(file_path.name)}
                yield d
                
        except Exception:
            continue


def create_document_metadata(doc: Document, index: int) -> DocumentMetadata:
    """Create metadata for a single document."""
    source = doc.metadata.get("source") or "unknown"
    path = DOCUMENTS_DIR / source

    try:
        size = path.stat().st_size if path.exists() else 0
    except OSError:
        size = 0

    return DocumentMetadata(
        document_number=str(index),
        filename=source,
        file_size=size,
        file_path=str(path),
        processed_date=date.today(),
    )


def build_document_metadata(documents: List[Document]) -> List[DocumentMetadata]:
    """Deprecated: Use create_document_metadata in a loop instead."""
    return [create_document_metadata(doc, idx) for idx, doc in enumerate(documents, start=1)]
