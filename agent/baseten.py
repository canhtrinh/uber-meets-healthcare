"""
Emergency classifier powered by Baseten's OpenAI-compatible inference API.

Runs before the main Anthropic conversation loop on every user turn.
If the utterance contains life-threatening red flags, the caller is
instructed to dial 911 and the turn is short-circuited.
"""

import asyncio
import json
import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None
_model: str = "deepseek-ai/DeepSeek-V3.1"


def configure(api_key: str, model: str | None = None) -> None:
    """Call once from StartEvent with values from context.variables."""
    global _client, _model
    _client = AsyncOpenAI(
        base_url="https://inference.baseten.co/v1",
        api_key=api_key,
    )
    if model:
        _model = model

_EMERGENCY_PROMPT = """\
You are a triage safety classifier. Given a caller's statement to a home-nurse \
dispatch service, decide whether it contains emergency red flags — symptoms or \
situations that require immediate 911 response rather than a home nurse visit.

Emergency red flags include (but are not limited to):
- Chest pain, pressure, or tightness
- Difficulty breathing or not breathing
- Signs of stroke (sudden face drooping, arm weakness, speech difficulty)
- Loss of consciousness or unresponsive person
- Severe allergic reaction / anaphylaxis
- Heavy uncontrolled bleeding
- Seizure in progress
- "Worst headache of my life"
- Suicidal statements or intent to harm

Respond with valid JSON only. No other text.
{"classification": "emergency" | "non_emergency" | "unclear", "reason": "<one short sentence>"}

Caller statement: {text}"""


async def classify_emergency(text: str) -> dict:
    """Return {"classification": ..., "reason": ...} for the given utterance.

    Falls back to {"classification": "unclear"} on any error so the caller
    is never silently dropped into the main loop without a safety check.
    """
    if _client is None:
        logger.warning("Baseten not configured — skipping emergency check")
        return {"classification": "unclear", "reason": "classifier not configured"}
    try:
        resp = await asyncio.wait_for(
            _client.chat.completions.create(
                model=_model,
                messages=[
                    {"role": "user", "content": _EMERGENCY_PROMPT.format(text=text)}
                ],
                response_format={"type": "json_object"},
                max_tokens=120,
                temperature=0.0,
            ),
            timeout=3.0,
        )
        return json.loads(resp.choices[0].message.content)
    except asyncio.TimeoutError:
        logger.warning("Baseten classify_emergency timed out")
        return {"classification": "unclear", "reason": "classifier timeout"}
    except Exception as exc:
        logger.warning("Baseten classify_emergency failed: %s", exc)
        return {"classification": "unclear", "reason": "classifier unavailable"}
