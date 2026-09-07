import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from app.db.supabase_client import get_supabase_client
from app.services import rag_service

logger = logging.getLogger(__name__)

PLACEHOLDER_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"


def _parse_datetime(date_str: str, time_str: str) -> datetime:
    """
    Parses date (YYYY-MM-DD) and time (HH:MM or HH:MM:SS) strings into an aware UTC datetime object.
    Raises ValueError if formats are invalid.
    """
    clean_date = date_str.strip()
    clean_time = time_str.strip()
    if len(clean_time) == 5:
        clean_time = f"{clean_time}:00"

    combined = f"{clean_date}T{clean_time}"
    dt = datetime.fromisoformat(combined)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def check_availability(
    date: str,
    time: str,
    business_id: str = PLACEHOLDER_BUSINESS_ID,
    duration_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Queries the appointments table for the given business_id/date/time range.
    Returns whether the requested slot is free (only 'booked' appointments block a slot).
    """
    try:
        start_dt = _parse_datetime(date, time)
    except ValueError as e:
        return {
            "available": False,
            "error": "invalid_datetime",
            "message": f"Invalid date or time format. Please use YYYY-MM-DD and HH:MM: {e}",
        }

    end_dt = start_dt + timedelta(minutes=duration_minutes)

    try:
        supabase = get_supabase_client()
        # Query active 'booked' appointments for the business
        response = (
            supabase.table("appointments")
            .select("id, start_time, end_time")
            .eq("business_id", business_id)
            .eq("status", "booked")
            .execute()
        )

        existing_appointments = response.data or []
        for appt in existing_appointments:
            appt_start = datetime.fromisoformat(appt["start_time"].replace("Z", "+00:00"))
            appt_end = datetime.fromisoformat(appt["end_time"].replace("Z", "+00:00"))

            # Overlap check: appt_start < requested_end and appt_end > requested_start
            if appt_start < end_dt and appt_end > start_dt:
                return {
                    "available": False,
                    "date": date,
                    "time": time,
                    "business_id": business_id,
                    "message": f"Slot at {time} on {date} is already booked.",
                }

        return {
            "available": True,
            "date": date,
            "time": time,
            "business_id": business_id,
            "message": f"Slot at {time} on {date} is available.",
        }
    except Exception as e:
        logger.error(f"Error checking availability: {e}")
        return {
            "available": False,
            "error": "database_error",
            "message": f"Unable to verify availability: {str(e)}",
        }


def create_appointment(
    customer_phone: str,
    date: str,
    time: str,
    business_id: str = PLACEHOLDER_BUSINESS_ID,
    customer_name: Optional[str] = None,
    duration_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Looks up or creates the customer by phone number in customers table,
    then inserts a new row in appointments with status='booked'.
    Catches exclusion constraint / conflict errors if slot is taken.
    """
    try:
        start_dt = _parse_datetime(date, time)
    except ValueError as e:
        return {
            "success": False,
            "error": "invalid_datetime",
            "message": f"Invalid date or time format: {e}",
        }

    end_dt = start_dt + timedelta(minutes=duration_minutes)

    try:
        supabase = get_supabase_client()

        # 1. Look up or create customer
        cust_resp = (
            supabase.table("customers")
            .select("id, name")
            .eq("phone_number", customer_phone)
            .execute()
        )

        customer_id = None
        if cust_resp.data and len(cust_resp.data) > 0:
            existing_cust = cust_resp.data[0]
            customer_id = existing_cust["id"]
            # If customer exists and name was blank, update name if provided
            if customer_name and not existing_cust.get("name"):
                supabase.table("customers").update({"name": customer_name}).eq("id", customer_id).execute()
        else:
            cust_insert = {
                "phone_number": customer_phone,
            }
            if customer_name:
                cust_insert["name"] = customer_name
            new_cust_resp = supabase.table("customers").insert(cust_insert).execute()
            if new_cust_resp.data and len(new_cust_resp.data) > 0:
                customer_id = new_cust_resp.data[0]["id"]

        if not customer_id:
            return {
                "success": False,
                "error": "customer_creation_failed",
                "message": "Failed to resolve customer record.",
            }

        # 2. Re-check availability before insertion to avoid unnecessary conflict errors
        avail_check = check_availability(date, time, business_id, duration_minutes)
        if not avail_check.get("available"):
            return {
                "success": False,
                "error": "slot_unavailable",
                "message": f"Slot at {time} on {date} is no longer available.",
            }

        # 3. Insert appointment
        appt_payload = {
            "business_id": business_id,
            "customer_id": customer_id,
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "status": "booked",
        }

        insert_resp = supabase.table("appointments").insert(appt_payload).execute()
        if insert_resp.data and len(insert_resp.data) > 0:
            created_appt = insert_resp.data[0]
            return {
                "success": True,
                "appointment_id": created_appt["id"],
                "customer_phone": customer_phone,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "message": f"Appointment successfully booked for {date} at {time}.",
            }

        return {
            "success": False,
            "error": "booking_failed",
            "message": "Could not create appointment record.",
        }

    except Exception as e:
        logger.error(f"Failed to create appointment: {e}")
        err_msg = str(e).lower()
        if "exclusion" in err_msg or "overlap" in err_msg or "constraint" in err_msg:
            return {
                "success": False,
                "error": "slot_unavailable",
                "message": f"The slot at {time} on {date} is no longer available.",
            }
        return {
            "success": False,
            "error": "database_error",
            "message": f"An error occurred while booking appointment: {str(e)}",
        }


def update_appointment(
    appointment_id: str,
    new_date: str,
    new_time: str,
    duration_minutes: int = 30,
) -> Dict[str, Any]:
    """
    Changes an existing appointment's start_time and end_time, keeping status='booked'.
    Re-checks for conflicts before committing.
    """
    try:
        new_start_dt = _parse_datetime(new_date, new_time)
    except ValueError as e:
        return {
            "success": False,
            "error": "invalid_datetime",
            "message": f"Invalid date or time format: {e}",
        }

    new_end_dt = new_start_dt + timedelta(minutes=duration_minutes)

    try:
        supabase = get_supabase_client()

        # Retrieve current appointment
        appt_resp = supabase.table("appointments").select("*").eq("id", appointment_id).execute()
        if not appt_resp.data or len(appt_resp.data) == 0:
            return {
                "success": False,
                "error": "not_found",
                "message": f"Appointment with ID {appointment_id} was not found.",
            }

        existing_appt = appt_resp.data[0]
        business_id = existing_appt["business_id"]

        # Check for conflicts with other booked appointments
        other_appts_resp = (
            supabase.table("appointments")
            .select("id, start_time, end_time")
            .eq("business_id", business_id)
            .eq("status", "booked")
            .neq("id", appointment_id)
            .execute()
        )

        other_appts = other_appts_resp.data or []
        for appt in other_appts:
            a_start = datetime.fromisoformat(appt["start_time"].replace("Z", "+00:00"))
            a_end = datetime.fromisoformat(appt["end_time"].replace("Z", "+00:00"))
            if a_start < new_end_dt and a_end > new_start_dt:
                return {
                    "success": False,
                    "error": "slot_unavailable",
                    "message": f"The requested new time slot ({new_date} at {new_time}) is not available.",
                }

        # Perform update
        update_payload = {
            "start_time": new_start_dt.isoformat(),
            "end_time": new_end_dt.isoformat(),
            "status": "booked",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        upd_resp = (
            supabase.table("appointments")
            .update(update_payload)
            .eq("id", appointment_id)
            .execute()
        )

        if upd_resp.data and len(upd_resp.data) > 0:
            return {
                "success": True,
                "appointment_id": appointment_id,
                "new_start_time": new_start_dt.isoformat(),
                "new_end_time": new_end_dt.isoformat(),
                "message": f"Appointment successfully updated to {new_date} at {new_time}.",
            }

        return {
            "success": False,
            "error": "update_failed",
            "message": "Failed to update appointment.",
        }

    except Exception as e:
        logger.error(f"Failed to update appointment {appointment_id}: {e}")
        err_msg = str(e).lower()
        if "exclusion" in err_msg or "overlap" in err_msg or "constraint" in err_msg:
            return {
                "success": False,
                "error": "slot_unavailable",
                "message": f"The new slot at {new_time} on {new_date} is no longer available.",
            }
        return {
            "success": False,
            "error": "database_error",
            "message": f"An error occurred while rescheduling appointment: {str(e)}",
        }


def cancel_appointment(appointment_id: str) -> Dict[str, Any]:
    """
    Sets status='cancelled' on the given appointment.
    """
    try:
        supabase = get_supabase_client()

        appt_resp = supabase.table("appointments").select("id").eq("id", appointment_id).execute()
        if not appt_resp.data or len(appt_resp.data) == 0:
            return {
                "success": False,
                "error": "not_found",
                "message": f"Appointment with ID {appointment_id} was not found.",
            }

        update_payload = {
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        upd_resp = (
            supabase.table("appointments")
            .update(update_payload)
            .eq("id", appointment_id)
            .execute()
        )

        if upd_resp.data and len(upd_resp.data) > 0:
            return {
                "success": True,
                "appointment_id": appointment_id,
                "message": f"Appointment {appointment_id} has been cancelled.",
            }

        return {
            "success": False,
            "error": "cancel_failed",
            "message": "Failed to cancel appointment.",
        }

    except Exception as e:
        logger.error(f"Failed to cancel appointment {appointment_id}: {e}")
        return {
            "success": False,
            "error": "database_error",
            "message": f"An error occurred while cancelling appointment: {str(e)}",
        }


def get_business_info(
    business_id: str = PLACEHOLDER_BUSINESS_ID,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieves business information via RAG vector similarity search in knowledge_base_documents.
    If matching chunks are found, returns them as context for the LLM.
    If no relevant chunks are found above the similarity threshold, returns a 'no info found' result.
    """
    try:
        results = rag_service.search_knowledge_base(
            business_id=business_id,
            query=query,
            top_k=3,
            similarity_threshold=0.3,
        )

        if not results:
            return {
                "found": False,
                "business_id": business_id,
                "query": query,
                "message": "I don't have that information, let me connect you to someone who can help.",
            }

        relevant_passages = [
            {
                "title": res.get("title", ""),
                "content": res.get("content", ""),
                "similarity": res.get("similarity", 0.0),
            }
            for res in results
        ]

        return {
            "found": True,
            "business_id": business_id,
            "query": query,
            "passages": relevant_passages,
        }
    except Exception as e:
        logger.error(f"Error executing RAG search for business_id {business_id}: {e}")
        return {
            "found": False,
            "error": "rag_search_failed",
            "business_id": business_id,
            "query": query,
            "message": "I don't have that information, let me connect you to someone who can help.",
        }
