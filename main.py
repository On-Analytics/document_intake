import tempfile
import os
import time
import uuid
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import date
from contextlib import contextmanager

import pdfplumber

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
import requests

from processors.document_classifier import classify_document_type
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


class DeferredPersistenceRecord(BaseModel):
    tenant_id: str
    filename: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    status: str
    document_id: Optional[str] = None
    schema_id: Optional[str] = None
    schema_name: Optional[str] = None
    field_count: int = 0
    processing_duration_ms: int = 0
    workflow: str = "unknown"
    batch_id: Optional[str] = None
    user_token: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


MAX_PAGES_PER_BATCH = 20
MAX_PAGES_PER_MONTH = 200


class _TTLCache:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time() + self.ttl_seconds, value)


_USER_BY_TOKEN_CACHE = _TTLCache(ttl_seconds=300)
_TENANT_BY_USER_CACHE = _TTLCache(ttl_seconds=900)
_SCHEMA_DETAILS_CACHE = _TTLCache(ttl_seconds=900)
_SYSTEM_PROMPT_CACHE = _TTLCache(ttl_seconds=3600)


def _determine_workflow(file_extension: str, content_length: int) -> str:
    """Determine workflow based on file characteristics.
    
    Args:
        file_extension: File extension (e.g., '.txt', '.pdf')
        content_length: Length of document content
        
    Returns:
        'basic' for .txt files or short content, 'balanced' otherwise
    """
    if file_extension.lower() == ".txt" or content_length < 50:
        return "basic"
    return "balanced"


def _should_use_optimistic_path(schema_details: Optional[Dict[str, Any]], document_type: Optional[str]) -> bool:
    """Check if we can use optimistic parallelism.
    
    Optimistic path requires knowing the document_type upfront (from schema or explicit parameter).
    This indicates the schema has been used before and has cached prompts.
    
    Args:
        schema_details: Schema details from database
        document_type: Explicitly provided document type
        
    Returns:
        True if document_type is known, False otherwise (will use leader-follower)
    """
    if document_type:
        return True
    if schema_details and schema_details.get("document_type"):
        return True
    return False



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
            raise ValueError("Could not extract text from document")
        
        text = "\n".join([d.page_content for d in docs])
        page_count = len(docs)
        return text, page_count
    except Exception as e:
        raise



