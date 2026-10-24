/** mm:ss on the match clock, from seconds since kickoff. */
export function formatClock(seconds: number): string {
  const whole = Math.floor(seconds);
  const mm = Math.floor(whole / 60);
  const ss = whole % 60;
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

/** Whole match minutes, for a window edge. */
export function formatMinute(seconds: number): number {
  return Math.round(seconds / 60);
}
