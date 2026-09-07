import logging
import os
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from fastapi import Request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse, Gather

logger = logging.getLogger(__name__)


def validate_twilio_request(request_url: str, params: Dict[str, Any], signature: str) -> bool:
    """
    Validates that an incoming HTTP request was sent by Twilio.
    Supports SKIP_TWILIO_SIGNATURE_VALIDATION env variable for local testing/dev.
    Uses PUBLIC_BASE_URL if configured to reconstruct full URL when running behind proxies/ngrok.
    """
    skip_validation = os.getenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "false").lower() == "true"
    if skip_validation:
        logger.warning("SKIP_TWILIO_SIGNATURE_VALIDATION is active. Skipping Twilio signature validation.")
        return True

    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not auth_token:
        logger.error("TWILIO_AUTH_TOKEN environment variable is missing.")
        return False

    public_base_url = os.getenv("PUBLIC_BASE_URL")
    if public_base_url:
        parsed_base = urlparse(public_base_url)
        parsed_req = urlparse(request_url)
        # Reconstruct request URL with public scheme and host while retaining path and query
        request_url = parsed_req._replace(
            scheme=parsed_base.scheme,
            netloc=parsed_base.netloc
        ).geturl()

    validator = RequestValidator(auth_token)
    return validator.validate(request_url, params, signature)


def build_incoming_call_response(
    greeting_text: str = "Thanks for calling, how can I help you today?",
    action_url: str = "/twilio/handle-speech"
) -> str:
    """
    Generates TwiML response for inbound call entrypoint.
    Plays a greeting and listens for spoken input.
    """
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action_url,
        speech_timeout="auto"
    )
    gather.say(greeting_text)
    response.append(gather)
    # If no speech input is detected by Gather
    response.say("We did not receive any input. Goodbye.")
    response.hangup()
    return str(response)


def build_retry_speech_response(
    prompt_text: str = "I'm sorry, I didn't catch that. Could you please repeat?",
    action_url: str = "/twilio/handle-speech?retry=1"
) -> str:
    """
    Generates TwiML response when speech was empty/unclear on the first attempt.
    """
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action_url,
        speech_timeout="auto"
    )
    gather.say(prompt_text)
    response.append(gather)
    response.say("We did not receive any input. Goodbye.")
    response.hangup()
    return str(response)


def build_speech_handled_response(speech_result: str) -> str:
    """
    Generates TwiML response echoing back the captured speech result and hanging up.
    """
    response = VoiceResponse()
    message = f"I heard you say: {speech_result}. A human will be with you shortly."
    response.say(message)
    response.hangup()
    return str(response)


def build_fallback_hangup_response(
    message: str = "Let me connect you to someone who can help"
) -> str:
    """
    Generates TwiML response for fallback hangup (e.g., repeated empty speech input).
    """
    response = VoiceResponse()
    response.say(message)
    response.hangup()
    return str(response)
