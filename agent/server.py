"""
Standalone HTTP server wrapping the nurse-dispatch agent logic.

Used by Veris simulations — runs the same intake/matching/booking logic
as handler.py but over a plain HTTP interface instead of Voicerun events.
"""

import json
import math
import os
import uuid
from typing import Optional

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="NurseNow Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ---------- System prompt (mirrors handler.py) ----------

SYSTEM_PROMPT = """You are a warm, calm dispatcher at a 24/7 home-health nursing service.
You are on a voice call with someone who needs a nurse at their home. Your job is to
(a) gather the REQUIRED intake, (b) run search_nurses once you have it, and (c) book
the nurse the caller picks.

REQUIRED intake — you MUST have ALL FIVE before calling search_nurses:
  1. patient.age
  2. patient.livesAlone
  3. situation.description
  4. situation.issueTags  (at least one tag)
  5. situation.urgency    (now / soon / scheduled)

CONVERSATION RULES:
- Keep every reply SHORT (one sentence, one question).
- ASK ONE QUESTION AT A TIME. Never stack multiple questions.
- After you learn something, IMMEDIATELY call the matching update_* tool.
- After each tool call, read the missingRequired field. Ask about the first missing item.
- Only when missingRequired is empty should you call search_nurses.
- When search_nurses returns, summarise: "I found N nurses nearby, closest is ~X min away."
- If the caller seems in real danger (chest pain, can't breathe), suggest 911 first.

ISSUE TAGS (lowercase, use exact strings):
fall, wound-care, post-op, medication-management, geriatric-assessment,
iv-therapy, pediatric, mental-health, chronic-disease, hospice,
dementia-care, cardiac, respiratory
"""

# ---------- Mock nurse catalog ----------

NURSES = [
    {"id": "n1", "name": "Sarah Chen, RN",
     "canTreat": ["fall", "geriatric-assessment", "post-op", "medication-management"],
     "languages": ["en", "zh"], "lat": 37.7849, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 3:00 PM", "rating": 4.9, "gender": "f"},
    {"id": "n2", "name": "Marcus Johnson, RN",
     "canTreat": ["wound-care", "post-op", "iv-therapy"],
     "languages": ["en"], "lat": 37.7649, "lng": -122.4294,
     "availableNow": True, "nextSlot": "Today 4:30 PM", "rating": 4.8, "gender": "m"},
    {"id": "n3", "name": "Priya Patel, NP",
     "canTreat": ["geriatric-assessment", "chronic-disease", "medication-management", "fall"],
     "languages": ["en", "hi"], "lat": 37.7949, "lng": -122.3994,
     "availableNow": False, "nextSlot": "Tomorrow 9:00 AM", "rating": 5.0, "gender": "f"},
    {"id": "n4", "name": "David Kim, RN",
     "canTreat": ["pediatric", "wound-care", "medication-management"],
     "languages": ["en", "ko"], "lat": 37.7549, "lng": -122.4194,
     "availableNow": True, "nextSlot": "Today 2:15 PM", "rating": 4.7, "gender": "m"},
    {"id": "n5", "name": "Elena Rodriguez, RN",
     "canTreat": ["fall", "wound-care", "post-op", "geriatric-assessment"],
     "languages": ["en", "es"], "lat": 37.7749, "lng": -122.4394,
     "availableNow": True, "nextSlot": "Today 3:45 PM", "rating": 4.9, "gender": "f"},
    {"id": "n6", "name": "Thomas Wright, RN",
     "canTreat": ["cardiac", "respiratory", "chronic-disease"],
     "languages": ["en"], "lat": 37.8049, "lng": -122.4194,
     "availableNow": False, "nextSlot": "Tomorrow 10:30 AM", "rating": 4.8, "gender": "m"},
    {"id": "n7", "name": "Amelia Foster, RN",
     "canTreat": ["mental-health", "dementia-care", "geriatric-assessment"],
     "languages": ["en"], "lat": 37.7699, "lng": -122.4094,
     "availableNow": True, "nextSlot": "Today 5:00 PM", "rating": 4.9, "gender": "f"},
]

DEFAULT_LOCATION = {"lat": 37.7749, "lng": -122.4194}

# ---------- State ----------

def _empty_state() -> dict:
    return {
        "patient": {},
        "situation": {"description": None, "issueTags": [], "urgency": None},
        "preferences": {},
        "location": DEFAULT_LOCATION.copy(),
        "candidates": [],
        "booking": None,
    }

# ---------- Matching ----------

def _haversine_minutes(a: tuple, b: tuple, speed_mph: float = 22.0) -> int:
    lat1, lng1 = a
    lat2, lng2 = b
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return max(3, int(round(2 * R * math.asin(math.sqrt(h)) / speed_mph * 60 + 2)))

def _rank_nurses(state: dict) -> list:
    tags = set(state["situation"].get("issueTags") or [])
    prefs = state["preferences"]
    user = (state["location"]["lat"], state["location"]["lng"])
    urgent = state["situation"].get("urgency") == "now"
    fit = []
    for n in NURSES:
        if tags and not (tags & set(n["canTreat"])):
            continue
        if urgent and not n["availableNow"]:
            continue
        if prefs.get("language") and prefs["language"] not in n["languages"]:
            continue
        if prefs.get("genderPref") and n.get("gender") != prefs["genderPref"]:
            continue
        fit.append({**n, "etaMinutes": _haversine_minutes(user, (n["lat"], n["lng"]))})
    fit.sort(key=lambda n: (n["etaMinutes"], -n["rating"]))
    return fit[:5]

# ---------- Tool schema ----------

TOOLS = [
    {"name": "update_patient", "description": "Record patient info.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "age": {"type": "integer"},
         "livesAlone": {"type": "boolean"}}}},
    {"name": "update_situation", "description": "Record situation and urgency.",
     "input_schema": {"type": "object", "properties": {
         "description": {"type": "string"},
         "issueTags": {"type": "array", "items": {"type": "string"}},
         "urgency": {"type": "string", "enum": ["now", "soon", "scheduled"]}}}},
    {"name": "update_preferences", "description": "Record optional preferences.",
     "input_schema": {"type": "object", "properties": {
         "language": {"type": "string"},
         "genderPref": {"type": "string", "enum": ["f", "m"]}}}},
    {"name": "search_nurses", "description": "Find matching nurses.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "book_nurse", "description": "Book a nurse.",
     "input_schema": {"type": "object", "required": ["nurseId", "when"], "properties": {
         "nurseId": {"type": "string"},
         "when": {"type": "string"}}}},
]

