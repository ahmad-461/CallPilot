import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException, status, Query

from app.db.supabase_client import get_supabase_client
from app.services import llm_service
from app.services.twilio_service import (
    validate_twilio_request,
    build_initial_call_twiml,
    build_speech_response_twiml,
    build_retry_twiml,
    build_fallback_twiml,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])

PLACEHOLDER_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"


@router.post("/incoming-call")
async def incoming_call(request: Request):
    """
    Twilio webhook entrypoint for inbound calls.
    Validates request signature, logs call start in Supabase, and returns greeting TwiML.
    """
    form_data = await request.form()
    params = dict(form_data)

    if not validate_twilio_request(request, params):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    call_sid = params.get("CallSid", "")
    customer_phone = params.get("From", "Unknown")
    started_at = datetime.now(timezone.utc)

    # Log initial call into Supabase
    if call_sid:
        try:
            supabase = get_supabase_client()
            supabase.table("calls").insert({
                "call_sid": call_sid,
                "business_id": PLACEHOLDER_BUSINESS_ID,
                "customer_phone": customer_phone,
                "started_at": started_at.isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to log incoming call for CallSid {call_sid}: {e}")

    twiml_content = build_initial_call_twiml()
    return Response(content=twiml_content, media_type="text/xml")


@router.post("/handle-speech")
async def handle_speech(request: Request, retry: Optional[int] = Query(0)):
    """
    Twilio webhook callback for speech input gather results.
    Processes SpeechResult through LLM service, updates call record in Supabase, and returns TwiML.
    """
    form_data = await request.form()
    params = dict(form_data)

    if not validate_twilio_request(request, params):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    call_sid = params.get("CallSid", "")
    customer_phone = params.get("From", "Unknown")
    speech_result = params.get("SpeechResult", "").strip()

    if speech_result:
        llm_response_text, is_complete, outcome = llm_service.process_conversation_turn(
            call_sid=call_sid,
            customer_phone=customer_phone,
            user_speech=speech_result,
        )

        transcript = _append_to_transcript(call_sid, speech_result, llm_response_text)
        _update_call_record(call_sid, transcript=transcript, outcome=outcome, ended=is_complete)

        if is_complete:
            llm_service.clear_session(call_sid)
            twiml_content = build_speech_response_twiml(llm_response_text, is_complete=True)
        else:
            twiml_content = build_speech_response_twiml(llm_response_text, is_complete=False)

        return Response(content=twiml_content, media_type="text/xml")

    if retry == 1:
        # Second attempt failed -> Terminal step
        _update_call_record(call_sid, outcome="unresolved", ended=True)
        llm_service.clear_session(call_sid)
        twiml_content = build_fallback_twiml()
        return Response(content=twiml_content, media_type="text/xml")

    # First attempt failed -> Prompt retry
    twiml_content = build_retry_twiml()
    return Response(content=twiml_content, media_type="text/xml")


def _append_to_transcript(call_sid: str, user_speech: str, agent_response: str) -> str:
    """Helper to retrieve existing transcript from Supabase and append the new turn."""
    new_turn = f"User: {user_speech}\nAgent: {agent_response}"
    if not call_sid:
        return new_turn

    try:
        supabase = get_supabase_client()
        call_resp = supabase.table("calls").select("transcript").eq("call_sid", call_sid).execute()
        if call_resp.data and len(call_resp.data) > 0:
            existing = call_resp.data[0].get("transcript")
            if existing:
                return f"{existing}\n{new_turn}"
    except Exception as e:
        logger.error(f"Failed to fetch existing transcript for CallSid {call_sid}: {e}")

    return new_turn


def _update_call_record(
    call_sid: str,
    transcript: Optional[str] = None,
    outcome: str = "unresolved",
    ended: bool = False,
):
    """
    Helper to update transcript, outcome, and optionally ended_at and duration_seconds in Supabase calls table.
    """
    if not call_sid:
        return

    try:
        supabase = get_supabase_client()
        update_payload: dict = {
            "outcome": outcome,
        }

        if transcript is not None:
            update_payload["transcript"] = transcript

        if ended:
            ended_at = datetime.now(timezone.utc)
            update_payload["ended_at"] = ended_at.isoformat()

            # Retrieve started_at to compute call duration
            call_resp = supabase.table("calls").select("started_at").eq("call_sid", call_sid).execute()
            if call_resp.data and len(call_resp.data) > 0 and call_resp.data[0].get("started_at"):
                raw_started = call_resp.data[0]["started_at"]
                if isinstance(raw_started, str):
                    started_dt = datetime.fromisoformat(raw_started.replace("Z", "+00:00"))
                    duration_seconds = max(0, int((ended_at - started_dt).total_seconds()))
                    update_payload["duration_seconds"] = duration_seconds

        supabase.table("calls").update(update_payload).eq("call_sid", call_sid).execute()
    except Exception as e:
        logger.error(f"Failed to update call record for CallSid {call_sid}: {e}")
