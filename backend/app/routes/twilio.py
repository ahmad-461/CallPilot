import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Response, status

from app.db.supabase_client import get_supabase_client
from app.services.twilio_service import (
    validate_twilio_request,
    build_incoming_call_response,
    build_retry_speech_response,
    build_speech_handled_response,
    build_fallback_hangup_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])

HARDCODED_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"


async def _verify_twilio_signature(request: Request, form_data: dict):
    signature = request.headers.get("X-Twilio-Signature", "")
    request_url = str(request.url)
    if not validate_twilio_request(request_url, form_data, signature):
        logger.warning("Invalid Twilio signature for request URL: %s", request_url)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature"
        )


@router.post("/incoming-call")
async def incoming_call(request: Request):
    """
    Twilio webhook entrypoint for inbound calls.
    Logs call start in DB and returns TwiML greeting with <Gather>.
    """
    form_data_multi = await request.form()
    form_data = dict(form_data_multi)
    await _verify_twilio_signature(request, form_data)

    call_sid = form_data.get("CallSid")
    customer_phone = form_data.get("From", "unknown")

    if not call_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing CallSid parameter"
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    # Log new call in Supabase calls table
    try:
        supabase = get_supabase_client()
        supabase.table("calls").insert({
            "call_sid": call_sid,
            "business_id": HARDCODED_BUSINESS_ID,
            "customer_phone": customer_phone,
            "started_at": now_iso,
        }).execute()
    except Exception as e:
        logger.error(f"Error inserting call record for CallSid {call_sid}: {e}")

    twiml_content = build_incoming_call_response(
        greeting_text="Thanks for calling, how can I help you today?",
        action_url="/twilio/handle-speech"
    )
    return Response(content=twiml_content, media_type="application/xml")


@router.post("/handle-speech")
async def handle_speech(request: Request, retry: Optional[int] = None):
    """
    Twilio Gather callback for processing speech transcription (SpeechResult).
    Updates call log with ended_at, duration_seconds, transcript, outcome='unresolved'.
    Handles retry if SpeechResult is empty/missing.
    """
    form_data_multi = await request.form()
    form_data = dict(form_data_multi)
    await _verify_twilio_signature(request, form_data)

    call_sid = form_data.get("CallSid")
    speech_result = form_data.get("SpeechResult", "").strip()

    if not call_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing CallSid parameter"
        )

    # Empty speech result fallback logic
    if not speech_result:
        if retry is None or retry < 1:
            # First attempt failed to capture speech: prompt to repeat
            twiml_content = build_retry_speech_response(
                prompt_text="I'm sorry, I didn't catch that. Could you please repeat?",
                action_url="/twilio/handle-speech?retry=1"
            )
            return Response(content=twiml_content, media_type="application/xml")
        else:
            # Second attempt failed to capture speech: gracefully hang up and update call log
            speech_result = "[No speech detected]"

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    duration_seconds = None
    try:
        supabase = get_supabase_client()
        # Query existing call to calculate duration from started_at
        response = supabase.table("calls").select("started_at").eq("call_sid", call_sid).execute()
        if response.data and len(response.data) > 0:
            started_at_str = response.data[0].get("started_at")
            if started_at_str:
                # Parse started_at timestamp
                started_at_dt = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                duration_seconds = max(0, int((now_dt - started_at_dt).total_seconds()))

        # Update call record
        supabase.table("calls").update({
            "ended_at": now_iso,
            "duration_seconds": duration_seconds,
            "transcript": speech_result,
            "outcome": "unresolved",
        }).eq("call_sid", call_sid).execute()
    except Exception as e:
        logger.error(f"Error updating call record for CallSid {call_sid}: {e}")

    if speech_result == "[No speech detected]":
        twiml_content = build_fallback_hangup_response("Let me connect you to someone who can help")
    else:
        twiml_content = build_speech_handled_response(speech_result)

    return Response(content=twiml_content, media_type="application/xml")
