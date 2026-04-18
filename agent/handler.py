"""
Voice-first nurse dispatch agent (Uber x Zocdoc for home health).

This handler runs the intake conversation:
  - collects patient profile, situation, preferences via LLM tool calls
  - matches against mock nurses and surfaces ranked candidates
  - books the selected nurse at the requested time

Every tool mutates a single `state` blob in context, then emits a
CustomEvent("state_update") so the browser can render a mirrored view.
"""

import json
import math
from typing import Optional

from primfunctions.events import (
    Event,
    StartEvent,
    TextEvent,
    StopEvent,
    TextToSpeechEvent,
    CustomEvent,
)
from primfunctions.context import Context
from primfunctions.completions import (
    CacheBreakpoint,
    SystemMessage,
    ToolResultMessage,
    UserMessage,
    configure_provider,
    deserialize_conversation,
    generate_chat_completion,
)
import baseten


# ---------- System prompt ----------

SYSTEM_PROMPT = """You are a warm, calm dispatcher at a 24/7 home-health nursing service.
You are on a voice call with someone who needs a nurse at their home. Your job is to
(a) gather the REQUIRED intake, (b) run search_nurses once you have it, and (c) book
the nurse the caller picks.

REQUIRED intake — you MUST have ALL FIVE before calling search_nurses. If any are
missing, your next turn MUST ask about the first missing one. Do NOT call search_nurses
while anything is missing; the tool will refuse.

  1. patient.age            (ask: "how old are you?" / "how old is the patient?")
  2. patient.livesAlone     (ask: "are you alone right now?" / "is anyone with you?")
  3. situation.description  (1–2 sentence plain-language summary of what happened)
  4. situation.issueTags    (at least one tag from the ISSUE TAGS list below)
  5. situation.urgency      ("now" / "soon" / "scheduled")

OPTIONAL intake — only ask if the caller volunteers OR it's clearly relevant:
  - patient.name
  - preferences.language
  - preferences.genderPref

CONVERSATION RULES:
- Keep every reply SHORT (one sentence, one question). Phone-call cadence, no lists.
- ASK ONE QUESTION AT A TIME. Never stack multiple questions.
- When a single user turn gives you multiple facts (e.g. "I'm 62 and I live alone"),
  emit MULTIPLE TOOL CALLS IN PARALLEL in one response — don't serialize them.
- After each tool call, read the `missingRequired` field in the tool result. If it is
  non-empty, your very next sentence must ask about the first item in that list.
- Only when `missingRequired` is empty should you call search_nurses.
- When search_nurses returns, tell the caller briefly: "I found [N] nurses nearby, the
  closest is about [X] minutes away. Tap one on your screen to book." Don't read the
  full list aloud — the UI shows it.
- If the caller sends "[user-edit] path=value", acknowledge briefly ("got it, noted")
  and, if the edit is to patient/situation/preferences, call search_nurses again.
- If the caller sends "[user-pick] book nurseId=<id> when=<time>", confirm briefly
  and call book_nurse with those exact values.
- If the caller seems in real danger (severe bleeding, chest pain, can't breathe),
  gently suggest 911 first — but still collect intake if they stay on the line.

FIRST TURN SCRIPT (already handled by greeting): "Take a breath - what's going on?"
Then listen. Your NEXT turn should:
  - call update_situation with whatever you learned (description, tags, urgency),
  - read `missingRequired` in the result,
  - ask about the first missing item (usually age).

ISSUE TAGS (lowercase, use exact strings):
fall, wound-care, post-op, medication-management, geriatric-assessment,
iv-therapy, pediatric, mental-health, chronic-disease, hospice,
dementia-care, cardiac, respiratory

GOOD FOLLOW-UPS:
  "How old are you?"
  "Is anyone with you right now?"
  "Can you tell me a little more about what happened?"
  "Do you need someone right away, or can we schedule a visit?"
  "Is there any bleeding?"
  "Are you able to stand?"

Remember: ONE question per turn. Be human. The UI on their screen mirrors everything
you learn — no need to read it back.
"""


