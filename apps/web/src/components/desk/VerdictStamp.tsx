import type { Copy } from "@/desk/copy";
import type { Verdict } from "@/desk/model";

interface VerdictStampProps {
  verdict: Verdict;
  copy: Copy;
  /** Why the verdict changed; shown on hover and focus for AMENDED and OVERTURNED. */
  reason?: string;
}

export function VerdictStamp({ verdict, copy, reason }: VerdictStampProps) {
  const showReason = reason && (verdict === "rephrased" || verdict === "blocked");
  return (
    <span
      className={`mp-stamp mp-stamp--${verdict}${verdict === "checking" ? " pulse" : ""}`}
      data-verdict={verdict}
      title={showReason ? reason : undefined}
      tabIndex={showReason ? 0 : undefined}
    >
      {copy.verdict[verdict]}
    </span>
  );
}
