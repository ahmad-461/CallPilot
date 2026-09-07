from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.db.supabase_client import check_db_connection
from app.routes import calls, appointments, business, twilio

app = FastAPI(
    title="CallPilot API",
    description="Backend API for CallPilot AI Voice Receptionist",
    version="0.1.0",
)

# CORS configuration for Next.js frontend running on localhost:3000
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route stubs
app.include_router(calls.router)
app.include_router(appointments.router)
app.include_router(business.router)
app.include_router(twilio.router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(response: Response):
    """
    Health check endpoint that verifies database connection to Supabase.
    Returns status 200 with {"status": "ok", "db": "connected"} when healthy,
    or status 503 with {"status": "error", "db": "disconnected"} when database is unreachable.
    """
    is_connected, _ = check_db_connection()
    if is_connected:
        return {"status": "ok", "db": "connected"}
    else:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "db": "disconnected"}
