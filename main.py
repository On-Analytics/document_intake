import shutil
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json

from router import route_document
from templates_registry import TEMPLATES, TemplateConfig
from template_metadata import get_template_metadata, upsert_template_metadata
from supabase_sync import update_schema_document_type
from langchain_community.document_loaders import PDFPlumberLoader, TextLoader, Docx2txtLoader
from langchain_core.documents import Document
from utils.supabase_schemas import get_schema_content

# Initialize FastAPI app
app = FastAPI(title="Document Processor API", version="1.0.0")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Response Models
class ProcessResponse(BaseModel):
    status: str
    document_id: str
    results: Dict[str, Any]
    operational_metadata: Dict[str, Any]

@app.get("/")
async def root():
    return {"message": "Document Processor API is running"}

@app.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    schema_id: Optional[str] = Form(None),
    schema_content_from_request: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
):
    """
    Upload a file, process it immediately, and return results.
    schema_content: Optional JSON string containing the full schema
    """
    print(f"Processing {file.filename}")

    # 1. Save to Temp File (Required for PDF loaders usually)
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    temp_schema_path = None # Track temp schema file cleanup

    try:
        # 2. Load Document for Router
        # Check file extension
        suffix_lower = suffix.lower()
        is_pdf = suffix_lower == ".pdf"
        is_txt = suffix_lower == ".txt"
        is_docx = suffix_lower == ".docx"
        is_image = suffix_lower in [".png", ".jpg", ".jpeg"]

        if is_pdf or is_txt or is_docx:
            # Use appropriate loader based on file type
            if is_pdf:
                loader = PDFPlumberLoader(tmp_path)
            elif is_txt:
                loader = TextLoader(tmp_path, encoding="utf-8")
            else:  # .docx
                loader = Docx2txtLoader(tmp_path)

            docs = loader.load()

            if not docs:
                raise HTTPException(status_code=400, detail="Could not extract text from document")

            # Combine pages for routing analysis
            full_text = "\n".join([d.page_content for d in docs])
            # Create a LangChain document for the router
            router_doc = Document(page_content=full_text, metadata={"source": file.filename})

            # 3. Determine Workflow
            route = route_document(router_doc)
            doc_type = route.get("document_type", "generic")
            workflow_name = route.get("workflow", "basic")

            print(f"Router decided: Type={doc_type}, Workflow={workflow_name}")

        elif is_image:
            print(f"Image detected: {file.filename}. Skipping text extraction and forcing Balanced workflow.")
            # For images, we can't easily extract text for the router without OCR.
            # So we default to the 'balanced' workflow (which uses Vision) and 'generic' type.
            router_doc = Document(page_content="", metadata={"source": file.filename})
            doc_type = "generic"
            workflow_name = "balanced"

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

        # 3b. If the client/template explicitly provided a document_type
        # (e.g., from the Supabase schemas table), let that override the
        # router's inferred type. This makes the schemas table the primary
        # source of truth for template document_type.
        if document_type:
            doc_type = document_type

        # 4. Load Schema Content
        # Replace schema loading logic:
        if schema_id:
            schema_content = get_schema_content(schema_id)
            if not schema_content and schema_content_from_request:
                try:
                    schema_content = json.loads(schema_content_from_request)
                except json.JSONDecodeError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {str(e)}")
        else:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_content = json.load(f)

        # Write Schema to Temp File
        # Extractors expect a file path, so we dump the JSON content to a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp_schema:
            json.dump(schema_content, tmp_schema)
            temp_schema_path = tmp_schema.name
            schema_path = Path(temp_schema_path)

        # 5. Run Extraction Workflow
        from core_pipeline import DocumentMetadata
        from extractors.extract_fields_basic import extract_fields_basic
        from extractors.extract_fields_balanced import extract_fields_balanced
        from extractors.vision_generate_markdown import vision_generate_markdown

        # Create metadata object required by extractors
        doc_metadata = DocumentMetadata(
            document_number="api-request",
            filename=file.filename,
            file_size=os.path.getsize(tmp_path),
            file_path=tmp_path,
            processed_date=None
        )

        extraction_result = {}

        if workflow_name == "balanced":
        # Vision + Text Extraction
            print(f"Running Balanced extraction (Vision + Text) for {file.filename}")

                # Step 1: Generate Markdown via Vision
            vision_result = vision_generate_markdown(
                document=router_doc,
                metadata=doc_metadata,
                schema_content=schema_content
            )
            markdown_content = vision_result.get("markdown_content")
            structure_hints = vision_result.get("structure_hints")

            # Step 2: Extract Fields from Markdown
            extraction_result = extract_fields_balanced(
                document=router_doc,
                metadata=doc_metadata,
                schema_content=schema_content,
                document_type=doc_type,
                markdown_content=markdown_content,
                structure_hints=structure_hints
            )
        else:
            # Basic Text extraction
            print(f"Running Basic extraction for {file.filename}")
            extraction_result = extract_fields_basic(
                document=router_doc,
                metadata=doc_metadata,
                schema_content=schema_content,
                document_type=doc_type
            )

        # 6. Optional: Log this run for observability (does not affect behavior)
        try:
            # Use schema_id when provided; otherwise note whether schema was auto-selected or inline
            effective_schema_id = schema_id
            if not effective_schema_id:
                if schema_content_from_request:
                    effective_schema_id = "inline-schema"
                else:
                    effective_schema_id = "auto-schema"

            log_run(
                content=router_doc.page_content or "",
                document_type=doc_type,
                schema_id=effective_schema_id,
                workflow=workflow_name,
                filename=file.filename,
            )
        except Exception:
            # Never let logging break the main flow
            pass

        # 7. Build Response
        # For non-PDF types, we treat the document as a single logical page for now.
        op_metadata = {
            "page_count": len(docs) if is_pdf else 1,
            "doc_type": doc_type,
            "workflow": workflow_name,
            "source": "api_upload"
        }

        return ProcessResponse(
            status="success",
            document_id="no-persistence",
            results=extraction_result,
            operational_metadata=op_metadata
        )

    except Exception as e:
        print(f"Processing Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        # Cleanup temp schema file
        if temp_schema_path and os.path.exists(temp_schema_path):
            os.unlink(temp_schema_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
