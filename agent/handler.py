"""
Voice-first nurse dispatch agent (Uber x Zocdoc for home health).

This handler runs the intake conversation:
  - collects patient profile, situation, preferences via LLM tool calls
  - matches against mock nurses and surfaces ranked candidates
  - books the selected nurse at the requested time

Every tool mutates a single `state` blob in context, then emits a
CustomEvent("state_update") so the browser can render a mirrored view.
"""

import datetime as _dt
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


# ---------- System prompt ----------

SYSTEM_PROMPT = """You are a warm, calm healthcare dispatcher at a 24/7 home-health
service. Your job is to triage a caller who needs a nurse to come to their home,
and book a visit.

Behavior rules:
- Greet warmly in one short sentence, then ask what's going on.
- Collect just enough information to find the right nurse:
    1) basic patient info (age, lives alone?, name if offered)
    2) the situation in plain language + urgency (now / soon / scheduled)
    3) optional preferences (language, gender)
- Call `update_patient`, `update_situation`, `update_preferences` as you learn
  things. Call them early and often - do NOT wait until the end.
- When you have a situation + urgency, call `search_nurses` to rank candidates.
  Re-call it whenever the user changes material information (including edits
  the user makes in the UI, which arrive as "[user-edit] ..." text messages).
- Issue tags for situations are short lowercase strings. Use from this list
  whenever possible: "fall", "wound-care", "post-op", "medication-management",
  "geriatric-assessment", "iv-therapy", "pediatric", "mental-health",
  "chronic-disease", "hospice", "dementia-care", "cardiac", "respiratory".
- Once the user picks a nurse and time, confirm verbally THEN call `book_nurse`.
- Keep replies short (1-2 sentences). The UI shows everything you've learned.
- If the caller sounds distressed or in real danger, gently suggest 911 first.

Visual context (photos):
- Whenever the caller mentions ANYTHING visual - an injury, swelling, rash,
  wound, bruise, deformity, an x-ray, an insurance card, an ID, a prescription
  bottle, a discharge document, a medication label - briefly offer to see a
  photo and call `request_photo` with an appropriate `kind` and a short
  human-friendly `prompt` like "your knee" or "your insurance card".
- Only call `request_photo` ONCE per item. Don't pester. The UI will show a
  camera box; the user may also decline.
- After a photo arrives (it comes in as a user message containing the actual
  image), inspect it and:
    * If it's an insurance card, call `update_insurance` with whatever fields
      you can read (insurer, memberId, groupNumber, planType).
    * If it's a body part / symptom photo, call `update_symptom_observation`
      with the area (e.g. "left knee") and a one-line clinical-style finding
      (e.g. "moderate swelling and erythema over the medial joint line").
      Also call `update_situation` to refine `issueTags` / `description` if
      the photo changes your understanding.
    * If it's any other document, summarise it briefly in the spoken reply.
- Never claim a diagnosis. Describe what you see and recommend the nurse
  evaluates in person.
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
        # Visual-context additions:
        "photoRequest": None,        # { kind, prompt, requestedAt } or None
        "insurance": {},             # { insurer, memberId, groupNumber, planType }
        "symptomObservations": [],   # [{ area, findings }]
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


def _parse_photo_event(text: str) -> tuple[str, str]:
    """Parse "[user-photo] kind=<k> data=<base64>" into (kind, base64).

    Order is fixed to keep parsing trivial despite base64 containing '='.
    """
    kind = "other"
    b64 = ""
    body = text[len("[user-photo]"):].strip()
    # kind=<k> data=<everything-after>
    if body.startswith("kind="):
        rest = body[len("kind="):]
        sp = rest.find(" data=")
        if sp != -1:
            kind = rest[:sp].strip() or "other"
            b64 = rest[sp + len(" data="):].strip()
    return kind, b64


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
    {
        "type": "function",
        "function": {
            "name": "request_photo",
            "description": (
                "Show the user a camera box so they can send a photo. Call this whenever the caller mentions "
                "something visual (injury, rash, wound, swelling, x-ray, insurance card, ID, prescription bottle, "
                "discharge papers, medication label). Don't ask twice for the same thing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["insurance", "symptom", "document", "other"],
                        "description": "What category of photo you're asking for.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Short human-friendly subject shown in the UI, e.g. 'your knee', 'your insurance card', 'the prescription bottle'.",
                    },
                },
                "required": ["kind", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_insurance",
            "description": "Record fields read from an insurance card photo. All fields optional; partial merges are fine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "insurer": {"type": "string", "description": "Carrier name, e.g. 'Blue Shield of California'"},
                    "memberId": {"type": "string"},
                    "groupNumber": {"type": "string"},
                    "planType": {"type": "string", "description": "e.g. PPO, HMO, EPO, Medicare Advantage"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_symptom_observation",
            "description": (
                "Record a brief clinical-style observation about something visible in a symptom photo. "
                "Append-only; call once per distinct observation. Never diagnose."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {"type": "string", "description": "Body area, e.g. 'left knee', 'right forearm'"},
                    "findings": {"type": "string", "description": "One-line description, e.g. 'moderate swelling and erythema over the medial joint line'"},
                },
                "required": ["area", "findings"],
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


def _apply_search_nurses(state: dict, args: dict) -> dict:
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


def _apply_request_photo(state: dict, args: dict) -> dict:
    state["photoRequest"] = {
        "kind": args.get("kind", "other"),
        "prompt": args.get("prompt", "a photo"),
        "requestedAt": _dt.datetime.utcnow().isoformat() + "Z",
    }
    return state


def _apply_update_insurance(state: dict, args: dict) -> dict:
    for k in ("insurer", "memberId", "groupNumber", "planType"):
        v = args.get(k)
        if v:
            state["insurance"][k] = v
    return state


def _apply_update_symptom_observation(state: dict, args: dict) -> dict:
    area = args.get("area")
    findings = args.get("findings")
    if area and findings:
        state["symptomObservations"].append({"area": area, "findings": findings})
    return state


TOOL_IMPLS = {
    "update_patient": _apply_update_patient,
    "update_situation": _apply_update_situation,
    "update_preferences": _apply_update_preferences,
    "search_nurses": _apply_search_nurses,
    "book_nurse": _apply_book_nurse,
    "request_photo": _apply_request_photo,
    "update_insurance": _apply_update_insurance,
    "update_symptom_observation": _apply_update_symptom_observation,
}


def _execute_tool(state: dict, name: str, args: dict) -> dict:
    """Run a tool, mutating state in place. Return a short confirmation dict for the LLM.

    The return is used as ToolResultMessage.content, which expects a dict.
    """
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    impl(state, args)
    if name == "search_nurses":
        return {
            "ok": True,
            "candidateCount": len(state["candidates"]),
            "topCandidates": [
                {"id": n["id"], "name": n["name"],
                 "etaMinutes": n["etaMinutes"], "nextSlot": n["nextSlot"]}
                for n in state["candidates"]
            ],
        }
    if name == "book_nurse":
        return {"ok": True, "booking": state["booking"]}
    if name == "request_photo":
        return {"ok": True, "photoRequest": state["photoRequest"]}
    if name == "update_insurance":
        return {"ok": True, "insurance": state["insurance"]}
    if name == "update_symptom_observation":
        return {"ok": True, "observationCount": len(state["symptomObservations"])}
    return {"ok": True}


# ---------- Main handler ----------

MODEL = "claude-haiku-4-5"
VOICE = "nova"


async def handler(event: Event, context: Context):
    if isinstance(event, StartEvent):
        # configure_provider takes `provider` and exactly one of voicerun_managed / api_key.
        configure_provider(provider="anthropic", voicerun_managed=True)
        state = _get_state(context)
        context.set_completion_messages([{"role": "system", "content": SYSTEM_PROMPT}])
        yield _state_update_event(state)
        yield TextToSpeechEvent(
            text="Hi, this is the home-nurse dispatch line. Take a breath - what's going on?",
            voice=VOICE,
        )
        return

    if isinstance(event, StopEvent):
        return

    if not isinstance(event, TextEvent):
        return

    user_text = event.data.get("text", "") or ""
    if not user_text.strip():
        return

    state = _get_state(context)
    messages = context.get_completion_messages() or [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # ---- Photo intake -----------------------------------------------------
    # The browser ships images over the only available channel - text events.
    # Format: "[user-photo] kind=<k> data=<base64-jpeg>"
    if user_text.startswith("[user-cancel-photo]"):
        if state.get("photoRequest") is not None:
            state["photoRequest"] = None
            _save_state(context, state)
            yield _state_update_event(state)
        # Tell the LLM the user declined so it can move on without re-asking.
        messages.append({
            "role": "user",
            "content": "[system-note] User declined to send a photo. Move on without it.",
        })
    elif user_text.startswith("[user-photo]"):
        kind, b64 = _parse_photo_event(user_text)
        if not b64:
            # Malformed - treat as a cancel so the UI doesn't get stuck.
            state["photoRequest"] = None
            _save_state(context, state)
            yield _state_update_event(state)
            return
        # Clear the pending request immediately so the camera box closes.
        state["photoRequest"] = None
        _save_state(context, state)
        yield _state_update_event(state)
        # Hand the image to the LLM as an Anthropic multimodal user message.
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        f"Here is the photo of {kind}. Read everything you can "
                        "and call the appropriate update tool(s). Then say one "
                        "short spoken sentence summarising what you saw."
                    ),
                },
            ],
        })
    else:
        messages.append({"role": "user", "content": user_text})

    reply_text: Optional[str] = None
    error_text: Optional[str] = None

    # Tool-calling loop. Cap iterations so we never spin forever. Wrap the
    # whole loop in try/except so a downstream LLM/proxy failure (e.g. an
    # oversized multimodal request) still produces a spoken apology instead
    # of leaving the call dead-quiet.
    try:
        for _ in range(6):
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
    except Exception as e:  # noqa: BLE001 - surface anything to the caller
        # Drop the partial turn from the message log so the next turn doesn't
        # carry a malformed message that would re-trigger the same failure.
        # Easiest robust thing: rebuild messages from the system prompt + the
        # last good completion-message snapshot.
        messages = context.get_completion_messages() or [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        error_text = (
            "Sorry, I had trouble processing that. Could you describe it in "
            "words instead?"
        )
        # Log to the UI debug stream so we can diagnose.
        yield CustomEvent(
            name="agent_error",
            data={"where": "completion_loop", "error": str(e)[:300]},
        )

    context.set_completion_messages(messages)
    _save_state(context, state)

    if reply_text:
        yield TextToSpeechEvent(text=reply_text, voice=VOICE)
    elif error_text:
        yield TextToSpeechEvent(text=error_text, voice=VOICE)
