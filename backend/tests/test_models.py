import pytest
from app.models import (
    Business,
    Customer,
    Appointment,
    Call,
    KnowledgeBaseDocument,
    AppointmentStatus,
    CallOutcome,
)


def test_models_import_and_instantiation():
    """Verify that SQLAlchemy models can be instantiated properly."""
    biz = Business(name="Test Spa")
    assert biz.name == "Test Spa"

    cust = Customer(phone_number="+15551234567", name="Jane Doe")
    assert cust.phone_number == "+15551234567"

    appt = Appointment(status=AppointmentStatus.BOOKED)
    assert appt.status == AppointmentStatus.BOOKED

    call = Call(customer_phone="+15551234567", outcome=CallOutcome.INFO_ONLY)
    assert call.outcome == CallOutcome.INFO_ONLY

    kb = KnowledgeBaseDocument(title="Services", content="Massage and Facial")
    assert kb.title == "Services"
