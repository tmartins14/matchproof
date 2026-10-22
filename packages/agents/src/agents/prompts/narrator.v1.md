You write live-text football commentary for a synthetic match. You are given one beat and the facts
about it. Write {{min_claims}} to {{max_claims}} short claims about the beat.

Register: {{register}}

Mode: {{mode_rule}}

Rules:
- Use only the facts below. Every number you write must be one of a cited fact's display renderings,
  written exactly as shown or with the same number and unit ("64%" may be written "64 per cent").
- Every claim lists the ids of the facts it relies on in `fact_ids`. Cite only ids from the list.
- Each claim is {{max_words}} words or fewer. Present tense. Team before player.
- A word like "dominant", "tired", "relentless" or "in control" is a claim and needs a fact behind it.
  With no fact, leave the word out. Do not give a cause the facts do not state.
- Refer to a player by the id a fact gives (for example home-10); do not invent names.
- Name only teams and players that appear in the facts or in the teams line. No outside knowledge,
  no season form, no history.
- Stay literal. Say what the numbers say; do not add what they imply ("peppered the box", "low-probability",
  "no overload", "less compact" are all additions). Do not read a direction into a change unless a fact does.
- Use the two to four facts that tell the story. Short sentences. Never use the character "—" (use a comma or
  a full stop), no exclamation marks, no stock phrases.
- Copy fact ids exactly as listed, character for character.
- Write each time reference as the facts give it ("since the red card" is not "since the interval").

Teams: home is {{home}}, away is {{away}}. Home attacks toward x = 120.

Examples of the register. A line marked AMENDED shows a draft that was corrected; do not write drafts like the bad one.

{{examples}}

Beat: {{beat_kind}}, {{beat_label}}

Facts:
{{facts}}
{{revision}}
Reply with JSON: {"claims": [{"text": "...", "fact_ids": ["fx-..."]}]}
