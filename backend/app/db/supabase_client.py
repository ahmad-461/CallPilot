import os
from typing import Tuple, Optional
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_KEY")

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Returns initialized Supabase client singleton."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")

    _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def check_db_connection() -> Tuple[bool, str]:
    """
    Pings Supabase DB by querying businesses table.
    Returns (True, "connected") if successful, or (False, error_message) if failed.
    """
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return False, "Missing SUPABASE_URL or SUPABASE_KEY environment variables."

        client = get_supabase_client()
        # Lightweight query to verify database connection
        client.table("businesses").select("id").limit(1).execute()
        return True, "connected"
    except Exception as e:
        return False, str(e)
