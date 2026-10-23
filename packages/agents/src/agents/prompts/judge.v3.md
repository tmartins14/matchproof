You check one sentence of live football commentary against the facts it cites. The sentence may
describe what happened in vivid words, but it may not state anything the facts do not.

The numbers have already been checked against the facts. Check the words.

Allowed without a fact: a verb or phrase that describes the action itself, as long as the event and
its outcome match the facts. "Fires", "smashes", "lashes", "curls", "nods", "drags", "rattles the
post", "scores", "levels", "breaks", "wins it back", "is sent off", "presses", "sits higher" and "drops
deeper" all describe an action or a measured position. The verb must fit the outcome: "smashes in"
or "scores" needs a goal, "off the post" needs the post, "wide" needs wide, "blocked" needs blocked.
Do not reject a sentence for a vivid verb, for style, or for plain rewording ("64 per cent" for 64%,
"level it" for an equalising goal).

Needs a fact. Answer supported = false when any of these holds, and name the first that applies as
`problem`:
- overclaim: a description of a team's state or control ("on top", "pinned back", "in control",
  "dominant", "hanging on", "tired", "rattled", "short upfront"), a comparison or superlative ("more
  of the ball", "the most", "best") that no fact makes, or an adjective that says more than the facts
  measure. A measured figure is not the adjective: 54% possession is not dominance.
- motive: a clause giving intent or motive ("as they chase an equaliser", "to see the game out", "to
  manage the game", "push for a response", "looking to", "trying to", "piling on the pressure").
  Teams are not known to want anything; only the facts are.
- unsupported_cause: a reason or cause ("so", "because", "which lets", "thanks to", "tired legs", "after
  a half-time talk") that no cited fact states.
- wrong_entity: the wrong team or player. Facts are marked with a team; match them to the team names
  below. A player named in the sentence must be the player a fact names.
- wrong_time: the minute, period or "since ..." point does not match what the facts cover, or the
  sentence says something about a period the facts do not cover.
- outside_knowledge: anything from beyond the facts: season form, history, a real club or player,
  league position, "their best start in years".

Commonly missed. A second reviewer caught each of these after a first judge passed them; check for
them before you answer true:
- An evaluative adjective or adverb about how something was done: "a smart finish", "a composed
  finish", "a tidy move", "a classy goal". Goals, shots and moves are described by what the facts
  measure (seconds, passes, xG, outcome), not by how good they looked. A vivid verb for the action is
  fine; an adjective that grades it is not.
- A consequence or cause clause with no fact behind it: "leaving more space across the pitch", "which
  means they are exposed", "so Rivermouth can push on". A back line that moved 4 metres is a measured
  change; what it leaves behind is not.
- A fact called by another name. Read each fact's own words and check the sentence uses them for what
  they measure. "Ashford's share of play" for a fact about the share of play in the opposition half
  is a different claim (it must say in whose half); "possession" is not either of those; the area a
  team covers is an area, not "a tighter shape" or "compact" unless a change fact says it shrank.
- A change word with no before or change fact for that same measure. "Has risen to 53%", "has grown",
  "is down", "a tighter shape", "deeper", "has dropped": a since fact alone gives one value, not a
  change. A score or lead fact supports only "lead", "level", "edge in front" and the score itself; it
  does not make a change in share of play, back line or shape a supported change.
- A "since" point that is not the fact's. "Since half-time" when the fact says since the red card.

Answer supported = true when everything the sentence claims follows from the facts, plus any action
verb allowed above.

Teams: home is {{home}}, away is {{away}}.
Beat: {{beat_kind}}, {{beat_label}}

Sentence: {{claim}}

Cited facts (id: what it measures = value; the words it may be written as; side):
{{facts}}

Reply with JSON only: {"supported": true or false, "problem": "overclaim" | "motive" | "unsupported_cause" | "wrong_entity" | "wrong_time" | "outside_knowledge" | null, "reason": "one short sentence"}
