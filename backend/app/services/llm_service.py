import os
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from google import genai
from google.genai import types

from app.services import appointment_service

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
PLACEHOLDER_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"

SYSTEM_PROMPT = """You are a friendly, natural-sounding AI phone receptionist for CallPilot Salon & Spa.
Your primary job is to help callers book, reschedule, or cancel appointments, and answer questions about business hours, services, location, and pricing.

Key guidelines:
1. Speak naturally, politely, and concisely as a human receptionist over the phone.
2. Normalize all spoken dates and times into YYYY-MM-DD and HH:MM (24-hour) format before invoking any tool functions.
3. Always verbally confirm appointment details (e.g., date, time, service) with the caller before calling tools that create, update, or cancel appointments.
4. Use get_business_info for any questions regarding business hours, services, pricing, or location.
5. Do not invent appointment availability or business information without checking tools.
6. When the caller's request has been fully addressed and they say goodbye or indicate they are done (e.g. "that's all", "thank you goodbye", "bye"), include the marker [CALL_COMPLETE] at the end of your response.
"""

FUNCTIONS = [
    types.FunctionDeclaration(
        name="check_availability",
        description="Check if a specific date and time slot is available for an appointment.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "date": types.Schema(type=types.Type.STRING, description="Date in YYYY-MM-DD format"),
                "time": types.Schema(type=types.Type.STRING, description="Time in HH:MM format (24-hour)"),
                "business_id": types.Schema(type=types.Type.STRING, description="Business UUID (optional)"),
            },
            required=["date", "time"],
        ),
    ),
    types.FunctionDeclaration(
        name="create_appointment",
        description="Book a new appointment for a customer after verbal confirmation.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "customer_phone": types.Schema(type=types.Type.STRING, description="Customer phone number"),
                "date": types.Schema(type=types.Type.STRING, description="Date in YYYY-MM-DD format"),
                "time": types.Schema(type=types.Type.STRING, description="Time in HH:MM format (24-hour)"),
                "customer_name": types.Schema(type=types.Type.STRING, description="Customer name (optional)"),
                "business_id": types.Schema(type=types.Type.STRING, description="Business UUID (optional)"),
            },
            required=["customer_phone", "date", "time"],
        ),
    ),
    types.FunctionDeclaration(
        name="update_appointment",
        description="Reschedule an existing appointment to a new date and time.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "appointment_id": types.Schema(type=types.Type.STRING, description="Existing appointment UUID"),
                "new_date": types.Schema(type=types.Type.STRING, description="New date in YYYY-MM-DD format"),
                "new_time": types.Schema(type=types.Type.STRING, description="New time in HH:MM format (24-hour)"),
            },
            required=["appointment_id", "new_date", "new_time"],
        ),
    ),
    types.FunctionDeclaration(
        name="cancel_appointment",
        description="Cancel an existing appointment.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "appointment_id": types.Schema(type=types.Type.STRING, description="Appointment UUID to cancel"),
            },
            required=["appointment_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_business_info",
        description="Get business information such as hours, services, pricing, or location.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "business_id": types.Schema(type=types.Type.STRING, description="Business UUID (optional)"),
                "query": types.Schema(type=types.Type.STRING, description="Specific caller query or topic (optional)"),
            },
        ),
    ),
]

TOOLS = [types.Tool(function_declarations=FUNCTIONS)]


