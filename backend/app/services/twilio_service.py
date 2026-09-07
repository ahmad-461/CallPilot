import os
import logging
from typing import Dict, Any
from fastapi import Request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse, Gather

logger = logging.getLogger(__name__)


def is_signature_validation_skipped() -> bool:
    """Checks whether Twilio signature validation should be bypassed."""
    skip_env = os.getenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "false").strip().lower()
    return skip_env in ("true", "1", "yes")


def validate_twilio_request(request: Request, params: Dict[str, Any]) -> bool:
    """
    Validates that an incoming HTTP request originated from Twilio.
    Uses X-Twilio-Signature header, TWILIO_AUTH_TOKEN, and request URL/params.
    Supports PUBLIC_BASE_URL reconstruction and SKIP_TWILIO_SIGNATURE_VALIDATION bypass.
    """
    if is_signature_validation_skipped():
        logger.warning("SKIP_TWILIO_SIGNATURE_VALIDATION is active! Bypassing signature validation.")
        return True

    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    signature = request.headers.get("X-Twilio-Signature")
    if not signature or not auth_token:
        return False

    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
    if public_base_url:
        path = request.url.path
        query = f"?{request.url.query}" if request.url.query else ""
        url = f"{public_base_url.rstrip('/')}{path}{query}"
    else:
        url = str(request.url)

    validator = RequestValidator(auth_token)
    return validator.validate(url, params, signature)


def build_initial_call_twiml() -> str:
    """
    Builds TwiML response for initial call entrypoint:
    Greets caller and gathers speech input.
    """
    response = VoiceResponse()
    response.say("Thanks for calling, how can I help you today?")
    gather = Gather(input="speech", action="/twilio/handle-speech", speech_timeout="auto")
    response.append(gather)
    return str(response)


def build_speech_response_twiml(speech_result: str) -> str:
    """
    Builds TwiML response when caller speech is successfully received:
    Echoes back speech and hangs up.
    """
    response = VoiceResponse()
    response.say(f"I heard you say: {speech_result}. A human will be with you shortly.")
    response.hangup()
    return str(response)


def build_retry_twiml() -> str:
    """
    Builds TwiML response when first speech gather attempt is empty:
    Asks caller to repeat and re-gathers speech with retry=1 parameter.
    """
    response = VoiceResponse()
    response.say("I'm sorry, I didn't catch that. Could you please repeat?")
    gather = Gather(input="speech", action="/twilio/handle-speech?retry=1", speech_timeout="auto")
    response.append(gather)
    return str(response)


def build_fallback_twiml() -> str:
    """
    Builds TwiML response when second speech gather attempt is empty:
    Apologizes, offers transfer, and hangs up.
    """
    response = VoiceResponse()
    response.say("Let me connect you to someone who can help")
    response.hangup()
    return str(response)
