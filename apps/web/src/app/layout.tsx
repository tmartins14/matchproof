import type { ReactNode } from "react";
import type { CSSProperties } from "react";
import { Archivo, Archivo_Narrow, Geist_Mono } from "next/font/google";
import { tokenCssVars } from "@/theme/tokens";
import "./desk.css";

export const metadata = { title: "Matchproof live desk" };

const display = Archivo_Narrow({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-display", display: "swap" });
const body = Archivo({ subsets: ["latin"], weight: ["400", "500", "600", "800"], variable: "--font-body", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono", display: "swap" });

export default function RootLayout({ children }: { children: ReactNode }) {
  // Tokens are written once, here, as --mp-<token> custom properties.
  const vars = tokenCssVars("broadcast") as CSSProperties;
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`} style={vars}>
      <body>{children}</body>
    </html>
  );
}
