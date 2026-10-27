// Writes out/matchproof-demo.srt from the voiceover text and real segment timings.
// Usage: tsx captions.ts <brag seconds> <seg1 s> <seg2 s> <seg3 s> <seg4 s> <seg5 s>
import { writeFileSync } from 'node:fs';
import { segmentTexts } from './lib.ts';

const [brag, ...durs] = process.argv.slice(2).map(Number);
if (brag === undefined || durs.length !== 5) throw new Error('need brag duration and five segment durations');
const texts = segmentTexts();

const stamp = (t: number): string => {
  const ms = Math.round(t * 1000);
  const p = (v: number, w: number): string => String(v).padStart(w, '0');
  return `${p(Math.floor(ms / 3_600_000), 2)}:${p(Math.floor(ms / 60_000) % 60, 2)}:${p(Math.floor(ms / 1000) % 60, 2)},${p(ms % 1000, 3)}`;
};

/** Sentences, further split at word boundaries so no caption runs past ~84 characters. */
function chunks(text: string): string[] {
  const out: string[] = [];
  for (const sentence of text.split(/(?<=[.!?:])\s+/)) {
    const words = sentence.split(' ');
    const pieces = Math.ceil(sentence.length / 84);
    const per = Math.ceil(words.length / pieces);
    for (let i = 0; i < words.length; i += per) out.push(words.slice(i, i + per).join(' '));
  }
  return out;
}

function wrap(line: string): string {
  if (line.length <= 42) return line;
  const words = line.split(' ');
  let best = 0;
  let acc = 0;
  for (let i = 0; i < words.length - 1; i++) {
    acc += words[i]!.length + 1;
    if (Math.abs(acc - line.length / 2) < Math.abs(best - line.length / 2) || best === 0) best = acc;
  }
  return `${line.slice(0, best).trim()}\n${line.slice(best).trim()}`;
}

let offset = brag;
let index = 1;
let srt = '';
durs.forEach((d, i) => {
  const parts = chunks(texts[i + 1] ?? '');
  const total = parts.reduce((a, p) => a + p.length, 0);
  let t = offset;
  for (const p of parts) {
    const len = (p.length / total) * d;
    srt += `${index++}\n${stamp(t)} --> ${stamp(t + len - 0.05)}\n${wrap(p)}\n\n`;
    t += len;
  }
  offset += d;
});
writeFileSync('out/matchproof-demo.srt', srt);
console.log(`out/matchproof-demo.srt: ${index - 1} cues`);
