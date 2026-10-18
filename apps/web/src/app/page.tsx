import type { Event } from "@/contracts/types";
import { getTokens } from "@/theme/tokens";

// Proves the generated-types wiring: this fails to compile if the event schema drops "home".
const side: Event["side"] = "home";

export default function Home() {
  const tokens = getTokens("broadcast");
  return (
    <main style={{ background: tokens.bg, color: tokens.text }} data-side={side}>
      <h1>Matchproof</h1>
    </main>
  );
}
