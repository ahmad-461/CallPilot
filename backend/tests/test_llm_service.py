from unittest.mock import patch, MagicMock
import pytest
from google.genai import types

from app.services.llm_service import (
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

    text, is_complete, outcome = process_conversation_turn(
        call_sid=call_sid,
        customer_phone=phone,
        user_speech="What are your hours?",
        client=mock_client,
    )

    assert text == "I can help you with that!"
    assert is_complete is True
    assert outcome == "unresolved"

    clear_session(call_sid)
