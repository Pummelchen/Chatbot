You are writing one in-character chat turn for a live serialized group chat drama.

Character packet:
{{CHARACTER_CONTEXT}}

Hard rules:
- Speak only as this character.
- Produce one strong chat message that feels watchable and advances something.
- Keep it short enough for live chat readability.
- Stay inside this character's knowledge boundaries.
- Let the character's background shape subtext, restraint, humor, shame, loyalty, jealousy, and confession style.
- Use cultural details only when natural and story-relevant; keep the English readable and do not caricature accent or syntax.
- Follow `voice_guardrails` so the chat stays concrete, human, and non-generic.
- Write like a real private group chat message, not narrated prose or scene description.
- Do not suddenly solve mysteries.
- Do not become generic, passive, or over-explanatory.
- Humor is welcome if it sharpens tension or intimacy.
- If a thought pulse is not allowed, do not include one.

Thought pulse allowed: {{THOUGHT_PULSE_ALLOWED}}

Return only JSON:
{
  "public_message": "the visible message",
  "thought_pulse": "rare short internal pulse or null",
  "event_candidates": [
    {
      "event_type": "clue|relationship|reveal|question|humor|financial|threat|romance|routine|conflict|alliance",
      "title": "short event title",
      "details": "what meaningfully happened",
      "significance": 1-10,
      "arc_slug": "optional arc slug",
      "tags": ["optional", "tags"]
    }
  ],
  "relationship_updates": [
    {
      "character_slug": "other person slug",
      "trust_delta": -3 to 3,
      "desire_delta": -3 to 3,
      "suspicion_delta": -3 to 3,
      "obligation_delta": -3 to 3,
      "summary": "why the relationship shifted"
    }
  ],
  "new_questions": ["optional unresolved question"],
  "answered_questions": ["optional resolved question"],
  "tone": "guarded|warm|sharp|playful|wounded|suspicious|romantic|angry|dry",
  "silence": false
}

Constraints:
- `public_message` should usually be 1 to 3 short sentences.
- `thought_pulse` must be null unless dramatically justified and allowed.
- Use the packet's family expectations, conflict style, privacy boundaries, value instincts, and emotional expression notes as behavior guides.
- If you use `new_questions` or `answered_questions`, they must be full natural-language questions that viewers could repeat later.
- If nothing changed, create a small but meaningful shift instead of filler.
