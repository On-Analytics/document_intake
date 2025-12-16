import shutil
import tempfile
import os
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import date
from contextlib import contextmanager

import pdfplumber

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import requests

from router import route_document
from langchain_community.document_loaders import PDFPlumberLoader, TextLoader, Docx2txtLoader
from langchain_core.documents import Document
from utils.supabase_schemas import get_schema_content, get_schema_details

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


class BatchProcessResponse(BaseModel):
    status: str
    batch_id: str
    total_files: int
    successful: int
    failed: int
    results: list[ProcessResponse]
    errors: list[Dict[str, Any]]


MAX_PAGES_PER_BATCH = 20
MAX_PAGES_PER_MONTH = 200


@contextmanager
def _stage_timer(timings_ms: Dict[str, int], name: str):
    start = time.time()
    try:
        yield
    finally:
        timings_ms[name] = int((time.time() - start) * 1000)


def _count_upload_pages(file: UploadFile) -> int:
    """Count logical pages for upload limiting.

    PDFs count as their number of pages. Non-PDF files count as 1.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix == ".pdf":
        try:
            # pdfplumber can read from file-like objects; ensure we rewind afterwards.
            with pdfplumber.open(file.file) as pdf:
                return len(pdf.pages)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read PDF page count for '{file.filename}': {str(e)}",
            )
        finally:
            try:
                file.file.seek(0)
            except Exception:
                pass

    # Non-PDF: treat as one logical page
    try:
        file.file.seek(0)
    except Exception:
        pass
    return 1


def _load_file_content(tmp_path: str, is_pdf: bool, is_txt: bool, is_docx: bool) -> tuple[str, int]:
    """Synchronous helper to load file content, to be run in a thread. Returns (text, page_count)."""
    print(f"[Loader] Starting load for {tmp_path} (pdf={is_pdf}, txt={is_txt}, docx={is_docx})")
    try:
        if is_pdf:
            loader = PDFPlumberLoader(tmp_path)
        elif is_txt:
            loader = TextLoader(tmp_path, encoding="utf-8")
        else:
            # docx
            loader = Docx2txtLoader(tmp_path)
        
        docs = loader.load()
        if not docs:
            print(f"[Loader] No documents returned for {tmp_path}")
            raise ValueError("Could not extract text from document")
        
        text = "\n".join([d.page_content for d in docs])
        page_count = len(docs)
        print(f"[Loader] Successfully loaded {len(text)} chars from {tmp_path} ({page_count} pages)")
        return text, page_count
    except Exception as e:
        print(f"[Loader] Error loading {tmp_path}: {e}")
        raise

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


def _get_user_id_from_token(auth_header: Optional[str]) -> Optional[str]:
    """Extract Supabase auth user id from JWT token via Supabase."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    try:
        token = auth_header.split(" ")[1]
        supabase_url = os.getenv("VITE_SUPABASE_URL")
        supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")

        if not supabase_url or not supabase_key:
            return None

        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {token}",
        }
        resp = requests.get(f"{supabase_url}/auth/v1/user", headers=headers, timeout=5)
        if resp.status_code != 200:
            return None

        user_id = resp.json().get("id")
        return user_id
    except Exception:
        return None


def _get_period_start_utc() -> date:
    """First day of the current month (UTC)."""
    today = date.today()
    return date(today.year, today.month, 1)


