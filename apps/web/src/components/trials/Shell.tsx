import type { ReactNode } from "react";
import { TopBar } from "./TopBar";

/** The frame every Trials page sits in: the top bar, then the page. */
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="tr-page">
      <TopBar />
      <main className="tr-main">{children}</main>
    </div>
  );
}
