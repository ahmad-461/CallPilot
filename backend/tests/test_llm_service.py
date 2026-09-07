from unittest.mock import patch, MagicMock
import pytest
from google.genai import types

from app.services.llm_service import (
    TurnResult,
    compute_call_outcome,
    get_or_create_session,
    get_session,
    clear_session,
    execute_tool_call,
    process_conversation_turn,
)


def test_compute_call_outcome():
    assert compute_call_outcome({"create_appointment", "get_business_info"}) == "booked"
    assert compute_call_outcome({"cancel_appointment", "get_business_info"}) == "cancelled"
    assert compute_call_outcome({"get_business_info", "check_availability"}) == "info-only"
    assert compute_call_outcome(set()) == "unresolved"
    # Both create and cancel (reschedule scenario) -> booked
    assert compute_call_outcome({"create_appointment", "cancel_appointment"}) == "booked"


def test_session_management():
    call_sid = "CA123456789"
    phone = "+15551234567"

    session = get_or_create_session(call_sid, phone)
    assert session.call_sid == call_sid
    assert session.customer_phone == phone

    fetched = get_session(call_sid)
    assert fetched is session

    clear_session(call_sid)
    assert get_session(call_sid) is None


@patch("app.services.llm_service.appointment_service")
def test_execute_tool_call(mock_appt_service):
    mock_appt_service.check_availability.return_value = {"available": True}
    res = execute_tool_call("check_availability", {"date": "2025-05-10", "time": "10:00"}, "+15551234567")
    assert res == {"available": True}
    mock_appt_service.check_availability.assert_called_once_with(
        date="2025-05-10",
        time="10:00",
        business_id="00000000-0000-0000-0000-000000000000",
    )


def test_process_conversation_turn_with_mock_client():
    call_sid = "CA99999"
    phone = "+15559999999"

    mock_client = MagicMock()
    mock_part = types.Part.from_text(text="I can help you with that! [CALL_COMPLETE]")
    mock_content = types.Content(role="model", parts=[mock_part])
    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response

    result = process_conversation_turn(
        call_sid=call_sid,
        customer_phone=phone,
        user_speech="What are your hours?",
        client=mock_client,
    )

    assert isinstance(result, TurnResult)
    assert result.response_text == "I can help you with that!"
    assert result.is_complete is True
    assert result.outcome == "unresolved"
    assert result.is_handoff is False
    assert result.handoff_reason is None

    clear_session(call_sid)


def test_process_conversation_turn_explicit_handoff():
    call_sid = "CA_handoff_1"
    phone = "+15559999999"

    mock_client = MagicMock()
    mock_part = types.Part.from_text(text="Connecting you to an agent now. [HANDOFF:explicit_request]")
    mock_content = types.Content(role="model", parts=[mock_part])
    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response

    result = process_conversation_turn(
        call_sid=call_sid,
        customer_phone=phone,
        user_speech="I want to speak with a representative",
        client=mock_client,
    )

    assert result.response_text == "Connecting you to an agent now."
    assert result.is_complete is True
    assert result.outcome == "escalated"
    assert result.is_handoff is True
    assert result.handoff_reason == "explicit_request"

    clear_session(call_sid)


def test_process_conversation_turn_api_error_handoff():
    call_sid = "CA_handoff_err"
    phone = "+15559999999"

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("Gemini Service Unavailable")

    result = process_conversation_turn(
        call_sid=call_sid,
        customer_phone=phone,
        user_speech="Hello",
        client=mock_client,
    )

    assert result.response_text == "Let me connect you to someone who can help."
    assert result.is_complete is True
    assert result.outcome == "escalated"
    assert result.is_handoff is True
    assert result.handoff_reason == "tool_error"

    clear_session(call_sid)
