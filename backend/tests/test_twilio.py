from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.twilio_service import (
    validate_twilio_request,
    build_incoming_call_response,
    build_retry_speech_response,
    build_speech_handled_response,
    build_fallback_hangup_response,
)

client = TestClient(app)


def test_twilio_service_build_twiml():
    twiml_inc = build_incoming_call_response("Hello test", "/twilio/handle-speech")
    assert "<Say>Hello test</Say>" in twiml_inc
    assert '<Gather action="/twilio/handle-speech"' in twiml_inc

    twiml_retry = build_retry_speech_response("Repeat please", "/twilio/handle-speech?retry=1")
    assert "<Say>Repeat please</Say>" in twiml_retry
    assert '<Gather action="/twilio/handle-speech?retry=1"' in twiml_retry

    twiml_handled = build_speech_handled_response("I want to book an appointment")
    assert "I heard you say: I want to book an appointment" in twiml_handled
    assert "<Hangup" in twiml_handled

    twiml_fallback = build_fallback_hangup_response("Connecting to agent")
    assert "<Say>Connecting to agent</Say>" in twiml_fallback
    assert "<Hangup" in twiml_fallback


def test_validate_twilio_request_skip(monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "true")
    assert validate_twilio_request("http://test.com", {}, "dummy_sig") is True


def test_validate_twilio_request_invalid(monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "false")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake_auth_token")
    assert validate_twilio_request("http://test.com", {"CallSid": "123"}, "invalid_sig") is False


@patch("app.routes.twilio.get_supabase_client")
def test_incoming_call_endpoint(mock_get_supabase, monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "true")
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    response = client.post(
        "/twilio/incoming-call",
        data={"CallSid": "CA12345", "From": "+1234567890"}
    )

    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    assert "Thanks for calling, how can I help you today?" in response.text
    assert '<Gather action="/twilio/handle-speech"' in response.text

    mock_supabase.table.assert_called_with("calls")
    mock_supabase.table().insert.assert_called_once()
    insert_data = mock_supabase.table().insert.call_args[0][0]
    assert insert_data["call_sid"] == "CA12345"
    assert insert_data["customer_phone"] == "+1234567890"


@patch("app.routes.twilio.get_supabase_client")
def test_handle_speech_success(mock_get_supabase, monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "true")
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table().select().eq().execute.return_value.data = [
        {"started_at": "2026-01-01T12:00:00+00:00"}
    ]

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA12345", "SpeechResult": "I would like to book a haircut"}
    )

    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    assert "I heard you say: I would like to book a haircut" in response.text

    mock_supabase.table().update.assert_called_once()
    update_data = mock_supabase.table().update.call_args[0][0]
    assert update_data["transcript"] == "I would like to book a haircut"
    assert update_data["outcome"] == "unresolved"


@patch("app.routes.twilio.get_supabase_client")
def test_handle_speech_empty_first_attempt(mock_get_supabase, monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "true")

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA12345", "SpeechResult": ""}
    )

    assert response.status_code == 200
    assert "I'm sorry, I didn't catch that. Could you please repeat?" in response.text
    assert 'action="/twilio/handle-speech?retry=1"' in response.text


@patch("app.routes.twilio.get_supabase_client")
def test_handle_speech_empty_retry_attempt(mock_get_supabase, monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "true")
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table().select().eq().execute.return_value.data = [
        {"started_at": "2026-01-01T12:00:00+00:00"}
    ]

    response = client.post(
        "/twilio/handle-speech?retry=1",
        data={"CallSid": "CA12345", "SpeechResult": ""}
    )

    assert response.status_code == 200
    assert "Let me connect you to someone who can help" in response.text

    mock_supabase.table().update.assert_called_once()
    update_data = mock_supabase.table().update.call_args[0][0]
    assert update_data["transcript"] == "[No speech detected]"
    assert update_data["outcome"] == "unresolved"


def test_handle_speech_unauthorized(monkeypatch):
    monkeypatch.setenv("SKIP_TWILIO_SIGNATURE_VALIDATION", "false")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret_token")

    response = client.post(
        "/twilio/handle-speech",
        data={"CallSid": "CA12345", "SpeechResult": "hello"}
    )
    assert response.status_code == 403
