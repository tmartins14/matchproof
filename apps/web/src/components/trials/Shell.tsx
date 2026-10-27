import type { ReactNode } from "react";

/** The frame every Trials page sits in. The top bar is not here: the root layout renders it once. */
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="tr-page mp-above">
      <main className="tr-main">{children}</main>
    </div>
  );
}
