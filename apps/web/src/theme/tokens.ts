export type ThemeName = "broadcast";

export const themeNames: readonly ThemeName[] = ["broadcast"];

// Values from docs/DESIGN.md ("Floodlight"). Stored as values, never CSS declarations.
export const themes = {
  broadcast: {
    // Colour
    bg: "#0B4F8A", surface: "#073A69", raised: "#0E5D9F",
    input: "#042848", code: "#042848", shadow: "#042848",
    line: "#3C7CB5", line2: "#1B5C94", strong: "#6A9CC9",
    text: "#FFFFFF", text2: "#E6F0FA", muted: "#D3E5F7",
    chip: "#FFFFFF", ink: "#0A2540",
    lime: "#D7F35B", verified: "#D7F35B", live: "#D7F35B", primary: "#D7F35B",
    stageOn: "#D7F35B", focus: "#D7F35B", ball: "#D7F35B", limeInk: "#14200F",
    amended: "#FF9A3C", amendedInk: "#2E1A00",
    overturned: "#FF5A4E", overturnedInk: "#2E0A06",
    checking: "#FFFFFF", checkingBorder: "#D3E5F7",
    home: "#FFFFFF", homeText: "#FFFFFF", away: "#7CC4FF", awayText: "#A8D8FF",
    pitch: "#0F5A38", pitchFrame: "#FFFFFF", pitchLine: "rgba(255,255,255,0.55)",
    zone: "rgba(215,243,91,0.16)",
    bandA: "#0E5D9F", bandB: "#D7F35B", bandC: "#09457A",
    // Type
    display: "var(--font-display), 'Arial Narrow', sans-serif",
    body: "var(--font-body), system-ui, sans-serif",
    mono: "var(--font-mono), ui-monospace, monospace",
    // Shape and depth
    radius: "0",
    cut: "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)",
    cutTab: "polygon(0 0, 100% 0, calc(100% - 12px) 100%, 0 100%)",
    shadowPanel: "8px 8px 0 var(--mp-shadow)",
    shadowChip: "5px 5px 0 var(--mp-shadow)",
    pitchFrameWidth: "4px",
  },
} as const;

export type ThemeTokens = (typeof themes)[ThemeName];
export type TokenName = keyof ThemeTokens;

export function getTokens(theme: ThemeName): ThemeTokens {
  return themes[theme];
}

export function tokenCssVars(theme: ThemeName): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const [name, value] of Object.entries(themes[theme])) {
    vars[`--mp-${name}`] = value;
  }
  return vars;
}
