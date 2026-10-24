import en from "@/copy/en.json";
import es from "@/copy/es.json";

export type Lang = "en" | "es";
export type Copy = typeof en;

export const copy: Record<Lang, Copy> = { en, es };

/** Fills {name} slots in a copy string. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? ""));
}
