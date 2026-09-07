import os
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_service import TurnResult
from app.services.twilio_service import (
    validate_twilio_request,
    build_initial_call_twiml,
    build_speech_response_twiml,
    build_retry_twiml,
    build_fallback_twiml,
    build_transfer_twiml,
    build_no_agent_twiml,
)

client = TestClient(app)


def test_twiml_builders():
    """Verify that TwiML response string builders produce expected XML elements."""
    initial_xml = build_initial_call_twiml()
    assert "<Say>Thanks for calling, how can I help you today?</Say>" in initial_xml
    assert 'action="/twilio/handle-speech"' in initial_xml
    assert 'input="speech"' in initial_xml

    speech_ongoing_xml = build_speech_response_twiml("We are open 9am to 6pm.", is_complete=False)
    assert "<Say>We are open 9am to 6pm.</Say>" in speech_ongoing_xml
    assert 'action="/twilio/handle-speech"' in speech_ongoing_xml

    speech_complete_xml = build_speech_response_twiml("You are booked for tomorrow at 2 PM. Goodbye!", is_complete=True)
    assert "<Say>You are booked for tomorrow at 2 PM. Goodbye!</Say>" in speech_complete_xml
    assert "<Hangup" in speech_complete_xml

    retry_xml = build_retry_twiml()
    assert "<Say>I'm sorry, I didn't catch that. Could you please repeat?</Say>" in retry_xml
    assert 'action="/twilio/handle-speech?retry=1"' in retry_xml

    fallback_xml = build_fallback_twiml()
    assert "<Say>Let me connect you to someone who can help</Say>" in fallback_xml
    assert "<Hangup" in fallback_xml

    transfer_xml = build_transfer_twiml("+15559876543", "Hold on while I connect you.")
    assert "<Say>Hold on while I connect you.</Say>" in transfer_xml
    assert '<Dial action="/twilio/dial-status" method="POST">' in transfer_xml
    assert "+15559876543</Dial>" in transfer_xml

    no_agent_xml = build_no_agent_twiml()
    assert "<Say>I'm sorry, no one is available to take your call right now. Please try again later.</Say>" in no_agent_xml
    assert "<Hangup" in no_agent_xml


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "false", "TWILIO_AUTH_TOKEN": "testtoken"})
def test_signature_validation():
    """Verify signature validation with bypass disabled."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = None  # No signature header
    assert not validate_twilio_request(mock_request, {})


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
def test_signature_validation_bypass():
    """Verify signature validation bypass when SKIP_TWILIO_SIGNATURE_VALIDATION is true."""
    mock_request = MagicMock()
    assert validate_twilio_request(mock_request, {}) is True


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "false"})
def test_incoming_call_forbidden_without_signature():
    """Incoming call request without valid signature returns 403 Forbidden when bypass is false."""
    response = client.post("/twilio/incoming-call", data={"CallSid": "CA12345", "From": "+15551234567"})
    assert response.status_code == 403


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
@patch("app.routes.twilio.get_supabase_client")
def test_incoming_call_success(mock_get_supabase):
    """Incoming call request returns valid greeting TwiML and attempts call logging."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    response = client.post("/twilio/incoming-call", data={"CallSid": "CA12345", "From": "+15551234567"})
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>Thanks for calling, how can I help you today?</Say>" in response.text
    mock_supabase.table.assert_called_with("calls")


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
@patch("app.routes.twilio.get_supabase_client")
@patch("app.routes.twilio.llm_service")
def test_handle_speech_with_result_ongoing(mock_llm, mock_get_supabase):
    """Handle speech callback processes speech through LLM and returns gather TwiML for ongoing call."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"started_at": "2025-01-01T00:00:00+00:00", "transcript": None}
    ]
    mock_get_supabase.return_value = mock_supabase

    mock_llm.process_conversation_turn.return_value = TurnResult(
        response_text="We are open Monday through Friday from 9 AM to 6 PM.",
        is_complete=False,
        outcome="info-only",
        is_handoff=False,
        handoff_reason=None,
    )

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA12345", "From": "+15551234567", "SpeechResult": "What are your business hours?"},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>We are open Monday through Friday from 9 AM to 6 PM.</Say>" in response.text
    assert 'action="/twilio/handle-speech"' in response.text


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
@patch("app.routes.twilio.get_supabase_client")
@patch("app.routes.twilio.llm_service")
def test_handle_speech_with_result_complete(mock_llm, mock_get_supabase):
    """Handle speech callback processes speech through LLM and hangs up when conversation complete."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"started_at": "2025-01-01T00:00:00+00:00", "transcript": None}
    ]
    mock_get_supabase.return_value = mock_supabase

    mock_llm.process_conversation_turn.return_value = TurnResult(
        response_text="You are all set for 2 PM tomorrow! Thank you for calling.",
        is_complete=True,
        outcome="booked",
        is_handoff=False,
        handoff_reason=None,
    )

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA12345", "From": "+15551234567", "SpeechResult": "Sounds great, thanks!"},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>You are all set for 2 PM tomorrow! Thank you for calling.</Say>" in response.text
    assert "<Hangup" in response.text
    mock_llm.clear_session.assert_called_once_with("CA12345")


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
@patch("app.routes.twilio.get_supabase_client")
def test_handle_speech_empty_first_attempt(mock_get_supabase):
    """Handle speech with empty SpeechResult on first attempt prompts retry without logging DB update."""
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA12345", "SpeechResult": ""},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>I'm sorry, I didn't catch that. Could you please repeat?</Say>" in response.text
    assert 'action="/twilio/handle-speech?retry=1"' in response.text


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
@patch("app.routes.twilio.get_supabase_client")
def test_handle_speech_empty_second_attempt(mock_get_supabase):
    """Handle speech with empty SpeechResult on second attempt (retry=1) hangs up and updates DB."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_supabase.return_value = mock_supabase

    response = client.post(
        "/twilio/handle-speech?retry=1",
        data={"CallSid": "CA12345", "SpeechResult": ""},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>Let me connect you to someone who can help</Say>" in response.text
    assert "<Hangup" in response.text


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true", "HUMAN_AGENT_PHONE_NUMBER": "+15559876543"})
@patch("app.routes.twilio.get_supabase_client")
@patch("app.routes.twilio.llm_service")
def test_handle_speech_handoff_with_agent_configured(mock_llm, mock_get_supabase):
    """Handle speech returning handoff signal transfers call via <Dial> to agent phone number."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"started_at": "2025-01-01T00:00:00+00:00", "transcript": None}
    ]
    mock_get_supabase.return_value = mock_supabase

    mock_llm.process_conversation_turn.return_value = TurnResult(
        response_text="Let me connect you to someone who can help.",
        is_complete=True,
        outcome="escalated",
        is_handoff=True,
        handoff_reason="explicit_request",
    )

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA_handoff_call", "From": "+15551234567", "SpeechResult": "Can I speak to a person?"},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>Let me connect you to someone who can help.</Say>" in response.text
    assert '<Dial action="/twilio/dial-status" method="POST">+15559876543</Dial>' in response.text
    mock_llm.clear_session.assert_called_once_with("CA_handoff_call")


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true", "HUMAN_AGENT_PHONE_NUMBER": ""})
@patch("app.routes.twilio.get_supabase_client")
@patch("app.routes.twilio.llm_service")
def test_handle_speech_handoff_without_agent_configured(mock_llm, mock_get_supabase):
    """Handle speech returning handoff signal falls back gracefully when HUMAN_AGENT_PHONE_NUMBER is unconfigured."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_supabase.return_value = mock_supabase

    mock_llm.process_conversation_turn.return_value = TurnResult(
        response_text="Let me connect you to someone who can help.",
        is_complete=True,
        outcome="escalated",
        is_handoff=True,
        handoff_reason="explicit_request",
    )

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA_no_agent_call", "From": "+15551234567", "SpeechResult": "Agent please"},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Say>I'm sorry, no one is available to take your call right now. Please try again later.</Say>" in response.text
    assert "<Hangup" in response.text


@patch.dict(os.environ, {"SKIP_TWILIO_SIGNATURE_VALIDATION": "true"})
@patch("app.routes.twilio.get_supabase_client")
def test_dial_status_callback(mock_get_supabase):
    """Dial status callback endpoint updates call record in Supabase with status details."""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"transcript": "User: Representative\nAgent: Connecting you.", "handoff_reason": "explicit_request"}
    ]
    mock_get_supabase.return_value = mock_supabase

    response = client.post(
        "/twilio/dial-status",
        data={"CallSid": "CA_handoff_call", "DialCallStatus": "completed", "DialCallDuration": "45"},
    )
    assert response.status_code == 200
    assert "text/xml" in response.headers["content-type"]
    assert "<Response/>" in response.text
    mock_supabase.table.assert_called_with("calls")
