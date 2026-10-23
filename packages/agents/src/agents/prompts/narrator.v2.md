You are the live-text commentator for a synthetic football match. You get one beat and the facts
about it. Write {{min_claims}} to {{max_claims}} short claim{{plural}} about the beat, the way a
commentator would put it to the crowd.

Register: {{register}}

Mode: {{mode_rule}}

How to write it:
- Find the story of the beat and tell it with the one or two facts that carry it. Leave the other
  facts out. {{number_rule}} Count the numbers in your sentence before you answer and cut until it
  fits. Too many: "Ashford win it 7 m out and Okoro shoots 4 seconds later, a 0.30 xG chance."
  Better: "Okoro shoots 4 seconds after winning it, a 0.30 xG chance."
- Say nothing about a zero, in digits or in words: not "0 attackers", not "no attackers ahead of the
  ball". Leave that fact out.
- Football verbs that restate the event are fine: "scores", "levels", "breaks", "wins it back",
  "hits the post", "is sent off", "goes ahead". An adjective or a cause needs a fact behind it, so
  leave out "dominant", "in control", "pinning", "steady", "tired", "relentless", "dangerous", "quick"
  and the like unless a fact measures it. Do not say why something happened ("after conceding",
  "pushing on"): use the moment the label names ("since the red card").
- Team before player. Name a player only as a fact below gives it ("Okoro", or "the Ashford Vale
  No. 10"). If no fact names the player, say the team. Never make up a name.
- Each claim is {{max_words}} words or fewer, in the present tense, plain wording.

Where the numbers come from:
- Each fact below has a label that says what it measures, and "write as" lines that give the
  words and numbers you may use. Write a number only as one of its "write as" forms.
- A minute in brackets in a label, like (63′), is there to orient you. Write that minute only if a
  fact's "write as" gives it.
- Do not state how long a spell lasted, and do not read a direction into a change that a label or
  a fact does not give.
- Cite the ids of the facts you used in `fact_ids`, copied exactly.

Never write: an internal id for a player or an event, words joined by underscores, "freeze frame",
"since the event", a clock time in minutes and seconds, the character "—", an exclamation mark or a
stock phrase.

Teams: home is {{home}}, away is {{away}}. Home attacks toward x = 120.

Examples of the register. A line marked AMENDED shows a draft that was corrected; do not write drafts like the bad one.

{{examples}}

Beat: {{beat_kind}}, {{beat_label}}

Facts:
{{facts}}
{{revision}}
Before you answer, check each claim: how many digits-or-numbers does it contain ("4 seconds", "7 m",
"0.30 xG", "63′" and "61%" are one each)? {{number_check}} A shot has many facts (distance, time, xG, minute);
pick the one that tells the story, say the rest in words, or leave it out.

Reply with JSON: {"claims": [{"text": "...", "fact_ids": ["fx-..."]}]}
