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
(a) gather the REQUIRED intake, (b) run search_nurses the MOMENT intake is complete,
(c) book the nurse the caller picks.

REQUIRED intake — you MUST have ALL NINE before calling search_nurses. The tool
will refuse if anything is missing.

  1. patient.name               (ask: "what's your name?" / "who am I speaking with?")
  2. patient.age                (ask: "how old are you?")
  3. patient.livesAlone         (ask: "are you alone right now?" / "is anyone with you?")
  4. situation.description      (plain-language summary of what happened)
  5. situation.issueTags        (at least one tag from the ISSUE TAGS list)
  6. situation.urgency          ("now" / "soon" / "scheduled")
  7. emergencyContact.name      (ask: "who should we call if anything goes wrong?")
  8. emergencyContact.phone     (ask: "what's their phone number?")
  9. insurance.provider         (ask: "what health insurance do you have?")

OPTIONAL (ask only if caller volunteers OR clearly relevant):
  - emergencyContact.relationship (e.g. daughter, spouse)
  - insurance.memberId           (don't make them read long IDs over voice)
  - preferences.language, preferences.genderPref

CONVERSATION RULES:
- ONE short question per turn. Phone-call cadence, no lists, no markdown, no stacked
  questions.
- After you learn something, IMMEDIATELY call the matching update_* tool. You MAY
  emit multiple update_* tool_calls in a single response when the caller shares
  several things at once — parallel tool use is PREFERRED, it cuts turn latency.
- After every tool call, read the `missingRequired` field in the result. If it is
  non-empty, your very next sentence asks about the FIRST item in that list.
- The moment `missingRequired` is EMPTY, call search_nurses in the SAME response.
  Do NOT announce "I'll find nurses now" as its own turn. Do NOT ask the caller for
  permission — just call it. The UI will show the results the moment it returns.
- When search_nurses returns, its result includes `topCandidates` with each nurse's
  id, name, ETA, and next slot. Use that to map a spoken name ("book Sarah Chen")
  to the right nurseId. Announce ONE sentence: "Found a few nurses nearby, closest
  is about [X] min — tap one on your screen, or tell me who to book."
- "[user-edit] path=value": acknowledge briefly ("got it"), then if the edit is to
  patient/situation/preferences/emergencyContact/insurance, re-call search_nurses
  so the ranking refreshes.
- "[user-pick] book nurseId=<id> when=<time>": confirm briefly and call book_nurse
  with those exact values.
- "book <name>" spoken: prefer the matching nurseId from the last search_nurses
  result; if you can't resolve it, pass nurseName and the server will fuzzy-match.
- Real danger signs (severe bleeding, chest pain, can't breathe, stroke symptoms):
  gently suggest 911 first — but stay on the line and keep gathering intake.

FIRST TURN SCRIPT (already spoken as the greeting): the caller just heard the 911
disclaimer + "what's going on?" Your next turn reacts to whatever they say. Start
with update_situation for the situation they describe, then ask about the first
missing required field (usually their name).

ISSUE TAGS (lowercase, exact strings):
fall, wound-care, post-op, medication-management, geriatric-assessment,
iv-therapy, pediatric, mental-health, chronic-disease, hospice,
dementia-care, cardiac, respiratory

GOOD FOLLOW-UPS:
  "What's your name?"
  "How old are you?"
  "Is anyone with you right now?"
  "Can you tell me a bit more about what happened?"
  "Do you need someone right away, or is this something we can schedule?"
  "Who should I call if anything goes wrong — what's their name and number?"
  "What insurance do you have?"

Remember: ONE question per turn. Be human. The UI mirrors your state — no need to
read it back.
"""


# ---------- Mock nurse catalog ----------
# Hardcoded SF-area nurses. ETAs are intentionally scheduled-visit-shaped
# (mostly 2–4 hours out, with one rush slot at 45 min) — home-health dispatch
# isn't rideshare. baseEtaMinutes is the travel/prep time to the caller's
# door; the ranker uses it directly.
NURSES = [
    {"id": "n1", "name": "Sarah Chen, RN", "photo": "/avatars/1.png",
     "canTreat": ["fall", "geriatric-assessment", "post-op", "medication-management"],
     "languages": ["en", "zh"], "lat": 37.7849, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 3:00 PM",
     "baseEtaMinutes": 45,
     "rating": 4.9, "yearsExperience": 12, "gender": "f"},
    {"id": "n2", "name": "Marcus Johnson, RN", "photo": "/avatars/2.png",
     "canTreat": ["wound-care", "post-op", "iv-therapy"],
     "languages": ["en"], "lat": 37.7649, "lng": -122.4294,
     "availableNow": True, "nextSlot": "Today 4:30 PM",
     "baseEtaMinutes": 150,
     "rating": 4.8, "yearsExperience": 8, "gender": "m"},
    {"id": "n3", "name": "Priya Patel, NP", "photo": "/avatars/3.png",
     "canTreat": ["geriatric-assessment", "chronic-disease", "medication-management", "fall"],
     "languages": ["en", "hi"], "lat": 37.7949, "lng": -122.3994,
     "availableNow": False, "nextSlot": "Tomorrow 9:00 AM",
     "baseEtaMinutes": 180,
     "rating": 5.0, "yearsExperience": 15, "gender": "f"},
    {"id": "n4", "name": "David Kim, RN", "photo": "/avatars/4.png",
     "canTreat": ["pediatric", "wound-care", "medication-management"],
     "languages": ["en", "ko"], "lat": 37.7549, "lng": -122.4194,
     "availableNow": True, "nextSlot": "Today 2:15 PM",
     "baseEtaMinutes": 180,
     "rating": 4.7, "yearsExperience": 6, "gender": "m"},
    {"id": "n5", "name": "Elena Rodriguez, RN", "photo": "/avatars/5.png",
     "canTreat": ["fall", "wound-care", "post-op", "geriatric-assessment"],
     "languages": ["en", "es"], "lat": 37.7749, "lng": -122.4394,
     "availableNow": True, "nextSlot": "Today 3:45 PM",
     "baseEtaMinutes": 120,
     "rating": 4.9, "yearsExperience": 11, "gender": "f"},
    {"id": "n6", "name": "Thomas Wright, RN", "photo": "/avatars/6.png",
     "canTreat": ["cardiac", "respiratory", "chronic-disease"],
     "languages": ["en"], "lat": 37.8049, "lng": -122.4194,
     "availableNow": False, "nextSlot": "Tomorrow 10:30 AM",
     "baseEtaMinutes": 240,
     "rating": 4.8, "yearsExperience": 14, "gender": "m"},
    {"id": "n7", "name": "Amelia Foster, RN", "photo": "/avatars/7.png",
     "canTreat": ["mental-health", "dementia-care", "geriatric-assessment"],
     "languages": ["en"], "lat": 37.7699, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 5:00 PM",
     "baseEtaMinutes": 210,
     "rating": 4.9, "yearsExperience": 10, "gender": "f"},
    {"id": "n8", "name": "Jacob Liu, RN", "photo": "/avatars/8.png",
     "canTreat": ["iv-therapy", "wound-care", "post-op"],
     "languages": ["en", "zh"], "lat": 37.7499, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 3:30 PM",
     "baseEtaMinutes": 165,
     "rating": 4.6, "yearsExperience": 5, "gender": "m"},
    {"id": "n9", "name": "Grace Okafor, NP", "photo": "/avatars/9.png",
     "canTreat": ["hospice", "dementia-care", "chronic-disease", "medication-management"],
     "languages": ["en"], "lat": 37.7849, "lng": -122.4394,
     "availableNow": False, "nextSlot": "Tomorrow 11:00 AM",
     "baseEtaMinutes": 225,
     "rating": 5.0, "yearsExperience": 18, "gender": "f"},
    {"id": "n10", "name": "Ryan O'Connor, RN", "photo": "/avatars/10.png",
     "canTreat": ["fall", "geriatric-assessment", "medication-management"],
     "languages": ["en"], "lat": 37.7799, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 2:45 PM",
     "baseEtaMinutes": 135,
     "rating": 4.7, "yearsExperience": 7, "gender": "m"},
    {"id": "n11", "name": "Isabella Martinez, RN", "photo": "/avatars/11.png",
     "canTreat": ["pediatric", "mental-health"],
     "languages": ["en", "es"], "lat": 37.7599, "lng": -122.4394,
     "availableNow": True, "nextSlot": "Today 4:00 PM",
     "baseEtaMinutes": 195,
     "rating": 4.8, "yearsExperience": 6, "gender": "f"},
    {"id": "n12", "name": "Daniel Park, RN", "photo": "/avatars/12.png",
     "canTreat": ["cardiac", "respiratory", "post-op"],
     "languages": ["en", "ko"], "lat": 37.7899, "lng": -122.4294,
     "availableNow": True, "nextSlot": "Today 5:30 PM",
     "baseEtaMinutes": 240,
     "rating": 4.9, "yearsExperience": 13, "gender": "m"},
]

DEFAULT_LOCATION = {"label": "Downtown SF", "lat": 37.7749, "lng": -122.4194}


# ---------- State helpers ----------

def _empty_state() -> dict:
    return {
        "patient": {},
        "situation": {"description": None, "issueTags": [], "urgency": None},
        "preferences": {},
        "emergencyContact": {},
        "insurance": {},
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
        # Use the hand-tuned per-nurse ETA (home-health visits are scheduled
        # hours out, not rideshare minutes).
        n = {**n, "etaMinutes": n["baseEtaMinutes"]}
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
            "name": "update_emergency_contact",
            "description": "Record the patient's emergency contact — someone to reach if something goes wrong. Call as soon as you learn a name or phone number. Both name AND phone are required before search_nurses can run; relationship is optional.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Emergency contact's name"},
                    "phone": {"type": "string", "description": "Emergency contact's phone number, any readable format"},
                    "relationship": {"type": "string", "description": "Optional — e.g. 'daughter', 'spouse', 'neighbor'"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_insurance",
            "description": "Record the patient's health insurance. Provider name is required before search_nurses; memberId is optional and only worth collecting if the caller volunteers it (don't make them read a long ID over voice).",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "description": "Insurance provider (e.g. 'Medicare', 'Blue Cross', 'Kaiser', 'Aetna')"},
                    "memberId": {"type": "string", "description": "Optional member/policy ID"},
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
            "description": "Book the selected nurse at the given time. Call this only after the caller has verbally confirmed. Prefer nurseId from the last search_nurses result; if you only have a name, pass nurseName and the server will resolve it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nurseId": {"type": "string", "description": "Nurse id from search_nurses.candidates[].id (preferred)"},
                    "nurseName": {"type": "string", "description": "Fallback when only the name is known (e.g. 'Sarah Chen'). Fuzzy-matched to current candidates."},
                    "when": {"type": "string", "description": "Human-readable time, e.g. 'Now', 'Today 3:00 PM', 'Tomorrow 9:00 AM'"},
                },
                "required": ["when"],
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


def _apply_update_emergency_contact(state: dict, args: dict) -> dict:
    ec = state.setdefault("emergencyContact", {})
    for k in ("name", "phone", "relationship"):
        if args.get(k):
            ec[k] = args[k]
    return state


def _apply_update_insurance(state: dict, args: dict) -> dict:
    ins = state.setdefault("insurance", {})
    for k in ("provider", "memberId"):
        if args.get(k):
            ins[k] = args[k]
    return state


REQUIRED_FIELDS = [
    ("patient", "name", "the patient's name"),
    ("patient", "age", "the patient's age"),
    ("patient", "livesAlone", "whether the patient is alone right now"),
    ("situation", "description", "a short description of what happened"),
    ("situation", "issueTags", "the type of care needed (at least one tag)"),
    ("situation", "urgency", "how urgent this is (now, soon, or scheduled)"),
    ("emergencyContact", "name", "the emergency contact's name"),
    ("emergencyContact", "phone", "the emergency contact's phone number"),
    ("insurance", "provider", "their insurance provider"),
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


def _resolve_nurse(state: dict, args: dict):
    """Find the referenced nurse by id (preferred) or fuzzy-matched name.
    Search the current candidates first, then fall back to the full catalog.
    Returns the nurse dict or None."""
    nid = (args.get("nurseId") or "").strip()
    if nid:
        for n in state.get("candidates") or []:
            if n["id"] == nid:
                return n
        for n in NURSES:
            if n["id"] == nid:
                return n
    name = (args.get("nurseName") or "").strip().lower()
    if name:
        pool = (state.get("candidates") or []) + NURSES
        # 1) exact (case-insensitive) match on the prefix before the comma
        for n in pool:
            if n["name"].split(",")[0].strip().lower() == name:
                return n
        # 2) substring match anywhere in the full name
        for n in pool:
            if name in n["name"].lower():
                return n
        # 3) any overlap between spoken tokens and the nurse's name tokens
        tokens = {t for t in name.split() if len(t) > 1}
        if tokens:
            for n in pool:
                nurse_tokens = {t.lower().rstrip(",") for t in n["name"].split()}
                if tokens & nurse_tokens:
                    return n
    return None


def _apply_book_nurse(state: dict, args: dict) -> dict:
    nurse = _resolve_nurse(state, args)
    if nurse is None:
        # No match — record a placeholder so the tool result can describe the miss.
        state["booking"] = {
            "nurseId": args.get("nurseId") or args.get("nurseName") or "unknown",
            "nurseName": args.get("nurseName") or args.get("nurseId") or "Unknown nurse",
            "when": args.get("when"),
            "etaMinutes": None,
            "error": "nurse_not_found",
        }
        return state
    state["booking"] = {
        "nurseId": nurse["id"],
        "nurseName": nurse["name"],
        "when": args.get("when"),
        "etaMinutes": nurse["baseEtaMinutes"],
    }
    return state


TOOL_IMPLS = {
    "update_patient": _apply_update_patient,
    "update_situation": _apply_update_situation,
    "update_preferences": _apply_update_preferences,
    "update_emergency_contact": _apply_update_emergency_contact,
    "update_insurance": _apply_update_insurance,
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
        b = state["booking"] or {}
        if b.get("error") == "nurse_not_found":
            # Give the LLM enough context to ask the user to clarify.
            cands = [{"id": n["id"], "name": n["name"]} for n in (state.get("candidates") or [])]
            return {
                "ok": False,
                "error": "nurse_not_found",
                "candidates": cands,
                "nextAction": "Tell the caller you didn't catch which nurse they meant and read two or three names from `candidates`. Then ask them to pick one.",
            }
        return {"ok": True, "booking": b}

    # update_* tools: just surface what's still missing.
    missing = _missing_required(state)
    return {
        "ok": True,
        "missingRequired": missing,
        "nextAction": (
            f"Ask about: {missing[0]['ask']}." if missing else "All required info filled. Call search_nurses."
        ),
    }


# ---------- Main handler ----------

MODEL = "claude-haiku-4-5"
VOICE = "nova"
# OpenAI voices support 0.25–4.0x. 1.2 = noticeably snappier without sounding rushed.
SPEECH_SPEED = 1.2


async def handler(event: Event, context: Context):
    if isinstance(event, StartEvent):
        # configure_provider takes `provider` and exactly one of voicerun_managed / api_key.
        configure_provider(provider="anthropic", voicerun_managed=True)
        baseten.configure(
            api_key=context.variables.get("BASETEN_API_KEY", ""),
            model=context.variables.get("BASETEN_MODEL"),
        )
        state = _get_state(context)
        # cache_breakpoint on the system message tells Anthropic to cache everything
        # up to and including this message, so turns 2+ skip re-reading the prompt.
        context.set_completion_messages([
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
                "cache_breakpoint": {"ttl": "5m"},
            }
        ])
        yield _state_update_event(state)
        yield TextToSpeechEvent(
            text=(
                "If this is a medical emergency, please hang up and dial 9-1-1 right now. "
                "Otherwise, this is the nurse dispatcher line — we're here to help fast. "
                "Looks like it's your first time calling, so let me get a few quick details. "
                "What's going on?"
            ),
            voice=VOICE,
            interruptible=False,
            stream=True,
            speed=SPEECH_SPEED,
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
    if emergency.get("classification") == "emergency":
        yield TextToSpeechEvent(
            text=(
                "This sounds like it could be a medical emergency. "
                "Please hang up and call 911 immediately. "
                "Do not wait — call 911 now."
            ),
            voice=VOICE,
            interruptible=False,
        )
        return
    # -----------------------------------------------------------------

    state = _get_state(context)
    messages = context.get_completion_messages() or [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
            "cache_breakpoint": {"ttl": "5m"},
        }
    ]
    messages.append({"role": "user", "content": user_text})

    reply_text: Optional[str] = None

    # Two-pass tool loop. At most: (1) one auto-call that may return parallel tool_calls,
    # (2) one forced reply. `tool_choice="none"` on the last pass guarantees speech.
    MAX_PASSES = 2
    for i in range(MAX_PASSES):
        tool_choice = "none" if i == MAX_PASSES - 1 else "auto"
        response = await generate_chat_completion({
            "provider": "anthropic",
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": tool_choice,
        })
        msg = response.message  # AssistantMessage
        messages.append(msg.serialize())

        tool_calls = msg.tool_calls or []
        if not tool_calls:
            reply_text = msg.content
            break

        for tc in tool_calls:
            args = tc.function.arguments or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            result = _execute_tool(state, tc.function.name, args)
            messages.append(ToolResultMessage(
                tool_call_id=tc.id,
                name=tc.function.name,
                content=result,
            ).serialize())
            _save_state(context, state)
            yield _state_update_event(state)

    context.set_completion_messages(messages)
    _save_state(context, state)

    if reply_text:
        yield TextToSpeechEvent(
            text=reply_text,
            voice=VOICE,
            interruptible=False,
            stream=True,
            speed=SPEECH_SPEED,
        )
