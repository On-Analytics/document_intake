import shutil
import tempfile
import os
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import requests

from router import route_document
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
    batch_id: Optional[str] = None  # For grouping results in frontend

def _get_tenant_id_from_token(auth_header: Optional[str]) -> Optional[str]:
    """Extract tenant_id from JWT token via Supabase."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    try:
        token = auth_header.split(" ")[1]
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return None
        
        # Get user from token
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {token}",
        }
        resp = requests.get(f"{supabase_url}/auth/v1/user", headers=headers, timeout=5)
        if resp.status_code != 200:
            return None
        
        user_id = resp.json().get("id")
        if not user_id:
            return None
        
        # Get tenant_id from profiles
        profile_resp = requests.get(
            f"{supabase_url}/rest/v1/profiles",
            headers={**headers, "Content-Type": "application/json"},
            params={"id": f"eq.{user_id}", "select": "tenant_id"},
            timeout=5
        )
        if profile_resp.status_code == 200 and profile_resp.json():
            return profile_resp.json()[0].get("tenant_id")
        return None
    except Exception:
        return None


def _log_extraction_result(
    tenant_id: str,
    filename: str,
    schema_id: Optional[str],
    schema_name: Optional[str],
    field_count: int,
    processing_duration_ms: int,
    workflow: str,
    status: str = "completed",
    error_message: Optional[str] = None,
    batch_id: Optional[str] = None,
    user_token: Optional[str] = None,
) -> bool:
    """Log extraction result to Supabase extraction_results table."""
    try:
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            return False
        
        # Use user's token for RLS, fallback to anon key
        auth_token = user_token if user_token else supabase_key
        
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        
        payload = {
            "tenant_id": tenant_id,
            "filename": filename,
            "schema_id": schema_id if schema_id and schema_id not in ["inline-schema", "auto-schema"] else None,
            "schema_name": schema_name,
            "field_count": field_count,
            "processing_duration_ms": processing_duration_ms,
            "workflow": workflow,
            "status": status,
            "error_message": error_message,
            "batch_id": batch_id,
        }
        
        resp = requests.post(
            f"{supabase_url}/rest/v1/extraction_results",
            headers=headers,
            json=payload,
            timeout=5
        )
        return resp.status_code in [200, 201]
    except Exception:
        return False


@app.get("/")
async def root():
    return {"message": "Document Processor API is running"}

@app.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    schema_id: Optional[str] = Form(None),
    schema_content_from_request: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    batch_id: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """
    Upload a file, process it immediately, and return results.
    schema_content: Optional JSON string containing the full schema
    batch_id: Optional batch ID for grouping multiple files processed together
    """
    start_time = time.time()
    tenant_id = _get_tenant_id_from_token(authorization)
    
    # Extract user token for RLS-compliant inserts
    user_token = authorization.split(" ")[1] if authorization and authorization.startswith("Bearer ") else None
    
    # Generate batch_id if not provided
    if not batch_id:
        batch_id = str(uuid.uuid4())

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

        elif is_image:
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
        schema_content = None
        if schema_id:
            schema_content = get_schema_content(schema_id)
        
        # Fallback to schema_content_from_request if not found in Supabase
        if not schema_content and schema_content_from_request:
            try:
                schema_content = json.loads(schema_content_from_request)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {str(e)}")
        
        if not schema_content:
            raise HTTPException(status_code=400, detail="No schema provided. Please select a template or provide schema content.")

        # Write Schema to Temp File (for any extractors that might need file path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp_schema:
            json.dump(schema_content, tmp_schema)
            temp_schema_path = tmp_schema.name

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
            # Vision + Text Extraction with Parallel Prompt Generation
            from utils.prompt_generator import generate_system_prompt
            
            # Run vision_generate_markdown and generate_system_prompt in parallel
            # This reduces latency by ~1-3 seconds when prompt is not cached
            with ThreadPoolExecutor(max_workers=2) as executor:
                vision_future = executor.submit(
                    vision_generate_markdown,
                    document=router_doc,
                    metadata=doc_metadata,
                    schema_content=schema_content
                )
                prompt_future = executor.submit(
                    generate_system_prompt,
                    document_type=doc_type,
                    schema=schema_content
                )
                
                # Wait for both to complete
                vision_result = vision_future.result()
                system_prompt = prompt_future.result()
            
            markdown_content = vision_result.get("markdown_content")
            structure_hints = vision_result.get("structure_hints")

            # Extract Fields from Markdown (prompt already generated)
            extraction_result = extract_fields_balanced(
                document=router_doc,
                metadata=doc_metadata,
                schema_content=schema_content,
                document_type=doc_type,
                markdown_content=markdown_content,
                structure_hints=structure_hints,
                system_prompt=system_prompt
            )
        else:
            # Basic Text extraction
            extraction_result = extract_fields_basic(
                document=router_doc,
                metadata=doc_metadata,
                schema_content=schema_content,
                document_type=doc_type
            )

        # 6. Log extraction result to Supabase (backend logging)
        processing_duration_ms = int((time.time() - start_time) * 1000)
        field_count = len([v for v in extraction_result.values() if v is not None]) if extraction_result else 0
        schema_name = schema_content.get("document_type") or schema_content.get("name") if schema_content else None
        
        if tenant_id:
            _log_extraction_result(
                tenant_id=tenant_id,
                filename=file.filename,
                schema_id=schema_id,
                schema_name=schema_name,
                field_count=field_count,
                processing_duration_ms=processing_duration_ms,
                workflow=workflow_name,
                status="completed",
                batch_id=batch_id,
                user_token=user_token,
            )

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
            operational_metadata=op_metadata,
            batch_id=batch_id
        )

    except Exception as e:
        # Log failed extraction
        if tenant_id:
            processing_duration_ms = int((time.time() - start_time) * 1000)
            _log_extraction_result(
                tenant_id=tenant_id,
                filename=file.filename,
                schema_id=schema_id,
                schema_name=None,
                field_count=0,
                processing_duration_ms=processing_duration_ms,
                workflow=workflow_name if 'workflow_name' in dir() else "unknown",
                status="failed",
                error_message=str(e)[:500],  # Truncate long errors
                batch_id=batch_id,
                user_token=user_token,
            )
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
