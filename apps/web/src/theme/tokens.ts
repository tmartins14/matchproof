export type ThemeName = "broadcast" | "editorial";

export const themeNames: readonly ThemeName[] = ["broadcast", "editorial"];

// Copied from tokens() in docs/prototype/Main.dc.html (same keys and values).
export const themes = {
  broadcast: {
    bg: "#0E1620", surface: "#16212D", raised: "#1F2C3A", input: "#0E1620", code: "#0E1620",
    line: "#2A3A4C", line2: "#22303F", strong: "#3A4D63", track: "#24313F",
    text: "#EEF2F6", text2: "#C9D3DE", muted: "#9DAABB",
    riv: "#F0506E", ash: "#6FB4FF", rivText: "#F7A3B4", ashText: "#A9D2FF", rivChip: "#1A0710", ashChip: "#071526",
    pitch: "#10261A", pitchBorder: "#10261A", pitchLine: "#FFFFFF", pitchOp: "0.24", pitchText: "#C9D3DE", goalRing: "#10261A", attack: "#FFC2CD",
    liveBg: "#3A1218", liveText: "#FFB3B3", liveDot: "#FF3B3B",
    primaryBg: "#EEF2F6", primaryText: "#0E1620", segOnBg: "#EEF2F6", segOnText: "#0E1620", segOff: "#9DAABB",
    selBg: "#1F2C3A", selBorder: "#6FB4FF", cardActive: "#16212D", cardBorderActive: "#3A4D63", cardBorder: "#22303F", claimBg: "#0E1620", claimBorder: "#22303F",
    checking: "#C9D3DE", checkingBorder: "#6C7A8C", verified: "#3FD6A6", rephrased: "#F6C445", blocked: "#FF6B4A",
    stageOn: "#FF3B3B", hot: "#FFB3B3", zone: "rgba(240,80,110,0.12)",
    warnBg: "#3A2A10", warnText: "#F6D58A", realBand: "#24405E", focus: "#6FB4FF", ball: "#FFFFFF",
    display: "'Barlow Condensed', 'Arial Narrow', sans-serif", dw: 700, body: "'Barlow', system-ui, sans-serif", mono: "'IBM Plex Mono', ui-monospace, monospace"
  },
  editorial: {
    bg: "#FAF7F0", surface: "#FFFDF8", raised: "#F3EEE3", input: "#FFFDF8", code: "#F3EEE3",
    line: "#E5E1D6", line2: "#ECE8DF", strong: "#CFC8B8", track: "#E5DFD2",
    text: "#171717", text2: "#404040", muted: "#5C5C5C",
    riv: "#9F1239", ash: "#1E3A5F", rivText: "#9F1239", ashText: "#1E3A5F", rivChip: "#FFFDF8", ashChip: "#FFFDF8",
    pitch: "#FFFDF8", pitchBorder: "#E5E1D6", pitchLine: "#1E3A5F", pitchOp: "0.38", pitchText: "#404040", goalRing: "#FFFDF8", attack: "#9F1239",
    liveBg: "#FBE7EC", liveText: "#7A0E2C", liveDot: "#B42318",
    primaryBg: "#171717", primaryText: "#FAF7F0", segOnBg: "#171717", segOnText: "#FAF7F0", segOff: "#5C5C5C",
    selBg: "#FBEFF2", selBorder: "#9F1239", cardActive: "#FFFDF8", cardBorderActive: "#CFC8B8", cardBorder: "#E5E1D6", claimBg: "#FAF7F0", claimBorder: "#E5E1D6",
    checking: "#5C5C5C", checkingBorder: "#8A8578", verified: "#1E6B52", rephrased: "#8A5A00", blocked: "#B42318",
    stageOn: "#B42318", hot: "#9F1239", zone: "rgba(159,18,57,0.09)",
    warnBg: "#FBE7EC", warnText: "#7A0E2C", realBand: "#DCE4EE", focus: "#9F1239", ball: "#171717",
    display: "'Fraunces', Georgia, serif", dw: 900, body: "'Geist', system-ui, sans-serif", mono: "'Geist Mono', ui-monospace, monospace"
  },
} as const;

export type ThemeTokens = (typeof themes)[ThemeName];

export function getTokens(theme: ThemeName): ThemeTokens {
  return themes[theme];
}
