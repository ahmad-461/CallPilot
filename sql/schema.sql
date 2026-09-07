-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create custom ENUM types
CREATE TYPE appointment_status AS ENUM (
    'booked',
    'cancelled',
    'rescheduled'
);

CREATE TYPE call_outcome AS ENUM (
    'booked',
    'cancelled',
    'info-only',
    'escalated',
    'unresolved'
);

-- 1. Businesses Table
CREATE TABLE IF NOT EXISTS businesses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    hours JSONB,
    greeting_message TEXT,
    services JSONB,
    pricing JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Customers Table
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number TEXT NOT NULL UNIQUE,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Appointments Table
CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status appointment_status NOT NULL DEFAULT 'booked',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT check_end_after_start CHECK (end_time > start_time),
    CONSTRAINT no_overlapping_appointments EXCLUDE USING gist (
        business_id WITH =,
        tstzrange(start_time, end_time) WITH &&
    ) WHERE (status = 'booked')
);

-- 4. Calls Table
CREATE TABLE IF NOT EXISTS calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    customer_phone TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    transcript TEXT,
    summary TEXT,
    outcome call_outcome,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Knowledge Base Documents Table
CREATE TABLE IF NOT EXISTS knowledge_base_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_appointments_business_start ON appointments(business_id, start_time);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone_number);
CREATE INDEX IF NOT EXISTS idx_calls_business ON calls(business_id);
CREATE INDEX IF NOT EXISTS idx_kb_docs_business ON knowledge_base_documents(business_id);