# ---------- Mock nurse catalog ----------
# Hardcoded SF-area nurses. Lat/lng roughly within city bounds.
NURSES = [
    {"id": "n1", "name": "Sarah Chen, RN", "photo": "/avatars/1.png",
     "canTreat": ["fall", "geriatric-assessment", "post-op", "medication-management"],
     "languages": ["en", "zh"], "lat": 37.7849, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 3:00 PM",
     "rating": 4.9, "yearsExperience": 12, "gender": "f"},
    {"id": "n2", "name": "Marcus Johnson, RN", "photo": "/avatars/2.png",
     "canTreat": ["wound-care", "post-op", "iv-therapy"],
     "languages": ["en"], "lat": 37.7649, "lng": -122.4294,
     "availableNow": True, "nextSlot": "Today 4:30 PM",
     "rating": 4.8, "yearsExperience": 8, "gender": "m"},
    {"id": "n3", "name": "Priya Patel, NP", "photo": "/avatars/3.png",
     "canTreat": ["geriatric-assessment", "chronic-disease", "medication-management", "fall"],
     "languages": ["en", "hi"], "lat": 37.7949, "lng": -122.3994,
     "availableNow": False, "nextSlot": "Tomorrow 9:00 AM",
     "rating": 5.0, "yearsExperience": 15, "gender": "f"},
    {"id": "n4", "name": "David Kim, RN", "photo": "/avatars/4.png",
     "canTreat": ["pediatric", "wound-care", "medication-management"],
     "languages": ["en", "ko"], "lat": 37.7549, "lng": -122.4194,
     "availableNow": True, "nextSlot": "Today 2:15 PM",
     "rating": 4.7, "yearsExperience": 6, "gender": "m"},
    {"id": "n5", "name": "Elena Rodriguez, RN", "photo": "/avatars/5.png",
     "canTreat": ["fall", "wound-care", "post-op", "geriatric-assessment"],
     "languages": ["en", "es"], "lat": 37.7749, "lng": -122.4394,
     "availableNow": True, "nextSlot": "Today 3:45 PM",
     "rating": 4.9, "yearsExperience": 11, "gender": "f"},
    {"id": "n6", "name": "Thomas Wright, RN", "photo": "/avatars/6.png",
     "canTreat": ["cardiac", "respiratory", "chronic-disease"],
     "languages": ["en"], "lat": 37.8049, "lng": -122.4194,
     "availableNow": False, "nextSlot": "Tomorrow 10:30 AM",
     "rating": 4.8, "yearsExperience": 14, "gender": "m"},
    {"id": "n7", "name": "Amelia Foster, RN", "photo": "/avatars/7.png",
     "canTreat": ["mental-health", "dementia-care", "geriatric-assessment"],
     "languages": ["en"], "lat": 37.7699, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 5:00 PM",
     "rating": 4.9, "yearsExperience": 10, "gender": "f"},
    {"id": "n8", "name": "Jacob Liu, RN", "photo": "/avatars/8.png",
     "canTreat": ["iv-therapy", "wound-care", "post-op"],
     "languages": ["en", "zh"], "lat": 37.7499, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 3:30 PM",
     "rating": 4.6, "yearsExperience": 5, "gender": "m"},
    {"id": "n9", "name": "Grace Okafor, NP", "photo": "/avatars/9.png",
     "canTreat": ["hospice", "dementia-care", "chronic-disease", "medication-management"],
     "languages": ["en"], "lat": 37.7849, "lng": -122.4394,
     "availableNow": False, "nextSlot": "Tomorrow 11:00 AM",
     "rating": 5.0, "yearsExperience": 18, "gender": "f"},
    {"id": "n10", "name": "Ryan O'Connor, RN", "photo": "/avatars/10.png",
     "canTreat": ["fall", "geriatric-assessment", "medication-management"],
     "languages": ["en"], "lat": 37.7799, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 2:45 PM",
     "rating": 4.7, "yearsExperience": 7, "gender": "m"},
    {"id": "n11", "name": "Isabella Martinez, RN", "photo": "/avatars/11.png",
     "canTreat": ["pediatric", "mental-health"],
     "languages": ["en", "es"], "lat": 37.7599, "lng": -122.4394,
     "availableNow": True, "nextSlot": "Today 4:00 PM",
     "rating": 4.8, "yearsExperience": 6, "gender": "f"},
    {"id": "n12", "name": "Daniel Park, RN", "photo": "/avatars/12.png",
     "canTreat": ["cardiac", "respiratory", "post-op"],
     "languages": ["en", "ko"], "lat": 37.7899, "lng": -122.4294,
     "availableNow": True, "nextSlot": "Today 5:30 PM",
     "rating": 4.9, "yearsExperience": 13, "gender": "m"},
]