def _get_user_id_from_token_cached(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    cached = _USER_BY_TOKEN_CACHE.get(auth_header)
    if isinstance(cached, dict):
        return cached.get("id")

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

        payload = resp.json() if resp.content else {}
        if isinstance(payload, dict) and payload.get("id"):
            _USER_BY_TOKEN_CACHE.set(auth_header, payload)
            return payload.get("id")
        return None
    except Exception:
        return None


def _get_tenant_id_for_user_cached(*, user_id: Optional[str], auth_header: Optional[str]) -> Optional[str]:
    if not user_id:
        return None

    cached = _TENANT_BY_USER_CACHE.get(user_id)
    if isinstance(cached, str):
        return cached

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

        profile_resp = requests.get(
            f"{supabase_url}/rest/v1/profiles",
            headers={**headers, "Content-Type": "application/json"},
            params={"id": f"eq.{user_id}", "select": "tenant_id"},
            timeout=5,
        )
        if profile_resp.status_code == 200 and profile_resp.json():
            tenant_id = profile_resp.json()[0].get("tenant_id")
            if tenant_id:
                _TENANT_BY_USER_CACHE.set(user_id, tenant_id)
            return tenant_id
        return None
    except Exception:
        return None


def _get_auth_context(auth_header: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    user_id = _get_user_id_from_token_cached(auth_header)
    tenant_id = _get_tenant_id_for_user_cached(user_id=user_id, auth_header=auth_header)
    user_token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else None
    return user_id, tenant_id, user_token


def _get_schema_details_cached(schema_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    cached = _SCHEMA_DETAILS_CACHE.get(schema_id)
    if isinstance(cached, dict):
        return cached
    details = get_schema_details(schema_id, tenant_id)
    if isinstance(details, dict):
        _SCHEMA_DETAILS_CACHE.set(schema_id, details)
    return details


def _calculate_system_prompt_cache_key(
    *,
    schema_id: Optional[str],
    document_type: str,
    schema: Any,
) -> str:
    try:
        schema_json = json.dumps(schema, sort_keys=True, ensure_ascii=False)
    except Exception:
        schema_json = str(schema)
    digest = hashlib.sha256(schema_json.encode("utf-8")).hexdigest()
    return f"schema_id={schema_id or 'none'}|doc_type={document_type}|schema_sha256={digest}"


def _get_system_prompt_cached(
    *,
    schema_id: Optional[str],
    document_type: str,
    schema: Any,
    tenant_id: Optional[str],
    user_token: Optional[str],
) -> str:
    cache_key = _calculate_system_prompt_cache_key(
        schema_id=schema_id,
        document_type=document_type,
        schema=schema,
    )
    cached = _SYSTEM_PROMPT_CACHE.get(cache_key)
    if isinstance(cached, str) and cached:
        return cached

    from utils.prompt_generator import generate_system_prompt

    prompt = generate_system_prompt(
        document_type=document_type,
        schema=schema,
        tenant_id=tenant_id,
        schema_id=schema_id,
        user_token=user_token,
    )
    if prompt:
        _SYSTEM_PROMPT_CACHE.set(cache_key, prompt)
    return prompt


def _get_prompt_cache_tenant_id(*, schema_id: Optional[str], tenant_id: Optional[str]) -> Optional[str]:
    if not schema_id:
        return tenant_id

    try:
        details = get_schema_details(schema_id)
        if not details:
            return tenant_id

        schema_tenant_id = details.get("tenant_id")
        if schema_tenant_id is None:
            return None

        return tenant_id
    except Exception:
        return tenant_id




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
    document_id: Optional[str],
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
            "document_id": document_id,
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


def _persist_deferred_records(records: list[DeferredPersistenceRecord]) -> None:
    for r in records:
        try:
            document_id = _create_document_row(
                tenant_id=r.tenant_id,
                filename=r.filename,
                file_size=r.file_size,
                page_count=r.page_count,
                status=r.status,
                metadata=r.metadata,
                user_token=r.user_token,
            )

            _log_extraction_result(
                tenant_id=r.tenant_id,
                filename=r.filename,
                document_id=document_id,
                schema_id=r.schema_id,
                schema_name=r.schema_name,
                field_count=r.field_count,
                processing_duration_ms=r.processing_duration_ms,
                workflow=r.workflow,
                status=r.status,
                error_message=r.error_message,
                batch_id=r.batch_id,
                user_token=r.user_token,
            )
        except Exception as e:
            pass


def _create_document_row(
    *,
    tenant_id: str,
    filename: str,
    file_size: Optional[int],
    page_count: Optional[int] = None,
    status: str,
    metadata: Optional[Dict[str, Any]] = None,
    user_token: Optional[str] = None,
) -> Optional[str]:
    try:
        import requests

        supabase_url = os.getenv("VITE_SUPABASE_URL")
        supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")
        if not supabase_url or not supabase_key:
            return None

        auth_token = user_token if user_token else supabase_key

        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

        payload = {
            "tenant_id": tenant_id,
            "filename": filename,
            "status": status,
            "file_size": file_size,
            "page_count": page_count,
            "metadata": metadata or {},
        }

        resp = requests.post(
            f"{supabase_url}/rest/v1/documents",
            headers=headers,
            json=payload,
            timeout=5,
        )
        if resp.status_code not in [200, 201]:
            return None

        data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get("id")
        if isinstance(data, dict):
            return data.get("id")
        return None
    except Exception:
        return None


def _update_document_row(
    *,
    document_id: str,
    status: Optional[str] = None,
    page_count: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_token: Optional[str] = None,
) -> bool:
    try:
        import requests

        supabase_url = os.getenv("VITE_SUPABASE_URL")
        supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY")
        if not supabase_url or not supabase_key:
            return False

        auth_token = user_token if user_token else supabase_key

        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

        payload: Dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if page_count is not None:
            payload["page_count"] = page_count
        if metadata is not None:
            payload["metadata"] = metadata

        if not payload:
            return True

        resp = requests.patch(
            f"{supabase_url}/rest/v1/documents?id=eq.{document_id}",
            headers=headers,
            json=payload,
            timeout=5,
        )
        ok = resp.status_code in [200, 204]
        return ok
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
    raise HTTPException(
        status_code=410,
        detail="Single-file processing is deprecated. Use POST /process-batch instead.",
    )
    

# Semaphore for batch processing concurrency control
BATCH_SEMAPHORE = asyncio.Semaphore(5)


# Shared context for batch processing (leader-follower pattern)
class BatchSharedContext:
    """Pre-computed context from leader document, shared with followers.
    
    Contains document type, schema, and system prompt that can be reused across files.
    Workflow is determined per-file based on file extension.
    """
    def __init__(
        self,
        doc_type: str,
        schema_content: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ):
        self.doc_type = doc_type
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
    defer_persistence: bool = False,
    tenant_id: Optional[str] = None,
    user_token: Optional[str] = None,
) -> tuple[
    Optional[ProcessResponse],
    Optional[Dict[str, Any]],
    Optional[BatchSharedContext],
    Optional[DeferredPersistenceRecord],
]:
    """
    Process a single file with semaphore control. Returns (response, error, shared_context, deferred_persistence).
    
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
        if tenant_id is None or user_token is None:
            _, tenant_id, user_token = _get_auth_context(authorization)
        
        suffix = Path(file.filename).suffix
        tmp_path = None
        workflow_name = "unknown"
        document_row_id: Optional[str] = None
        deferred_record: Optional[DeferredPersistenceRecord] = None
        
        try:
            # Save to temp file
            with _stage_timer(timings_ms, "upload_read_and_temp_write"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await file.read()
                    tmp.write(content)
                    tmp_path = tmp.name

            if tenant_id and tmp_path and not defer_persistence:
                with _stage_timer(timings_ms, "supabase_document_create"):
                    document_row_id = await asyncio.to_thread(
                        _create_document_row,
                        tenant_id=tenant_id,
                        filename=file.filename,
                        file_size=os.path.getsize(tmp_path),
                        page_count=None,
                        status="processing",
                        metadata={
                            "batch_id": batch_id,
                            "request_id": request_id,
                            "source": "api_batch",
                        },
                        user_token=user_token,
                    )
            
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
                     return None, {"filename": file.filename, "error": str(e)}, None, None
                except Exception as e:
                     return None, {"filename": file.filename, "error": f"Failed to load document: {str(e)}"}, None, None

                router_doc = Document(page_content=full_text, metadata={"source": file.filename})
            
            elif is_image:
                router_doc = Document(page_content="", metadata={"source": file.filename})
                # images don't need text loading for router yet (vision step handles it)
                page_count = 1
            else:
                return None, {"filename": file.filename, "error": f"Unsupported file type: {suffix}"}, None, None
            
            # Use shared context from leader, or compute for leader
            if shared_context:
                # Follower: use pre-computed values from leader
                doc_type = shared_context.doc_type
                schema_content = shared_context.schema_content
                system_prompt = shared_context.system_prompt

            else:
                # Leader or standalone: compute values
                if is_image:
                    doc_type = "generic"
                else:
                    with _stage_timer(timings_ms, "router"):
                        doc_type = classify_document_type(router_doc, schema_id=schema_id, tenant_id=tenant_id)
                
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
                        return None, {"filename": file.filename, "error": f"Invalid schema JSON: {str(e)}"}, None, None
                
                if not schema_content:
                    return None, {"filename": file.filename, "error": "No schema provided"}, None, None
                
                # Generate system prompt for leader (followers will reuse)
                system_prompt = None
                if is_leader:
                    from utils.prompt_generator import generate_system_prompt
                    with _stage_timer(timings_ms, "prompt_generate"):
                        system_prompt = generate_system_prompt(
                            document_type=doc_type,
                            schema=schema_content,
                            tenant_id=_get_prompt_cache_tenant_id(schema_id=schema_id, tenant_id=tenant_id),
                            schema_id=schema_id,
                            user_token=user_token,
                        )
            
            # Determine workflow based on file characteristics
            workflow_name = _determine_workflow(suffix, len(full_text) if 'full_text' in locals() else 0)
            
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
                    with _stage_timer(timings_ms, "prompt_generate"):
                        system_prompt = _get_system_prompt_cached(
                            schema_id=schema_id,
                            document_type=doc_type,
                            schema=schema_content,
                            tenant_id=_get_prompt_cache_tenant_id(schema_id=schema_id, tenant_id=tenant_id),
                            user_token=user_token,
                        )
                
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
                    with _stage_timer(timings_ms, "prompt_generate"):
                        system_prompt = _get_system_prompt_cached(
                            schema_id=schema_id,
                            document_type=doc_type,
                            schema=schema_content,
                            tenant_id=tenant_id,
                            user_token=user_token,
                        )
                
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
                    schema_content=schema_content,
                    system_prompt=system_prompt,
                )
            
            
            # Log result
            processing_duration_ms = int((time.time() - start_time) * 1000)
            field_count = len([v for v in extraction_result.values() if v is not None]) if extraction_result else 0
            schema_name = schema_content.get("document_type") or schema_content.get("name") if schema_content else None
            
            if tenant_id:
                if defer_persistence:
                    deferred_record = DeferredPersistenceRecord(
                        tenant_id=tenant_id,
                        filename=file.filename,
                        file_size=os.path.getsize(tmp_path),
                        page_count=page_count,
                        status="completed",
                        schema_id=schema_id,
                        schema_name=schema_name,
                        field_count=field_count,
                        processing_duration_ms=processing_duration_ms,
                        workflow=workflow_name,
                        batch_id=batch_id,
                        user_token=user_token,
                        metadata={
                            "batch_id": batch_id,
                            "request_id": request_id,
                            "source": "api_batch",
                            "page_count": page_count,
                            "doc_type": doc_type,
                            "workflow": workflow_name,
                            "timings_ms": timings_ms,
                        },
                    )
                else:
                    if document_row_id:
                        with _stage_timer(timings_ms, "supabase_document_update"):
                            await asyncio.to_thread(
                                _update_document_row,
                                document_id=document_row_id,
                                status="completed",
                                page_count=page_count,
                                metadata={
                                    "batch_id": batch_id,
                                    "request_id": request_id,
                                    "source": "api_batch",
                                    "page_count": page_count,
                                    "doc_type": doc_type,
                                    "workflow": workflow_name,
                                    "timings_ms": timings_ms,
                                },
                                user_token=user_token,
                            )
                    with _stage_timer(timings_ms, "supabase_log_result"):
                        await asyncio.to_thread(
                            _log_extraction_result,
                            tenant_id=tenant_id,
                            filename=file.filename,
                            document_id=document_row_id,
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
            
            return ProcessResponse(
                status="success",
                document_id=document_row_id or "no-persistence",
                results=extraction_result,
                operational_metadata=op_metadata,
                batch_id=batch_id
            ), None, result_shared_context, deferred_record
            
        except Exception as e:
            if tenant_id:
                processing_duration_ms = int((time.time() - start_time) * 1000)
                if defer_persistence:
                    deferred_record = DeferredPersistenceRecord(
                        tenant_id=tenant_id,
                        filename=file.filename,
                        file_size=os.path.getsize(tmp_path) if tmp_path and os.path.exists(tmp_path) else None,
                        page_count=page_count if 'page_count' in locals() else None,
                        status="failed",
                        schema_id=schema_id,
                        schema_name=None,
                        field_count=0,
                        processing_duration_ms=processing_duration_ms,
                        workflow=workflow_name,
                        batch_id=batch_id,
                        user_token=user_token,
                        error_message=str(e)[:500],
                        metadata={
                            "batch_id": batch_id,
                            "request_id": request_id,
                            "source": "api_batch",
                            "error_message": str(e)[:500],
                        },
                    )
                else:
                    if document_row_id:
                        _update_document_row(
                            document_id=document_row_id,
                            status="failed",
                            page_count=page_count if 'page_count' in locals() else None,
                            metadata={
                                "batch_id": batch_id,
                                "request_id": request_id,
                                "source": "api_batch",
                                "error_message": str(e)[:500],
                            },
                            user_token=user_token,
                        )
                    _log_extraction_result(
                        tenant_id=tenant_id,
                        filename=file.filename,
                        document_id=document_row_id,
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
            return None, {"filename": file.filename, "error": str(e)}, None, deferred_record
        
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
    background_tasks: BackgroundTasks = None,
):
    """
    Process multiple files concurrently (up to 5 at a time).
    Uses leader-follower pattern: first file determines doc_type and generates system_prompt,
    then remaining files process in parallel using the pre-computed values.
    """
    batch_start_time = time.time()
    batch_timings_ms: Dict[str, int] = {}
    batch_id = str(uuid.uuid4())

    auth_and_quota_start_time = time.time()
    user_id, tenant_id, user_token = _get_auth_context(authorization)
    
    successful_results = []
    errors = []
    deferred_records: list[DeferredPersistenceRecord] = []
    
    if not files:
        batch_timings_ms["auth_and_quota_ms"] = int((time.time() - auth_and_quota_start_time) * 1000)
        batch_timings_ms["total_batch_ms"] = int((time.time() - batch_start_time) * 1000)
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
        batch_timings_ms["auth_and_quota_ms"] = int((time.time() - auth_and_quota_start_time) * 1000)
        batch_timings_ms["total_batch_ms"] = int((time.time() - batch_start_time) * 1000)
        raise HTTPException(
            status_code=413,
            detail=(
                f"Batch exceeds maximum pages. "
                f"Total pages={total_pages}, max={MAX_PAGES_PER_BATCH}. "
                f"Per-file: {per_file_pages}"
            ),
        )

    # Monthly quota (per user_id): reserve pages upfront to prevent concurrent overage.
    reserved_pages = 0
    if user_id:
        ok = _adjust_monthly_usage_pages(
            user_id=user_id,
            pages_delta=total_pages,
            authorization=authorization,
            max_pages=MAX_PAGES_PER_MONTH,
        )
        if not ok:
            batch_timings_ms["auth_and_quota_ms"] = int((time.time() - auth_and_quota_start_time) * 1000)
            batch_timings_ms["total_batch_ms"] = int((time.time() - batch_start_time) * 1000)
            raise HTTPException(
                status_code=402,
                detail=f"Monthly quota exceeded. Max {MAX_PAGES_PER_MONTH} pages/month.",
            )
        reserved_pages = total_pages

    batch_timings_ms["auth_and_quota_ms"] = int((time.time() - auth_and_quota_start_time) * 1000)

    try:
        # Optimistic Parallelism: Only use if schema has been used before (has document_type).
        # If document_type exists, we have cached prompts and can process all files in parallel.
        # If document_type is None, use leader-follower to discover type from first document.
        optimistic_context_start_time = time.time()
        optimistic_context = None
        if schema_id:
            schema_details = _get_schema_details_cached(schema_id, tenant_id)
            if schema_details and schema_details.get("content"):
                
                # Check if document_type exists (explicit or from schema)
                # Only go optimistic if we have a known document_type (not None)
                opt_doc_type = document_type or schema_details.get("document_type")
                
                # Only create optimistic context if document_type is known
                if opt_doc_type:
                    opt_schema_content = schema_details.get("content")
                    
                    # Generate system prompt once
                    opt_system_prompt = _get_system_prompt_cached(
                        schema_id=schema_id,
                        document_type=opt_doc_type,
                        schema=opt_schema_content,
                        tenant_id=_get_prompt_cache_tenant_id(schema_id=schema_id, tenant_id=tenant_id),
                        user_token=user_token,
                    )
                    
                    optimistic_context = BatchSharedContext(
                        doc_type=opt_doc_type,
                        schema_content=opt_schema_content,
                        system_prompt=opt_system_prompt
                    )

        batch_timings_ms["optimistic_context_ms"] = int((time.time() - optimistic_context_start_time) * 1000)

        if optimistic_context:
            # OPTIMISTIC PATH: Launch all files in parallel immediately
            follower_tasks = [
                _process_single_file(
                    file=f,
                    batch_id=batch_id,
                    authorization=authorization,
                    shared_context=optimistic_context,
                    schema_id=schema_id,
                    is_leader=False,
                    defer_persistence=True,
                    tenant_id=tenant_id,
                    user_token=user_token,
                )
                for f in files
            ]

            gather_start_time = time.time()
            results = await asyncio.gather(*follower_tasks)
            batch_timings_ms["gather_ms"] = int((time.time() - gather_start_time) * 1000)
            for response, error, _, deferred_record in results:
                if response:
                    successful_results.append(response)
                if error:
                    errors.append(error)
                if deferred_record:
                    deferred_records.append(deferred_record)

        else:
            # FALLBACK PATH (Leader-Follower): Process first file to discovery type
            # Step 1: Process LEADER (first file) to determine doc_type and generate system_prompt
            leader_idx = 0
            for idx, f in enumerate(files):
                if not f.filename.lower().endswith(".txt"):
                    leader_idx = idx
                    break

            leader_file = files[leader_idx]
            
            leader_response, leader_error, shared_context, deferred_record = await _process_single_file(
                file=leader_file,
                batch_id=batch_id,
                authorization=authorization,
                shared_context=None,  # Leader computes its own
                schema_id=schema_id,
                schema_content_from_request=schema_content_from_request,
                document_type=document_type,
                is_leader=True,
                defer_persistence=True,
                tenant_id=tenant_id,
                user_token=user_token,
            )
            
            if leader_response:
                successful_results.append(leader_response)
            if leader_error:
                errors.append(leader_error)

            if deferred_record:
                deferred_records.append(deferred_record)
            
            # Step 2: Process FOLLOWERS in parallel using shared context from leader
            follower_files = [f for i, f in enumerate(files) if i != leader_idx]

            if len(follower_files) > 0 and shared_context:
                
                follower_tasks = [
                    _process_single_file(
                        file=f,
                        batch_id=batch_id,
                        authorization=authorization,
                        shared_context=shared_context,  # Reuse leader's computed values
                        schema_id=schema_id,
                        is_leader=False,
                        defer_persistence=True,
                        tenant_id=tenant_id,
                        user_token=user_token,
                    )
                    for f in follower_files
                ]

                # Process followers concurrently with semaphore limiting to 5
                gather_start_time = time.time()
                follower_results = await asyncio.gather(*follower_tasks)
                batch_timings_ms["gather_ms"] = int((time.time() - gather_start_time) * 1000)
                
                for response, error, _, deferred_record in follower_results:
                    if response:
                        successful_results.append(response)
                    if error:
                        errors.append(error)
                    if deferred_record:
                        deferred_records.append(deferred_record)
        
            elif len(follower_files) > 0 and not shared_context:
                # Leader failed to produce shared context, process followers independently
                
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
                        defer_persistence=True,
                        tenant_id=tenant_id,
                        user_token=user_token,
                    )
                    for f in follower_files
                ]

                # Process followers concurrently with semaphore limiting to 5
                gather_start_time = time.time()
                follower_results = await asyncio.gather(*follower_tasks)
                batch_timings_ms["gather_ms"] = int((time.time() - gather_start_time) * 1000)
                
                for response, error, _, deferred_record in follower_results:
                    if response:
                        successful_results.append(response)
                    if error:
                        errors.append(error)
                    if deferred_record:
                        deferred_records.append(deferred_record)

        batch_timings_ms["total_batch_ms"] = int((time.time() - batch_start_time) * 1000)

        if deferred_records and background_tasks is not None:
            background_tasks.add_task(_persist_deferred_records, deferred_records)
        elif deferred_records:
            pass

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
    user_id = _get_user_id_from_token_cached(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    from utils.supabase_schemas import delete_schema
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
