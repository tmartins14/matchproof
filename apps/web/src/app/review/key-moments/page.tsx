import type { Lang } from "@/desk/copy";
import { KeyMomentsView } from "./View";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/** Review aid for the key-moment bar: every headline beside every stamp. */
export default async function KeyMoments({ searchParams }: PageProps) {
  const lang: Lang = (await searchParams).lang === "es" ? "es" : "en";
  return <KeyMomentsView lang={lang} />;
}
