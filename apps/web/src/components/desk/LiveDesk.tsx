"use client";

import { fixture } from "@/desk/fixture";
import type { ReviewState } from "@/desk/reviewParams";
import { useLiveMatch } from "@/live/useLiveMatch";
import { Desk } from "./Desk";

interface LiveDeskProps {
  initial: ReviewState;
}

/** The desk fed by the API: the setup controls call it and the stream fills the desk as the match plays. */
export function LiveDesk({ initial }: LiveDeskProps) {
  const { data, ...live } = useLiveMatch(fixture.brief);
  return <Desk data={data} initial={initial} live={live} />;
}
