import json
import os
import anthropic

SYSTEM_PROMPT = """You are a video editing assistant. Convert natural language editing instructions into a structured JSON edit plan.

Output ONLY valid JSON in this exact format:
{
  "steps": [
    {
      "clip": "<clip_name>",
      "start": <seconds_or_null>,
      "end": <seconds_or_null>,
      "rotate": <-90|90|180|null>,
      "transition_in": <"crossfade"|"fadeblack"|null>,
      "transition_duration": <seconds_or_null>
    }
  ],
  "output_format": "mp4"
}

Rules:
- "clip" must exactly match one of the available clip names
- "start" / "end" in seconds (float), null = from beginning / until end
- "rotate": -90 = left/counter-clockwise, 90 = right/clockwise, 180 = upside down, null = no rotation
- "transition_in": applies between this clip and the previous one (null for first clip or hard cut)
  - "crossfade" = both clips dissolve into each other
  - "fadeblack" = fade to black then fade in
  - null = hard cut
- "transition_duration": seconds for the transition (0.5, 1, 2, etc.), null if no transition
- "last N seconds" of clip with duration D → start = D - N, end = null
- Output ONLY the JSON, no markdown fences, no explanation"""


def parse_instructions(instructions: str, clips: list) -> dict:
    clip_info = "\n".join(
        f"- {c['name']} (duration: {c['duration']:.2f}s)" for c in clips
    )
    user_message = f"Available clips:\n{clip_info}\n\nInstructions: {instructions}"

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