def get_gemini_client() -> genai.Client:
    """Initializes and returns the Gemini client using GEMINI_API_KEY env var."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY environment variable is not set!")
        # Fallback to LLM_API_KEY if set for backward compatibility
        api_key = os.getenv("LLM_API_KEY", "")

    return genai.Client(api_key=api_key)


class ConversationSession:
    def __init__(self, call_sid: str, customer_phone: str):
        self.call_sid = call_sid
        self.customer_phone = customer_phone
        self.history: List[types.Content] = []
        self.tools_called: Set[str] = set()
        self.is_complete: bool = False


# In-memory store holding message history for each active call (keyed by call_sid)
_CONVERSATIONS: Dict[str, ConversationSession] = {}


def get_or_create_session(call_sid: str, customer_phone: str) -> ConversationSession:
    """Retrieves or creates an in-memory session for the given call_sid."""
    if call_sid not in _CONVERSATIONS:
        _CONVERSATIONS[call_sid] = ConversationSession(call_sid, customer_phone)
    return _CONVERSATIONS[call_sid]


def get_session(call_sid: str) -> Optional[ConversationSession]:
    """Retrieves an existing in-memory session for call_sid, if present."""
    return _CONVERSATIONS.get(call_sid)


def clear_session(call_sid: str) -> None:
    """Clears and removes the conversation history for call_sid."""
    if call_sid in _CONVERSATIONS:
        del _CONVERSATIONS[call_sid]


def compute_call_outcome(tools_called: Set[str]) -> str:
    """
    Determines call outcome based on priority:
    booked > cancelled > info-only > unresolved
    """
    if "create_appointment" in tools_called:
        return "booked"
    elif "cancel_appointment" in tools_called:
        return "cancelled"
    elif "get_business_info" in tools_called or "check_availability" in tools_called or "update_appointment" in tools_called:
        return "info-only"
    return "unresolved"


def execute_tool_call(func_name: str, func_args: Dict[str, Any], default_phone: str) -> Dict[str, Any]:
    """Executes the tool function requested by Gemini and returns the result dict."""
    logger.info(f"Executing tool call '{func_name}' with args: {func_args}")

    if func_name == "check_availability":
        return appointment_service.check_availability(
            date=func_args.get("date", ""),
            time=func_args.get("time", ""),
            business_id=func_args.get("business_id") or PLACEHOLDER_BUSINESS_ID,
        )
    elif func_name == "create_appointment":
        phone = func_args.get("customer_phone") or default_phone
        return appointment_service.create_appointment(
            customer_phone=phone,
            date=func_args.get("date", ""),
            time=func_args.get("time", ""),
            business_id=func_args.get("business_id") or PLACEHOLDER_BUSINESS_ID,
            customer_name=func_args.get("customer_name"),
        )
    elif func_name == "update_appointment":
        return appointment_service.update_appointment(
            appointment_id=func_args.get("appointment_id", ""),
            new_date=func_args.get("new_date", ""),
            new_time=func_args.get("new_time", ""),
        )
    elif func_name == "cancel_appointment":
        return appointment_service.cancel_appointment(
            appointment_id=func_args.get("appointment_id", ""),
        )
    elif func_name == "get_business_info":
        return appointment_service.get_business_info(
            business_id=func_args.get("business_id") or PLACEHOLDER_BUSINESS_ID,
            query=func_args.get("query"),
        )
    else:
        logger.error(f"Unknown tool function: {func_name}")
        return {"error": f"Unknown tool function: {func_name}"}


def process_conversation_turn(
    call_sid: str,
    customer_phone: str,
    user_speech: str,
    client: Optional[genai.Client] = None,
) -> Tuple[str, bool, str]:
    """
    Processes a conversation turn:
    1. Appends caller speech to call history
    2. Calls Gemini with tool configuration
    3. Handles and resolves any tool call requests sequentially
    4. Returns (response_text, is_complete, call_outcome)
    """
    session = get_or_create_session(call_sid, customer_phone)

    # Append user speech turn
    user_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_speech)],
    )
    session.history.append(user_content)

    if client is None:
        client = get_gemini_client()

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=TOOLS,
        temperature=0.7,
    )

    max_turns = 5
    turn_count = 0

    while turn_count < max_turns:
        turn_count += 1
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=session.history,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini API call failed for CallSid {call_sid}: {e}")
            fallback_msg = "I'm sorry, I'm having trouble processing that right now. Could you please rephrase?"
            session.history.append(types.Content(role="model", parts=[types.Part.from_text(text=fallback_msg)]))
            return fallback_msg, False, compute_call_outcome(session.tools_called)

        # Retrieve candidate content
        candidate_content = None
        if response.candidates and len(response.candidates) > 0:
            candidate_content = response.candidates[0].content

        if not candidate_content:
            fallback_msg = "I'm sorry, I didn't quite catch that. Could you repeat?"
            return fallback_msg, False, compute_call_outcome(session.tools_called)

        # Append model content to session history
        session.history.append(candidate_content)

        # Check for function calls
        function_calls = []
        for part in candidate_content.parts:
            if part.function_call:
                function_calls.append(part.function_call)

        if function_calls:
            # Execute tool calls and feed results back to Gemini
            tool_response_parts = []
            for fc in function_calls:
                func_name = fc.name
                func_args = dict(fc.args) if fc.args else {}
                session.tools_called.add(func_name)

                result = execute_tool_call(func_name, func_args, customer_phone)

                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=func_name,
                        response={"result": result},
                    )
                )

            # Append function response turn from user role
            func_resp_content = types.Content(role="user", parts=tool_response_parts)
            session.history.append(func_resp_content)
            # Loop back to get Gemini's natural language response
            continue

        # No function calls -> extract text response
        text_response = ""
        for part in candidate_content.parts:
            if part.text:
                text_response += part.text

        text_response = text_response.strip()

        # Check for end-of-call marker
        if "[CALL_COMPLETE]" in text_response:
            session.is_complete = True
            text_response = text_response.replace("[CALL_COMPLETE]", "").strip()

        outcome = compute_call_outcome(session.tools_called)
        return text_response, session.is_complete, outcome

    # Fallback if max tool turns exceeded
    fallback_msg = "Thank you for calling. I have processed your request."
    outcome = compute_call_outcome(session.tools_called)
    return fallback_msg, session.is_complete, outcome
