import json
import os
import anthropic

SYSTEM_PROMPT = """You are a video editing assistant. The user will describe how they want to cut and arrange video clips in natural language. Your job is to convert their instructions into a structured JSON edit plan.

Output ONLY valid JSON in this exact format:
{
  "steps": [
    {"clip": "<clip_name>", "start": <seconds_or_null>, "end": <seconds_or_null>}
  ],
  "output_format": "mp4"
}

Rules:
- "clip" must be one of the available clip names provided
- "start" and "end" are in seconds (floats). Use null to mean "from the beginning" or "until the end"
- Steps are concatenated in order
- If the user says "the whole clip" or doesn't specify a range, use null for both start and end
- If the user says "last N seconds" of a clip with known duration D, set start = D - N, end = null
- Output ONLY the JSON object, no explanation, no markdown code fences"""


def parse_instructions(instructions: str, clips: list[dict]) -> dict:
    """
    clips: list of {"name": str, "duration": float}
    Returns parsed edit plan dict.
    """
    clip_info = "\n".join(
        f"- {c['name']} (duration: {c['duration']:.2f}s)" for c in clips
    )
    user_message = f"Available clips:\n{clip_info}\n\nInstructions: {instructions}"

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if model adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
