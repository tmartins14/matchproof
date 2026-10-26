"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { copy } from "@/desk/copy";
import { fill } from "@/desk/copy";
import { isSmoke, web } from "@/trials/data";
import { runDate } from "@/trials/format";
import { Wordmark } from "../desk/Wordmark";

type Page = "table" | "fixtures" | "compare" | "desk";
const STEP: Record<Page, 1 | 2 | 3> = { table: 1, fixtures: 2, compare: 2, desk: 3 };
const HREF: Record<Page, string> = { table: "/", fixtures: "/fixtures", compare: "/compare", desk: "/desk" };
const ORDER: Page[] = ["table", "fixtures", "compare", "desk"];

export function pageOf(pathname: string): Page {
  if (pathname.startsWith("/compare")) return "compare";
  if (pathname.startsWith("/fixtures")) return "fixtures";
  if (pathname.startsWith("/desk")) return "desk";
  return "table";
}

export function TopBar() {
  const t = copy.en.trials;
  const page = pageOf(usePathname());
  const lit = STEP[page];
  const steps = [t.stepper.rank, t.stepper.inspect, t.stepper.deploy];
  return (
    <header className="tr-bar mp-above">
      <Wordmark first={t.lockup.first} second={t.lockup.second} />
      <nav className="tr-nav" aria-label={t.nav.label}>
        {ORDER.map((p) => (
          <Link key={p} href={HREF[p]} className="tr-nav-link" aria-current={p === page ? "page" : undefined}>
            {t.nav[p]}
          </Link>
        ))}
      </nav>
      <ol className="tr-steps" aria-label={t.stepper.label}>
        {steps.map((label, i) => (
          <li key={label} className="tr-step" aria-current={i + 1 === lit ? "step" : undefined}>
            <span className="tr-step-n">{i + 1}</span> {label}
          </li>
        ))}
      </ol>
      <div className="tr-run">
        {isSmoke ? <span className="tr-chip">{t.smokeChip}</span> : null}
        <span className="tr-mono">{fill(t.run, { pack: web.pack, date: runDate(web.results.run_at) })}</span>
      </div>
    </header>
  );
}