def _adjust_monthly_usage_pages(
    *,
    user_id: str,
    pages_delta: int,
    authorization: Optional[str],
    max_pages: int = MAX_PAGES_PER_MONTH,
) -> bool:
    """Adjust the user's monthly usage via Supabase RPC.

    Positive deltas are capped; negative deltas act as refunds.
    """
    supabase_url = os.getenv("VITE_SUPABASE_URL")
    supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        return True

    user_token = authorization.split(" ")[1] if authorization and authorization.startswith("Bearer ") else None
    auth_token = user_token if user_token else supabase_key

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "p_user_id": user_id,
        "p_period_start": _get_period_start_utc().isoformat(),
        "p_pages": pages_delta,
        "p_max_pages": max_pages,
    }

    resp = requests.post(
        f"{supabase_url}/rest/v1/rpc/increment_usage_pages",
        headers=headers,
        json=payload,
        timeout=5,
    )

    if resp.status_code != 200:
        # If quota infra isn't available yet, don't hard-fail processing.
        return True

    try:
        return bool(resp.json())
    except Exception:
        # Some PostgREST setups return "true"/"false" as text.
        return resp.text.strip().lower() == "true"


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
    print(f"[Process] START filename='{file.filename}' schema_id='{schema_id}' document_type='{document_type}' batch_id='{batch_id}'")

    raise HTTPException(
        status_code=410,
        detail="Single-file processing is deprecated. Use POST /process-batch instead.",
    )
    
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
    print(f"[Process] Temp file saved: {tmp_path}")

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
                print("[Process] Loading PDF via PDFPlumberLoader")
                loader = PDFPlumberLoader(tmp_path)
            elif is_txt:
                print("[Process] Loading TXT via TextLoader")
                loader = TextLoader(tmp_path, encoding="utf-8")
            else:  # .docx
                print("[Process] Loading DOCX via Docx2txtLoader")
                loader = Docx2txtLoader(tmp_path)

            load_start = time.time()
            # Loader is synchronous and can block; run it in a thread so we don't
            # stall the event loop under concurrency.
            docs = await asyncio.to_thread(loader.load)
            print(f"[Process] Document loaded in {int((time.time() - load_start) * 1000)}ms (pages={len(docs) if docs else 0})")

            if not docs:
                raise HTTPException(status_code=400, detail="Could not extract text from document")

            # Combine pages for routing analysis
            full_text = "\n".join([d.page_content for d in docs])
            # Create a LangChain document for the router
            router_doc = Document(page_content=full_text, metadata={"source": file.filename})

            # 3. Determine Workflow
            print("[Process] Routing document (LLM may be called if cache miss)")
            route_start = time.time()
            route = route_document(router_doc, schema_id=schema_id)
            print(f"[Process] Routing complete in {int((time.time() - route_start) * 1000)}ms -> {route}")
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
        print(f"[Process] Loading schema content (schema_id='{schema_id}', request_schema_provided={bool(schema_content_from_request)})")
        schema_start = time.time()
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

        print(f"[Process] Schema loaded in {int((time.time() - schema_start) * 1000)}ms (fields={len(schema_content.get('fields', [])) if isinstance(schema_content, dict) else 'n/a'})")

        # Write Schema to Temp File (for any extractors that might need file path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp_schema:
            json.dump(schema_content, tmp_schema)
            temp_schema_path = tmp_schema.name

        # 5. Run Extraction Workflow
        from core_pipeline import DocumentMetadata
        from processors.extract_fields_basic import extract_fields_basic
        from processors.extract_fields_balanced import extract_fields_balanced
        from processors.vision_generate_markdown import vision_generate_markdown

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
            print(f"[Process] Running workflow='balanced' doc_type='{doc_type}' (vision + extraction)")
            # Vision + Text Extraction with Parallel Prompt Generation
            from utils.prompt_generator import generate_system_prompt
            
            # Run vision_generate_markdown and generate_system_prompt in parallel.
            # Both are synchronous and can block; run them in threads so we don't
            # stall the event loop.
            vision_wait_start = time.time()
            vision_result, system_prompt = await asyncio.gather(
                asyncio.to_thread(
                    vision_generate_markdown,
                    document=router_doc,
                    metadata=doc_metadata,
                    schema_content=schema_content,
                ),
                asyncio.to_thread(
                    generate_system_prompt,
                    document_type=doc_type,
                    schema=schema_content,
                ),
            )
            print(f"[Process] vision_generate_markdown completed in {int((time.time() - vision_wait_start) * 1000)}ms")
            print(f"[Process] generate_system_prompt completed in 0ms")
            
            markdown_content = vision_result.get("markdown_content")
            structure_hints = vision_result.get("structure_hints")

            # Extract Fields from Markdown (prompt already generated)
            extract_start = time.time()
            extraction_result = extract_fields_balanced(
                schema_content=schema_content,
                system_prompt=system_prompt,
                markdown_content=markdown_content,
                document_type=doc_type,
                structure_hints=structure_hints,
            )
            print(f"[Process] extract_fields_balanced completed in {int((time.time() - extract_start) * 1000)}ms")
        else:
            # Basic Text extraction
            print(f"[Process] Running workflow='basic' doc_type='{doc_type}' (text extraction)")
            extract_start = time.time()
            extraction_result = extract_fields_basic(
                document=router_doc,
                metadata=doc_metadata,
                schema_content=schema_content,
                document_type=doc_type
            )
            print(f"[Process] extract_fields_basic completed in {int((time.time() - extract_start) * 1000)}ms")

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
        # Add source filename to extraction results for traceability
        extraction_result["source_file"] = file.filename

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
        print(f"[Process] END filename='{file.filename}' duration_ms={int((time.time() - start_time) * 1000)}")