DEFAULT_LOCATION = {"label": "Downtown SF", "lat": 37.7749, "lng": -122.4194}


# ---------- State helpers ----------

def _empty_state() -> dict:
    return {
        "patient": {},
        "situation": {"description": None, "issueTags": [], "urgency": None},
        "preferences": {},
        "location": DEFAULT_LOCATION.copy(),
        "candidates": [],
        "booking": None,
    }


def _get_state(context: Context) -> dict:
    state = context.get_data("state")
    if state is None:
        state = _empty_state()
        context.set_data("state", state)
    return state


def _save_state(context: Context, state: dict) -> None:
    context.set_data("state", state)


def _state_update_event(state: dict) -> CustomEvent:
    # Single place that mirrors the canonical state to the browser.
    return CustomEvent(name="state_update", data={"state": state})


# ---------- Matching ----------

def _haversine_minutes(a: tuple, b: tuple, speed_mph: float = 22.0) -> int:
    """Great-circle distance in miles, converted to minutes at ~22mph city speed."""
    lat1, lng1 = a
    lat2, lng2 = b
    R = 3958.8  # earth radius (miles)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    miles = 2 * R * math.asin(math.sqrt(h))
    # add a tiny constant buffer so nearby nurses aren't all 0/1 min
    return max(3, int(round(miles / speed_mph * 60 + 2)))


def _rank_nurses(state: dict) -> list:
    sit = state["situation"]
    prefs = state["preferences"]
    tags = set(sit.get("issueTags") or [])
    user = (state["location"]["lat"], state["location"]["lng"])
    urgent = sit.get("urgency") == "now"

    # Must cover at least one reported tag. If no tags yet, show everyone.
    fit = []
    for n in NURSES:
        if tags and not (tags & set(n["canTreat"])):
            continue
        if urgent and not n["availableNow"]:
            continue
        lang = prefs.get("language")
        if lang and lang not in n["languages"]:
            continue
        gender = prefs.get("genderPref")
        if gender and n.get("gender") != gender:
            continue
        n = {**n, "etaMinutes": _haversine_minutes(user, (n["lat"], n["lng"]))}
        fit.append(n)

    fit.sort(key=lambda n: (n["etaMinutes"], -n["rating"]))
    return fit[:5]


# ---------- Tool schema (for the LLM) ----------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_patient",
            "description": "Record basic patient info as it is learned. All fields optional; call as many times as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "First name or how to address them"},
                    "age": {"type": "integer"},
                    "livesAlone": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_situation",
            "description": "Record what's happening and how urgent it is. Call this as soon as you understand the reason for the call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Plain-language one-line description of the situation"},
                    "issueTags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Short lowercase tags like 'fall', 'wound-care', 'post-op', 'medication-management', 'geriatric-assessment', 'iv-therapy', 'pediatric', 'mental-health', 'chronic-disease', 'hospice', 'dementia-care', 'cardiac', 'respiratory'",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["now", "soon", "scheduled"],
                        "description": "now = need a nurse immediately; soon = within a few hours; scheduled = later today or future day",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "Record optional preferences like preferred language or gender. Only call if the caller mentions them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "description": "ISO-ish code: en, es, zh, hi, ko, etc."},
                    "genderPref": {"type": "string", "enum": ["f", "m"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_nurses",
            "description": "Rank nurses for the current patient+situation. Returns top matches filtered by issue tags, urgency and preferences, ranked by ETA. Call this once you have enough info, and again after any material change.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_nurse",
            "description": "Book the selected nurse at the given time. Call this only after the caller has verbally confirmed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nurseId": {"type": "string"},
                    "when": {"type": "string", "description": "Human-readable time, e.g. 'Now', 'Today 3:00 PM', 'Tomorrow 9:00 AM'"},
                },
                "required": ["nurseId", "when"],
            },
        },
    },
]


