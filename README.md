# Document Intake & Schema Manager

This project is a document intake and schema management service. It provides:

- A **Python backend** for orchestrating document processing workflows.
- A **React + TypeScript + Vite frontend** for uploading documents and managing schemas.
- A set of **JSON templates** describing common document types.

## Project Structure

- `main.py`, `core_pipeline.py`, `workflows.py` – backend entrypoint and processing logic.
- `src/` – React frontend (Vite + TypeScript).
- `templates/` – JSON templates used to define extraction schemas.

## Templates

The `templates/` folder contains simple JSON schema definitions for common document types, including:

- `claim_schema.json`
- `invoice_schema.json`
- `resume_schema.json`
- `purchase_order_schema.json`
- `bank_statement_schema.json`

Each file declares a `document_type`, a short `description`, and a list of `fields` with basic metadata.

## Running the Backend

Create and activate a virtual environment, install dependencies, and run the API server (for example, with Uvicorn):

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Adjust the command if your entrypoint or module path differs.

## Running the Frontend

Install Node dependencies and start the Vite dev server from the project root:

```bash
npm install
npm run dev
```

Then open the printed local URL in your browser.

