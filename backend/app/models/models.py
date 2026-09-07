import enum
import uuid
from datetime import datetime
from typing import Optional, Any, List
from sqlalchemy import (
    String,
    Text,
    Integer,
    ForeignKey,
    DateTime,
    Enum,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AppointmentStatus(str, enum.Enum):
    BOOKED = "booked"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class CallOutcome(str, enum.Enum):
    BOOKED = "booked"
    CANCELLED = "cancelled"
    INFO_ONLY = "info-only"
    ESCALATED = "escalated"
    UNRESOLVED = "unresolved"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    hours: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    greeting_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    services: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    pricing: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment", back_populates="business", cascade="all, delete-orphan"
    )
    calls: Mapped[List["Call"]] = relationship(
        "Call", back_populates="business", cascade="all, delete-orphan"
    )
    knowledge_base_documents: Mapped[List["KnowledgeBaseDocument"]] = relationship(
        "KnowledgeBaseDocument", back_populates="business", cascade="all, delete-orphan"
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment", back_populates="customer", cascade="all, delete-orphan"
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_sid: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            name="appointment_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=AppointmentStatus.BOOKED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business", back_populates="appointments")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="appointments")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    customer_phone: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[CallOutcome]] = mapped_column(
        Enum(
            CallOutcome,
            name="call_outcome",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business", back_populates="calls")


class KnowledgeBaseDocument(Base):
    __tablename__ = "knowledge_base_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship("Business", back_populates="knowledge_base_documents")
