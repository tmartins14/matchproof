import type { Claim } from "@/contracts/types";
import { overturnedLines } from "@/desk/claimLines";
import type { Copy } from "@/desk/copy";

interface OverturnedLinesProps {
  claim: Claim;
  copy: Copy;
  display?: boolean;
}

/** Every attempt at an overturned claim, struck, with its label. The reason follows in the caller. */
export function OverturnedLines({ claim, copy, display = false }: OverturnedLinesProps) {
  const lines = overturnedLines(claim, copy);
  return (
    <>
      {lines.map((line) => (
        <span key={line.text} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {line.label ? <span className="mp-muted" style={{ fontSize: 13 }}>{line.label}</span> : null}
          <span
            className={`mp-struck${display ? " display" : ""}`}
            style={display ? { fontSize: 22, fontWeight: 600, lineHeight: 1.25 } : { fontWeight: 500, lineHeight: 1.35 }}
          >
            {line.text}
          </span>
        </span>
      ))}
    </>
  );
}
