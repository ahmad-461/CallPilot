# CallPilot — AI Voice Receptionist

CallPilot is an AI voice receptionist platform designed to handle inbound business calls, answer queries using RAG, and manage appointment scheduling.

## Repo Structure

```text
/backend
  /app
    /db           # Supabase client initialization & DB connection check
    /models       # SQLAlchemy models
    /routes       # FastAPI routers (stubs for calls, appointments, business)
    /services     # Service stubs (twilio, llm, rag)
    main.py       # FastAPI application entrypoint with /health endpoint
  requirements.txt
  .env.example    # Environment variable placeholders
/sql
  schema.sql      # Database schema (Postgres / Supabase)
.npmrc            # Node config with legacy-peer-deps=true
```

## Setup & Running

### 1. Prerequisites
- Python 3.10+
- Supabase account & project

### 2. Environment Configuration
Copy the example environment file and set your Supabase credentials:
```bash
cp backend/.env.example backend/.env
```
Update `SUPABASE_URL` and `SUPABASE_KEY` in `backend/.env`.

### 3. Database Setup
Run the SQL script `sql/schema.sql` directly in the Supabase SQL Editor. This will:
- Enable required Postgres extensions (`btree_gist`, `vector`).
- Create ENUM types and tables (`businesses`, `customers`, `appointments`, `calls`, `knowledge_base_documents`).
- Set up indexes and an exclusion constraint to prevent double-booking on overlapping appointment slots.

### 4. Install Dependencies
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Run the Backend Server
Start the local development server using `uvicorn`:
```bash
cd backend
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. You can check server health at `http://127.0.0.1:8000/health`.