REQUIRED_FIELDS = [
    ("patient", "age"), ("patient", "livesAlone"),
    ("situation", "description"), ("situation", "issueTags"), ("situation", "urgency"),
]

def _missing_required(state: dict) -> list:
    missing = []
    for section, field in REQUIRED_FIELDS:
        v = state.get(section, {}).get(field)
        if v is None or (isinstance(v, list) and not v):
            missing.append(f"{section}.{field}")
    return missing

def _execute_tool(state: dict, name: str, args: dict) -> dict:
    if name == "update_patient":
        for k in ("name", "age", "livesAlone"):
            if args.get(k) is not None:
                state["patient"][k] = args[k]
    elif name == "update_situation":
        sit = state["situation"]
        if args.get("description"):
            sit["description"] = args["description"]
        if args.get("issueTags"):
            sit["issueTags"] = sorted(set(sit.get("issueTags") or []) | set(args["issueTags"]))
        if args.get("urgency"):
            sit["urgency"] = args["urgency"]
    elif name == "update_preferences":
        for k in ("language", "genderPref"):
            if args.get(k):
                state["preferences"][k] = args[k]
    elif name == "search_nurses":
        missing = _missing_required(state)
        if missing:
            return {"ok": False, "error": "missing_required", "missing": missing}
        state["candidates"] = _rank_nurses(state)
        return {"ok": True, "candidateCount": len(state["candidates"]),
                "topCandidates": [{"id": n["id"], "name": n["name"],
                                   "etaMinutes": n["etaMinutes"]} for n in state["candidates"]]}
    elif name == "book_nurse":
        nurse = next((n for n in NURSES if n["id"] == args["nurseId"]), None)
        state["booking"] = {"nurseId": args["nurseId"],
                            "nurseName": nurse["name"] if nurse else args["nurseId"],
                            "when": args["when"]}
        return {"ok": True, "booking": state["booking"]}
    else:
        return {"ok": False, "error": f"unknown tool {name}"}

    return {"ok": True, "missingRequired": _missing_required(state)}

# ---------- Session store ----------

_sessions: dict[str, dict] = {}

# ---------- API ----------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    state: dict

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    sid = req.session_id or str(uuid.uuid4())
    if sid not in _sessions:
        _sessions[sid] = {
            "messages": [],
            "state": _empty_state(),
        }
    session = _sessions[sid]
    session["messages"].append({"role": "user", "content": req.message})

    reply_text = ""
    for _ in range(8):
        resp = _client.messages.create(
            model="claude-haiku-4-5",
            system=SYSTEM_PROMPT,
            max_tokens=512,
            tools=TOOLS,
            messages=session["messages"],
        )
        # Append assistant turn
        session["messages"].append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            for block in resp.content:
                if hasattr(block, "text"):
                    reply_text = block.text
            break

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = _execute_tool(session["state"], block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            if tool_results:
                session["messages"].append({"role": "user", "content": tool_results})
        else:
            break

    return ChatResponse(response=reply_text, session_id=sid, state=session["state"])


@app.get("/health")
async def health():
    return {"ok": True}
