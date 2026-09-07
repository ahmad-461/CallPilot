from unittest.mock import patch, MagicMock
import pytest

from app.services.appointment_service import (
    check_availability,
    create_appointment,
    update_appointment,
    cancel_appointment,
    get_business_info,
    PLACEHOLDER_BUSINESS_ID,
)


@patch("app.services.rag_service.search_knowledge_base")
def test_get_business_info(mock_search):
    mock_search.return_value = [
        {"title": "Hours & Location", "content": "Open Mon-Fri 9-6", "similarity": 0.85}
    ]
    info = get_business_info(query="What are your hours?")
    assert info["business_id"] == PLACEHOLDER_BUSINESS_ID
    assert info["found"] is True
    assert len(info["passages"]) == 1
    assert info["passages"][0]["title"] == "Hours & Location"


@patch("app.services.rag_service.search_knowledge_base")
def test_get_business_info_no_match(mock_search):
    mock_search.return_value = []
    info = get_business_info(query="Do you offer pet grooming?")
    assert info["business_id"] == PLACEHOLDER_BUSINESS_ID
    assert info["found"] is False
    assert "don't have that information" in info["message"]


@patch("app.services.appointment_service.get_supabase_client")
def test_check_availability_free(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

    res = check_availability("2025-05-10", "10:00")
    assert res["available"] is True
    assert "is available" in res["message"]


@patch("app.services.appointment_service.get_supabase_client")
def test_check_availability_conflict(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase
    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {
            "id": "appt-1",
            "start_time": "2025-05-10T10:00:00+00:00",
            "end_time": "2025-05-10T10:30:00+00:00",
        }
    ]

    res = check_availability("2025-05-10", "10:15")
    assert res["available"] is False
    assert "already booked" in res["message"]


@patch("app.services.appointment_service.get_supabase_client")
def test_create_appointment_success(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    # Customers lookup -> customer exists
    mock_cust_table = MagicMock()
    mock_cust_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "cust-123", "name": "Jane Doe"}
    ]

    # Appointments availability check -> no overlapping appointments
    mock_appt_table = MagicMock()
    mock_appt_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    mock_appt_table.insert.return_value.execute.return_value.data = [
        {"id": "appt-456", "status": "booked"}
    ]

    def table_side_effect(table_name):
        if table_name == "customers":
            return mock_cust_table
        if table_name == "appointments":
            return mock_appt_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    res = create_appointment("+15551234567", "2025-05-10", "14:00", customer_name="Jane Doe")
    assert res["success"] is True
    assert res["appointment_id"] == "appt-456"


@patch("app.services.appointment_service.get_supabase_client")
def test_create_appointment_conflict(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_cust_table = MagicMock()
    mock_cust_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "cust-123"}
    ]

    mock_appt_table = MagicMock()
    mock_appt_table.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "appt-existing", "start_time": "2025-05-10T14:00:00+00:00", "end_time": "2025-05-10T14:30:00+00:00"}
    ]

    def table_side_effect(table_name):
        if table_name == "customers":
            return mock_cust_table
        if table_name == "appointments":
            return mock_appt_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    res = create_appointment("+15551234567", "2025-05-10", "14:00")
    assert res["success"] is False
    assert res["error"] == "slot_unavailable"


@patch("app.services.appointment_service.get_supabase_client")
def test_update_appointment_success(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_table = MagicMock()
    # First query retrieves existing appointment
    mock_table.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "appt-123", "business_id": PLACEHOLDER_BUSINESS_ID}
    ]
    # Second query checks other appointments -> none
    mock_table.select.return_value.eq.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
    # Update execution returns updated record
    mock_table.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": "appt-123"}
    ]

    mock_supabase.table.return_value = mock_table

    res = update_appointment("appt-123", "2025-05-11", "11:00")
    assert res["success"] is True
    assert res["appointment_id"] == "appt-123"


@patch("app.services.appointment_service.get_supabase_client")
def test_cancel_appointment_success(mock_get_supabase):
    mock_supabase = MagicMock()
    mock_get_supabase.return_value = mock_supabase

    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.execute.return_value.data = [{"id": "appt-123"}]
    mock_table.update.return_value.eq.return_value.execute.return_value.data = [{"id": "appt-123", "status": "cancelled"}]
    mock_supabase.table.return_value = mock_table

    res = cancel_appointment("appt-123")
    assert res["success"] is True
    assert "cancelled" in res["message"]
