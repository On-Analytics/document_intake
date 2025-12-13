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


class BatchProcessResponse(BaseModel):
    status: str
    batch_id: str
    total_files: int
    successful: int
    failed: int
    results: list[ProcessResponse]
    errors: list[Dict[str, Any]]

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
                schema_content=schema_content,
                system_prompt=system_prompt,
                markdown_content=markdown_content,
                document_type=doc_type,
                structure_hints=structure_hints,
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
    async with BATCH_SEMAPHORE:
        start_time = time.time()
        tenant_id = _get_tenant_id_from_token(authorization)
        user_token = authorization.split(" ")[1] if authorization and authorization.startswith("Bearer ") else None
        
        suffix = Path(file.filename).suffix
        tmp_path = None
        workflow_name = "unknown"
        
        try:
            # Save to temp file
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
                if is_pdf:
                    loader = PDFPlumberLoader(tmp_path)
                elif is_txt:
                    loader = TextLoader(tmp_path, encoding="utf-8")
                else:
                    loader = Docx2txtLoader(tmp_path)
                
                docs = loader.load()
                if not docs:
                    return None, {"filename": file.filename, "error": "Could not extract text from document"}, None
                
                full_text = "\n".join([d.page_content for d in docs])
                router_doc = Document(page_content=full_text, metadata={"source": file.filename})
            
            elif is_image:
                router_doc = Document(page_content="", metadata={"source": file.filename})
                docs = []  # For page_count later
            else:
                return None, {"filename": file.filename, "error": f"Unsupported file type: {suffix}"}, None
            
            # Use shared context from leader, or compute for leader
            if shared_context:
                # Follower: use pre-computed values
                doc_type = shared_context.doc_type
                workflow_name = shared_context.workflow_name
                schema_content = shared_context.schema_content
                system_prompt = shared_context.system_prompt
            else:
                # Leader or standalone: compute values
                if is_image:
                    doc_type = "generic"
                    workflow_name = "balanced"
                else:
                    route = route_document(router_doc)
                    doc_type = route.get("document_type", "generic")
                    workflow_name = route.get("workflow", "basic")
                
                # Override with explicit document_type if provided
                if document_type:
                    doc_type = document_type
                
                # Load schema
                schema_content = None
                if schema_id:
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
                    system_prompt = generate_system_prompt(document_type=doc_type, schema=schema_content)
            
            # Run extraction
            from core_pipeline import DocumentMetadata
            from extractors.extract_fields_basic import extract_fields_basic
            from extractors.extract_fields_balanced import extract_fields_balanced
            from extractors.vision_generate_markdown import vision_generate_markdown
            
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
                vision_result = vision_generate_markdown(
                    document=router_doc,
                    metadata=doc_metadata,
                    schema_content=schema_content
                )
                
                # Use pre-computed prompt or generate if not available
                if not system_prompt:
                    from utils.prompt_generator import generate_system_prompt
                    system_prompt = generate_system_prompt(document_type=doc_type, schema=schema_content)
                
                markdown_content = vision_result.get("markdown_content")
                structure_hints = vision_result.get("structure_hints")
                
                extraction_result = extract_fields_balanced(
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
                    system_prompt = generate_system_prompt(document_type=doc_type, schema=schema_content)
                
                extraction_result = extract_fields_basic(
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
            
            extraction_result["source_file"] = file.filename
            
            op_metadata = {
                "page_count": len(docs) if is_pdf else 1,
                "doc_type": doc_type,
                "workflow": workflow_name,
                "source": "api_batch"
            }
            
            return ProcessResponse(
                status="success",
                document_id="no-persistence",
                results=extraction_result,
                operational_metadata=op_metadata,
                batch_id=batch_id
            ), None, result_shared_context
            
        except Exception as e:
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
    
    # Step 1: Process LEADER (first file) to determine doc_type and generate system_prompt
    leader_file = files[0]
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
    if len(files) > 1 and shared_context:
        print(f"[Batch] Processing {len(files) - 1} follower files with shared context (doc_type='{shared_context.doc_type}')")
        
        follower_tasks = [
            _process_single_file(
                file=f,
                batch_id=batch_id,
                authorization=authorization,
                shared_context=shared_context,  # Reuse leader's computed values
                schema_id=schema_id,
                is_leader=False,
            )
            for f in files[1:]
        ]
        
        # Process followers concurrently with semaphore limiting to 5
        follower_results = await asyncio.gather(*follower_tasks)
        
        for response, error, _ in follower_results:
            if response:
                successful_results.append(response)
            if error:
                errors.append(error)
    
    elif len(files) > 1 and not shared_context:
        # Leader failed to produce shared context, process followers independently
        print(f"[Batch] Leader failed, processing {len(files) - 1} followers independently")
        
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
            for f in files[1:]
        ]
        
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
