import type { ReactNode } from "react";
import type { CSSProperties } from "react";
import localFont from "next/font/local";
import { tokenCssVars } from "@/theme/tokens";
import { Backdrop } from "@/components/desk/Backdrop";
import { TopBar } from "@/components/trials/TopBar";
import "./desk.css";
import "./trials.css";

export const metadata = { title: "Matchproof Narrator Trials" };

// Latin subsets, committed under ./fonts (SIL Open Font License; texts in docs/compliance/fonts), so a build never reaches a font service.
const display = localFont({
  src: [
    { path: "./fonts/archivo-narrow-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/archivo-narrow-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-display",
  display: "swap",
});
const body = localFont({
  src: [
    { path: "./fonts/archivo-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/archivo-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/archivo-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/archivo-800.woff2", weight: "800", style: "normal" },
  ],
  variable: "--font-body",
  display: "swap",
});
const mono = localFont({
  src: [
    { path: "./fonts/geist-mono-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/geist-mono-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono",
  display: "swap",
});

export default function RootLayout({ children }: { children: ReactNode }) {
  // Tokens are written once, here, as --mp-<token> custom properties.
  const vars = tokenCssVars("broadcast") as CSSProperties;
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`} style={vars}>
      <body>
        <TopBar />
        {/* One backdrop for every page, below the bar. */}
        <div className="mp-root">
          <Backdrop />
          {children}
        </div>
      </body>
    </html>
  );
}