# Semaphore for batch processing concurrency control
BATCH_SEMAPHORE = asyncio.Semaphore(5)


# Shared context for batch processing (leader-follower pattern)
class BatchSharedContext:
    """Pre-computed context from leader document, shared with followers."""
    def __init__(
        self,
        doc_type: str,
        workflow_name: str,
        schema_content: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ):
        self.doc_type = doc_type
        self.workflow_name = workflow_name
        self.schema_content = schema_content
        self.system_prompt = system_prompt


async def _process_single_file(
    file: UploadFile,
    batch_id: str,
    authorization: Optional[str],
    shared_context: Optional[BatchSharedContext] = None,
    schema_id: Optional[str] = None,
    schema_content_from_request: Optional[str] = None,
    document_type: Optional[str] = None,
    is_leader: bool = False,
) -> tuple[Optional[ProcessResponse], Optional[Dict[str, Any]], Optional[BatchSharedContext]]:
    """
    Process a single file with semaphore control. Returns (response, error, shared_context).
    
    Leader document (is_leader=True): Determines doc_type, generates system_prompt, returns shared_context.
    Follower documents: Use pre-computed shared_context from leader.
    """
    semaphore_wait_start = time.time()
    await BATCH_SEMAPHORE.acquire()
    semaphore_wait_ms = int((time.time() - semaphore_wait_start) * 1000)
    try:
        start_time = time.time()
        timings_ms: Dict[str, int] = {"semaphore_wait_ms": semaphore_wait_ms}
        request_id = f"{batch_id}:{file.filename}"
        tenant_id = _get_tenant_id_from_token(authorization)
        user_token = authorization.split(" ")[1] if authorization and authorization.startswith("Bearer ") else None
        
        suffix = Path(file.filename).suffix
        tmp_path = None
        workflow_name = "unknown"
        
        try:
            # Save to temp file
            with _stage_timer(timings_ms, "upload_read_and_temp_write"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await file.read()
                    tmp.write(content)
                    tmp_path = tmp.name
            
            # Check file extension
            suffix_lower = suffix.lower()
            is_pdf = suffix_lower == ".pdf"
            is_txt = suffix_lower == ".txt"
            is_docx = suffix_lower == ".docx"
            is_image = suffix_lower in [".png", ".jpg", ".jpeg"]
            
            if is_pdf or is_txt or is_docx:
                try:
                    with _stage_timer(timings_ms, "loader_text_extraction"):
                        full_text, page_count = await asyncio.to_thread(
                            _load_file_content,
                            tmp_path,
                            is_pdf,
                            is_txt,
                            is_docx,
                        )
                except ValueError as e:
                     return None, {"filename": file.filename, "error": str(e)}, None
                except Exception as e:
                     return None, {"filename": file.filename, "error": f"Failed to load document: {str(e)}"}, None

                router_doc = Document(page_content=full_text, metadata={"source": file.filename})
            
            elif is_image:
                router_doc = Document(page_content="", metadata={"source": file.filename})
                # images don't need text loading for router yet (vision step handles it)
                page_count = 1
            else:
                return None, {"filename": file.filename, "error": f"Unsupported file type: {suffix}"}, None
            
            # Use shared context from leader, or compute for leader
            if shared_context:
                # Follower: use pre-computed values
                doc_type = shared_context.doc_type
                workflow_name = shared_context.workflow_name
                schema_content = shared_context.schema_content
                system_prompt = shared_context.system_prompt
                
                # Image files MUST use balanced (vision) workflow regardless of shared context
                if is_image:
                    workflow_name = "balanced"

                # .txt files MUST use basic workflow regardless of shared context
                # (mirrors router.py behavior which forces basic for .txt sources)
                if is_txt:
                    workflow_name = "basic"

            else:
                # Leader or standalone: compute values
                if is_image:
                    doc_type = "generic"
                    workflow_name = "balanced"
                else:
                    with _stage_timer(timings_ms, "router"):
                        route = route_document(router_doc, schema_id=schema_id)
                    doc_type = route.get("document_type", "generic")
                    workflow_name = route.get("workflow", "basic")

                # .txt files should always use basic workflow
                if is_txt:
                    workflow_name = "basic"
                
                # Override with explicit document_type if provided
                if document_type:
                    doc_type = document_type
                
                # Load schema
                schema_content = None
                if schema_id:
                    with _stage_timer(timings_ms, "schema_fetch"):
                        schema_content = get_schema_content(schema_id)
                
                if not schema_content and schema_content_from_request:
                    try:
                        schema_content = json.loads(schema_content_from_request)
                    except json.JSONDecodeError as e:
                        return None, {"filename": file.filename, "error": f"Invalid schema JSON: {str(e)}"}, None
                
                if not schema_content:
                    return None, {"filename": file.filename, "error": "No schema provided"}, None
                
                # Generate system prompt for leader (followers will reuse for both workflows)
                system_prompt = None
                if is_leader:
                    from utils.prompt_generator import generate_system_prompt
                    print(f"[Batch Leader] Generating system prompt for doc_type='{doc_type}' (workflow={workflow_name})")
                    with _stage_timer(timings_ms, "prompt_generate"):
                        system_prompt = generate_system_prompt(document_type=doc_type, schema=schema_content)
            
            # Run extraction
            from core_pipeline import DocumentMetadata
            from processors.extract_fields_basic import extract_fields_basic
            from processors.extract_fields_balanced import extract_fields_balanced
            from processors.vision_generate_markdown import vision_generate_markdown
            
            doc_metadata = DocumentMetadata(
                document_number="api-batch",
                filename=file.filename,
                file_size=os.path.getsize(tmp_path),
                file_path=tmp_path,
                processed_date=None
            )
            
            extraction_result = {}
            
            if workflow_name == "balanced":
                # Vision processing (unique per document)
                with _stage_timer(timings_ms, "vision_generate_markdown"):
                    vision_result = await asyncio.to_thread(
                        vision_generate_markdown,
                        document=router_doc,
                        metadata=doc_metadata,
                        schema_content=schema_content,
                    )
                vision_timings_ms = None
                if isinstance(vision_result, dict):
                    vision_timings_ms = vision_result.get("vision_timings_ms")
                
                # Use pre-computed prompt or generate if not available
                if not system_prompt:
                    from utils.prompt_generator import generate_system_prompt
                    with _stage_timer(timings_ms, "prompt_generate"):
                        system_prompt = generate_system_prompt(document_type=doc_type, schema=schema_content)
                
                markdown_content = vision_result.get("markdown_content")
                structure_hints = vision_result.get("structure_hints")
                
                with _stage_timer(timings_ms, "extract_fields_balanced"):
                    extraction_result = await asyncio.to_thread(
                        extract_fields_balanced,
                        schema_content=schema_content,
                        system_prompt=system_prompt,
                        markdown_content=markdown_content,
                        document_type=doc_type,
                        structure_hints=structure_hints,
                    )
            else:
                # Use pre-computed prompt or generate if not available
                if not system_prompt:
                    from utils.prompt_generator import generate_system_prompt
                    with _stage_timer(timings_ms, "prompt_generate"):
                        system_prompt = generate_system_prompt(document_type=doc_type, schema=schema_content)
                
                with _stage_timer(timings_ms, "extract_fields_basic"):
                    extraction_result = await asyncio.to_thread(
                        extract_fields_basic,
                        document=router_doc,
                        metadata=doc_metadata,
                        schema_content=schema_content,
                        document_type=doc_type,
                        system_prompt=system_prompt,
                    )
            
            # Build shared context for leader to return
            result_shared_context = None
            if is_leader:
                result_shared_context = BatchSharedContext(
                    doc_type=doc_type,
                    workflow_name=workflow_name,
                    schema_content=schema_content,
                    system_prompt=system_prompt,
                )
            
            # Log result
            processing_duration_ms = int((time.time() - start_time) * 1000)
            field_count = len([v for v in extraction_result.values() if v is not None]) if extraction_result else 0
            schema_name = schema_content.get("document_type") or schema_content.get("name") if schema_content else None
            
            if tenant_id:
                with _stage_timer(timings_ms, "supabase_log_result"):
                    await asyncio.to_thread(
                        _log_extraction_result,
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
            
            extraction_result["source_file"] = file.filename
            
            op_metadata = {
                "page_count": page_count,
                "doc_type": doc_type,
                "workflow": workflow_name,
                "source": "api_batch",
                "request_id": request_id,
                "timings_ms": timings_ms,
            }

            if workflow_name == "balanced" and 'vision_timings_ms' in locals() and vision_timings_ms:
                op_metadata["vision_timings_ms"] = vision_timings_ms

            timings_ms["total_file_ms"] = int((time.time() - start_time) * 1000)
            print(
                f"[BatchFile] END request_id='{request_id}' total_ms={timings_ms['total_file_ms']} timings_ms={timings_ms}"
            )
            
            return ProcessResponse(
                status="success",
                document_id="no-persistence",
                results=extraction_result,
                operational_metadata=op_metadata,
                batch_id=batch_id
            ), None, result_shared_context
            
        except Exception as e:
            print(f"[Error] Processing {file.filename} failed: {e}")
            import traceback
            traceback.print_exc()
            if tenant_id:
                processing_duration_ms = int((time.time() - start_time) * 1000)
                _log_extraction_result(
                    tenant_id=tenant_id,
                    filename=file.filename,
                    schema_id=schema_id,
                    schema_name=None,
                    field_count=0,
                    processing_duration_ms=processing_duration_ms,
                    workflow=workflow_name,
                    status="failed",
                    error_message=str(e)[:500],
                    batch_id=batch_id,
                    user_token=user_token,
                )
            return None, {"filename": file.filename, "error": str(e)}, None
        
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    finally:
        BATCH_SEMAPHORE.release()


@app.post("/process-batch", response_model=BatchProcessResponse)
async def process_batch(
    files: list[UploadFile] = File(...),
    schema_id: Optional[str] = Form(None),
    schema_content_from_request: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """
    Process multiple files concurrently (up to 5 at a time).
    Uses leader-follower pattern: first file determines doc_type and generates system_prompt,
    then remaining files process in parallel using the pre-computed values.
    """
    batch_id = str(uuid.uuid4())
    
    successful_results = []
    errors = []
    
    if not files:
        return BatchProcessResponse(
            status="failed",
            batch_id=batch_id,
            total_files=0,
            successful=0,
            failed=0,
            results=[],
            errors=[{"filename": "N/A", "error": "No files provided"}],
        )

    # Enforce per-batch total page limit before processing anything.
    total_pages = 0
    per_file_pages: list[Dict[str, Any]] = []
    pages_by_filename: Dict[str, int] = {}
    for f in files:
        pages = _count_upload_pages(f)
        per_file_pages.append({"filename": f.filename, "pages": pages})
        pages_by_filename[f.filename] = pages
        total_pages += pages

    if total_pages > MAX_PAGES_PER_BATCH:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Batch exceeds maximum pages. "
                f"Total pages={total_pages}, max={MAX_PAGES_PER_BATCH}. "
                f"Per-file: {per_file_pages}"
            ),
        )

    # Monthly quota (per user_id): reserve pages upfront to prevent concurrent overage.
    user_id = _get_user_id_from_token(authorization)
    reserved_pages = 0
    if user_id:
        ok = _adjust_monthly_usage_pages(
            user_id=user_id,
            pages_delta=total_pages,
            authorization=authorization,
            max_pages=MAX_PAGES_PER_MONTH,
        )
        if not ok:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly quota exceeded. Max {MAX_PAGES_PER_MONTH} pages/month.",
            )
        reserved_pages = total_pages

    try:
        # Optimistic Parallelism: If schema_id is provided, we can skip the Leader step
        # because we know the doc_type and can fetch the schema/prompt upfront.
        optimistic_context = None
        if schema_id:
            print(f"[Batch] Optimistic Mode: Checking schema {schema_id}")
            schema_details = get_schema_details(schema_id)
            if schema_details and schema_details.get("content"):
                
                # Determine doc_type (prefer explicit > schema > generic)
                opt_doc_type = document_type or schema_details.get("document_type") or "generic"
                opt_schema_content = schema_details.get("content")
                
                # Generate system prompt once
                from utils.prompt_generator import generate_system_prompt
                opt_system_prompt = generate_system_prompt(document_type=opt_doc_type, schema=opt_schema_content)
                
                optimistic_context = BatchSharedContext(
                    doc_type=opt_doc_type,
                    # User requested default to 'balanced' (vision) for safety with scanned docs
                    workflow_name="balanced", 
                    schema_content=opt_schema_content,
                    system_prompt=opt_system_prompt
                )
                print(f"[Batch] Optimistic Mode: ACTIVATED for {len(files)} files (type='{opt_doc_type}')")

        if optimistic_context:
            # OPTIMISTIC PATH: Launch all files in parallel immediately
            follower_tasks = [
                _process_single_file(
                    file=f,
                    batch_id=batch_id,
                    authorization=authorization,
                    shared_context=optimistic_context,
                    schema_id=schema_id,
                    is_leader=False
                )
                for f in files
            ]
            
            results = await asyncio.gather(*follower_tasks)
            for response, error, _ in results:
                if response:
                    successful_results.append(response)
                if error:
                    errors.append(error)

        else:
            # FALLBACK PATH (Leader-Follower): Process first file to discovery type
            # Step 1: Process LEADER (first file) to determine doc_type and generate system_prompt
            leader_idx = 0
            for idx, f in enumerate(files):
                if not f.filename.lower().endswith(".txt"):
                    leader_idx = idx
                    break

            leader_file = files[leader_idx]
            print(f"[Batch] Processing leader file: {leader_file.filename}")
            
            leader_response, leader_error, shared_context = await _process_single_file(
                file=leader_file,
                batch_id=batch_id,
                authorization=authorization,
                shared_context=None,  # Leader computes its own
                schema_id=schema_id,
                schema_content_from_request=schema_content_from_request,
                document_type=document_type,
                is_leader=True,
            )
            
            if leader_response:
                successful_results.append(leader_response)
            if leader_error:
                errors.append(leader_error)
            
            # Step 2: Process FOLLOWERS in parallel using shared context from leader
            follower_files = [f for i, f in enumerate(files) if i != leader_idx]

            if len(follower_files) > 0 and shared_context:
                print(f"[Batch] Processing {len(follower_files)} follower files with shared context (doc_type='{shared_context.doc_type}')")
                
                follower_tasks = [
                    _process_single_file(
                        file=f,
                        batch_id=batch_id,
                        authorization=authorization,
                        shared_context=shared_context,  # Reuse leader's computed values
                        schema_id=schema_id,
                        is_leader=False,
                    )
                    for f in follower_files
                ]
                
                # Process followers concurrently with semaphore limiting to 5
                follower_results = await asyncio.gather(*follower_tasks)
                
                for response, error, _ in follower_results:
                    if response:
                        successful_results.append(response)
                    if error:
                        errors.append(error)
        
            elif len(follower_files) > 0 and not shared_context:
                # Leader failed to produce shared context, process followers independently
                print(f"[Batch] Leader failed, processing {len(follower_files)} followers independently")
                
                follower_tasks = [
                    _process_single_file(
                        file=f,
                        batch_id=batch_id,
                        authorization=authorization,
                        shared_context=None,
                        schema_id=schema_id,
                        schema_content_from_request=schema_content_from_request,
                        document_type=document_type,
                        is_leader=False,
                    )
                    for f in follower_files
                ]
                
                # Process followers concurrently with semaphore limiting to 5
                follower_results = await asyncio.gather(*follower_tasks)
                
                for response, error, _ in follower_results:
                    if response:
                        successful_results.append(response)
                    if error:
                        errors.append(error)

        return BatchProcessResponse(
            status="completed" if not errors else "partial" if successful_results else "failed",
            batch_id=batch_id,
            total_files=len(files),
            successful=len(successful_results),
            failed=len(errors),
            results=successful_results,
            errors=errors,
        )
    finally:
        # Refund reserved pages for non-successful files so only successful processing is charged.
        if user_id and reserved_pages:
            successful_filenames = {
                r.results.get("source_file")
                for r in successful_results
                if isinstance(r.results, dict)
            }
            successful_pages = sum(
                pages_by_filename.get(name, 1)
                for name in successful_filenames
                if name
            )
            refund_pages = max(reserved_pages - successful_pages, 0)
            if refund_pages:
                _adjust_monthly_usage_pages(
                    user_id=user_id,
                    pages_delta=-refund_pages,
                    authorization=authorization,
                    max_pages=MAX_PAGES_PER_MONTH,
                )


