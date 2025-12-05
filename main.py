import shutil
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json

# Import custom modules
from auth import get_current_user, UserContext
from utils.supabase_client import get_supabase
from supabase import Client
from router import route_document
from orchestrator import run_workflow
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_core.documents import Document

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
    results: Dict[str, Any]
    operational_metadata: Dict[str, Any]

@app.get("/")
async def root():
    return {"message": "Document Processor API is running"}

@app.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    schema_id: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """
    Upload a file, process it immediately, log the event, and return results.
    """
    print(f"User {current_user.email} (Tenant: {current_user.tenant_id}) uploading {file.filename}")

    # 1. Save to Temp File (Required for PDF loaders usually)
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    temp_schema_path = None # Track temp schema file cleanup

    try:
        # 2. Load Document for Router
        # Check file extension
        is_pdf = suffix.lower() == ".pdf"
        is_image = suffix.lower() in [".png", ".jpg", ".jpeg"]
        
        if is_pdf:
            # Simplified loading logic for now
            loader = PDFPlumberLoader(tmp_path)
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

        # 4. Select Schema
        if schema_id:
            print(f"Using Custom Schema ID: {schema_id}")
            # Fetch schema from DB
            schema_res = supabase.table("schemas").select("content").eq("id", schema_id).single().execute()
            if not schema_res.data:
                raise HTTPException(status_code=404, detail="Schema not found")
            
            schema_content = schema_res.data["content"]
        else:
            # AUTO-DETECT: Fetch System Template from DB based on Router Result
            print(f"Auto-detecting schema for type: {doc_type}")
            
            # Map router types to schema types if necessary (e.g. receipt -> invoice)
            type_mapping = {
                "receipt": "invoice",
                # Add others if needed
            }
            target_type = type_mapping.get(doc_type, doc_type)
            
            # Query DB for a public schema matching this document_type
            # We use JSON containment operator to find content->'document_type' == target_type
            schema_res = supabase.table("schemas") \
                .select("content") \
                .eq("is_public", True) \
                .contains("content", {"document_type": target_type}) \
                .limit(1) \
                .execute()
                
            if schema_res.data and len(schema_res.data) > 0:
                print(f"Found System Schema for '{target_type}' in DB")
                schema_content = schema_res.data[0]["content"]
            else:
                print(f"No system schema found for '{target_type}', falling back to Claim/Generic")
                # Fallback to Claim schema from DB if specific one not found
                fallback_res = supabase.table("schemas") \
                    .select("content") \
                    .eq("is_public", True) \
                    .contains("content", {"document_type": "claim"}) \
                    .limit(1) \
                    .execute()
                
                if fallback_res.data:
                    schema_content = fallback_res.data[0]["content"]
                else:
                    raise HTTPException(status_code=404, detail="No appropriate schema found in database")

        # Write Schema to Temp File (Common for both paths)
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
                schema_path=schema_path
            )
            markdown_content = vision_result.get("markdown_content")
            structure_hints = vision_result.get("structure_hints")

            # Step 2: Extract Fields from Markdown
            extraction_result = extract_fields_balanced(
                document=router_doc,
                metadata=doc_metadata,
                schema_path=schema_path,
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
                schema_path=schema_path,
                document_type=doc_type
            )

        # 6. Log to Supabase (Stateless Mode)
        op_metadata = {
            "page_count": len(docs) if is_pdf else 1,
            "doc_type": doc_type,
            "workflow": workflow_name,
            "source": "api_upload"
        }
        
        db_res = supabase.table("documents").insert({
            "tenant_id": current_user.tenant_id,
            "filename": file.filename,
            "storage_path": None,
            "status": "completed",
            "file_size": os.path.getsize(tmp_path),
            "metadata": op_metadata
        }).execute()
        
        doc_id = db_res.data[0]['id'] if db_res.data else "unknown"

        return ProcessResponse(
            status="success",
            document_id=doc_id,
            results=extraction_result, # This would be the actual AI output
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
