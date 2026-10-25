import type { Beat, Claim, Event, Fact, PositionFrame, Status, StreamMessage } from "@/contracts/types";
import type { DeskData, Phase, RunningMetric } from "@/desk/deskData";

const TICKER_LEN = 5;
const RUNNING = /^(possession_share|shots|shots_on_target|xg)\((home|away), to (\d+)′\)$/;
const MOMENTUM = /^momentum\(min-(\d{2})\)$/;

const PHASES: Partial<Record<Status["state"], Phase>> = {
  pre_match: "connecting",
  live: "live",
  focus: "focus",
  freeze: "freeze",
  half_time: "half_time",
  full_time: "full_time",
  error: "error",
};

/** Looks a fact up by its name; the running totals and momentum are found by name, never computed. */
function indexFact(d: DeskData, fact: Fact): void {
  const running = RUNNING.exec(fact.name);
  if (running) {
    const [, metric, side, minuteText] = running;
    const minute = Number(minuteText);
    let mark = d.running.find((m) => m.minute === minute);
    if (!mark) {
      mark = { minute, t_to: 0, facts: {} };
      d.running.push(mark);
      d.running.sort((a, b) => a.minute - b.minute);
    }
    const sides = (mark.facts[metric as RunningMetric] ??= {});
    sides[side as "home" | "away"] = fact.id;
    if (fact.scope?.t_to !== undefined) mark.t_to = fact.scope.t_to;
    return;
  }
  const momentum = MOMENTUM.exec(fact.name);
  if (momentum) d.momentum[Number(momentum[1]) - 1] = fact.id;
}

function addClaim(d: DeskData, incoming: Claim): void {
  const slot = d.claimSlot.get(incoming.id);
  if (slot === undefined) {
    d.claimSlot.set(incoming.id, d.claims.length);
    d.claims.push(incoming);
    return;
  }
  // The last message per claim wins. A correction carries the new text; the first draft is kept.
  const previous = d.claims[slot];
  d.claims[slot] = previous?.draft_text && !incoming.draft_text ? { ...incoming, draft_text: previous.draft_text } : incoming;
}

function addStatus(d: DeskData, status: Status, nextId: number): DeskData {
  const out: DeskData = { ...d };
  if (status.speed !== undefined) out.speed = status.speed;
  if (status.state === "score") {
    if (status.score) out.score = status.score;
    return out;
  }
  if (status.state === "notice") {
    if (status.message) out.notices = [...d.notices, { id: nextId, text: status.message }];
    return out;
  }
  const phase = PHASES[status.state];
  if (phase) out.phase = phase;
  if (status.state === "full_time" && status.score) out.score = status.score;
  if (status.state === "freeze") {
    out.freezeEventId = status.event_id;
    out.awaitingFreezeFrame = true;
  }
  return out;
}

/**
 * One stream message into the desk data, in constant time. The collections (events, facts, claims,
 * beats, frames) are appended to in place and the returned object is new, so a render that compares
 * the result with the previous one sees the change; nothing is copied per message.
 */
export function accumulate(d: DeskData, msg: StreamMessage): DeskData {
  const next: DeskData = { ...d, clock: Math.max(d.clock, msg.t) };
  switch (msg.type) {
    case "event": {
      const event = msg.data as Event;
      d.events.push(event);
      const ticker = [...d.ticker_event_ids, event.id];
      next.ticker_event_ids = ticker.length > TICKER_LEN ? ticker.slice(-TICKER_LEN) : ticker;
      next.counts = { ...d.counts, events: d.counts.events + 1 };
      return next;
    }
    case "frame": {
      const frame = msg.data as PositionFrame;
      next.liveFrame = frame;
      if (d.awaitingFreezeFrame && d.freezeEventId) {
        d.frames[d.freezeEventId] = frame;
        next.awaitingFreezeFrame = false;
      } else if (d.phase === "freeze") {
        next.phase = "focus"; // the hold is over: play resumes inside the focus window
      }
      return next;
    }
    case "fact": {
      const fact = msg.data as Fact;
      if (d.factIds.has(fact.id)) return next;
      d.factIds.add(fact.id);
      d.facts.push(fact);
      indexFact(d, fact);
      next.counts = { ...d.counts, facts: d.counts.facts + 1 };
      return next;
    }
    case "beat": {
      const beat = msg.data as Beat;
      d.beats.push(beat);
      if (beat.highlight) d.highlights[beat.id] = beat.highlight;
      return next;
    }
    case "claim":
    case "verdict":
      addClaim(d, msg.data as Claim);
      return next;
    case "status":
      return { ...addStatus(next, msg.data as Status, msg.seq) };
  }
}