@app.delete("/schemas/{schema_id}")
async def delete_schema_endpoint(
    schema_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Delete a schema and its corresponding prompt cache entry.
    Requires authentication.
    """
    user_id = _get_user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    from utils.supabase_schemas import get_schema_details, delete_schema
    from utils.prompt_generator import calculate_prompt_cache_key, delete_prompt_from_cache
    
    # 1. Fetch schema details to calculate cache key
    schema_details = get_schema_details(schema_id)
    if not schema_details:
        raise HTTPException(status_code=404, detail="Schema not found")
        
    schema_content = schema_details.get("content")
    document_type = schema_details.get("document_type")
    
    # 2. Calculate cache key if content and doc_type exist
    cache_key = None
    if schema_content and document_type:
        # Needs to match the logic in generate_system_prompt
        # If content relies on "document_type" from the schema JSON itself, prioritize that
        # But supabase_schemas.py seems to return the row's document_type column too
        
        # Ensure schema_content is a dict
        if isinstance(schema_content, str):
            try:
                schema_content = json.loads(schema_content)
            except:
                pass
                
        if isinstance(schema_content, dict):
             cache_key, _ = calculate_prompt_cache_key(document_type, schema_content)
    
    # 3. Delete Schema
    deleted = delete_schema(schema_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete schema")
        
    # 4. Delete Prompt Cache (if key was calculated)
    prompt_deleted = False
    if cache_key:
        prompt_deleted = delete_prompt_from_cache(cache_key)
        
    return {
        "status": "success", 
        "schema_id": schema_id, 
        "prompt_cache_deleted": prompt_deleted
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