# ---------- Tool implementations ----------

def _apply_update_patient(state: dict, args: dict) -> dict:
    for k in ("name", "age", "livesAlone"):
        if args.get(k) is not None:
            state["patient"][k] = args[k]
    return state


def _apply_update_situation(state: dict, args: dict) -> dict:
    sit = state["situation"]
    if args.get("description"):
        sit["description"] = args["description"]
    if args.get("issueTags"):
        existing = set(sit.get("issueTags") or [])
        sit["issueTags"] = sorted(existing | set(args["issueTags"]))
    if args.get("urgency"):
        sit["urgency"] = args["urgency"]
    return state


def _apply_update_preferences(state: dict, args: dict) -> dict:
    for k in ("language", "genderPref"):
        if args.get(k):
            state["preferences"][k] = args[k]
    return state


REQUIRED_FIELDS = [
    ("patient", "age", "the patient's age"),
    ("patient", "livesAlone", "whether the patient is alone right now"),
    ("situation", "description", "a short description of what happened"),
    ("situation", "issueTags", "the type of care needed (at least one tag)"),
    ("situation", "urgency", "how urgent this is (now, soon, or scheduled)"),
]


def _missing_required(state: dict) -> list:
    """Return a list of {path, ask} dicts for every required field not yet filled."""
    missing = []
    for section, field, human in REQUIRED_FIELDS:
        value = state.get(section, {}).get(field)
        if value is None or (isinstance(value, list) and len(value) == 0):
            missing.append({"path": f"{section}.{field}", "ask": human})
    return missing


def _apply_search_nurses(state: dict, args: dict) -> dict:
    # The precondition check lives in _execute_tool; this just ranks.
    state["candidates"] = _rank_nurses(state)
    return state


def _apply_book_nurse(state: dict, args: dict) -> dict:
    nurse = next((n for n in NURSES if n["id"] == args["nurseId"]), None)
    state["booking"] = {
        "nurseId": args["nurseId"],
        "nurseName": nurse["name"] if nurse else args["nurseId"],
        "when": args["when"],
        "etaMinutes": _haversine_minutes(
            (state["location"]["lat"], state["location"]["lng"]),
            (nurse["lat"], nurse["lng"]),
        ) if nurse else None,
    }
    return state


TOOL_IMPLS = {
    "update_patient": _apply_update_patient,
    "update_situation": _apply_update_situation,
    "update_preferences": _apply_update_preferences,
    "search_nurses": _apply_search_nurses,
    "book_nurse": _apply_book_nurse,
}


def _execute_tool(state: dict, name: str, args: dict) -> dict:
    """Run a tool, mutating state in place. Return a short confirmation dict for the LLM.

    The return is used as ToolResultMessage.content, which expects a dict. Every
    non-terminal result also carries `missingRequired` so the LLM always knows what to
    ask about next.
    """
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return {"ok": False, "error": f"unknown tool {name}"}

    # search_nurses has a precondition: all required intake filled first.
    if name == "search_nurses":
        missing = _missing_required(state)
        if missing:
            return {
                "ok": False,
                "error": "cannot_search_yet",
                "missingRequired": missing,
                "nextAction": (
                    f"Before I can match a nurse, I still need to know: "
                    f"{missing[0]['ask']}. Ask the caller about that now."
                ),
            }
        impl(state, args)
        return {
            "ok": True,
            "candidateCount": len(state["candidates"]),
            "topCandidates": [
                {"id": n["id"], "name": n["name"],
                 "etaMinutes": n["etaMinutes"], "nextSlot": n["nextSlot"]}
                for n in state["candidates"]
            ],
            "missingRequired": [],
        }

    impl(state, args)

    if name == "book_nurse":
        return {"ok": True, "booking": state["booking"]}

    # For update_* tools, surface what's still missing so the LLM drives intake.
    missing = _missing_required(state)
    return {
        "ok": True,
        "missingRequired": missing,
        "nextAction": (
            f"Ask the caller about: {missing[0]['ask']}."
            if missing
            else "All required intake is filled. Call search_nurses next."
        ),
    }


# ---------- Main handler ----------

MODEL = "claude-haiku-4-5"
# lyric is Prim-native: lower TTFB than OpenAI voices (no extra provider hop).
VOICE = "lyric"


async def handler(event: Event, context: Context):
    if isinstance(event, StartEvent):
        # configure_provider takes `provider` and exactly one of voicerun_managed / api_key.
        configure_provider(provider="anthropic", voicerun_managed=True)
        baseten.configure(
            api_key=context.variables.get("BASETEN_API_KEY", ""),
            model=context.variables.get("BASETEN_MODEL"),
        )
        state = _get_state(context)
        # Mark the system prompt as a cache breakpoint so turn 2+ skips re-tokenizing it
        # (Anthropic ephemeral cache, 5 minute TTL).
        context.set_completion_messages([
            SystemMessage(
                content=SYSTEM_PROMPT,
                cache_breakpoint=CacheBreakpoint(ttl="5m"),
            ).serialize()
        ])
        yield _state_update_event(state)
        yield TextToSpeechEvent(
            text="Hi, this is the home-nurse dispatch line. Take a breath - what's going on?",
            voice=VOICE,
            interruptible=True,
            stream=True,
        )
        return

    if isinstance(event, StopEvent):
        return

    if not isinstance(event, TextEvent):
        return

    user_text = event.data.get("text", "") or ""
    if not user_text.strip():
        return

    # --- Baseten safety classifier (runs before the main LLM loop) ---
    emergency = await baseten.classify_emergency(user_text)
    yield CustomEvent(name="baseten_classification", data={"baseten": emergency})
    if emergency.get("classification") == "emergency":
        yield TextToSpeechEvent(
            text=(
                "This sounds like it could be a medical emergency. "
                "Please hang up and call 911 immediately. "
                "Do not wait — call 911 now."
            ),
            voice=VOICE,
        )
        return
    # -----------------------------------------------------------------

    state = _get_state(context)
    messages = context.get_completion_messages() or [
        SystemMessage(
            content=SYSTEM_PROMPT,
            cache_breakpoint=CacheBreakpoint(ttl="5m"),
        ).serialize()
    ]
    messages.append({"role": "user", "content": user_text})

    reply_text: Optional[str] = None

    # Tool loop capped low — in practice a turn needs (a) one LLM call returning
    # tool calls and (b) one follow-up to speak the result. The model is prompted
    # to emit multiple tool calls in parallel, so 2 iterations is enough.
    for _ in range(3):
        response = await generate_chat_completion({
            "provider": "anthropic",
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
        })
        msg = response.message  # AssistantMessage
        # Keep the messages list as dicts end-to-end so later turns re-serialize cleanly.
        messages.append(msg.serialize())

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            reply_text = msg.content
            break

        for tc in tool_calls:
            # ToolCall.function.arguments is already a dict in primfunctions' wire shape.
            args = tc.function.arguments or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            result = _execute_tool(state, tc.function.name, args)
            messages.append(ToolResultMessage(
                tool_call_id=tc.id,
                name=tc.function.name,
                content=result,  # ToolResultMessage expects a dict
            ).serialize())
            # Mirror state to the UI after every tool call.
            _save_state(context, state)
            yield _state_update_event(state)

    context.set_completion_messages(messages)
    _save_state(context, state)

    if reply_text:
        yield TextToSpeechEvent(
            text=reply_text, voice=VOICE, interruptible=True, stream=True,
        )
