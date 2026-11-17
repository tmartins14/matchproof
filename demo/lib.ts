import { readFileSync } from 'node:fs';

/** Plain spoken text per segment, taken from vo/script.ssml so captions and cues follow the voiceover. */
export function segmentTexts(): Record<number, string> {
  const ssml = readFileSync(new URL('./vo/script.ssml', import.meta.url), 'utf8');
  const out: Record<number, string> = {};
  for (const m of ssml.matchAll(/<!-- seg(\d) -->([\s\S]*?)(?=<!-- seg\d -->|<\/voice>)/g)) {
    out[Number(m[1])] = (m[2] ?? '')
      .replace(/<sub alias="([^"]*)">[^<]*<\/sub>/g, '$1')
      .replace(/<[^>]+>/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }
  return out;
}

/** Duration in seconds of a 16-bit mono PCM WAV, read from its data chunk. */
export function wavDuration(path: string): number {
  const buf = readFileSync(path);
  const rate = buf.readUInt32LE(24);
  const bytesPerFrame = buf.readUInt16LE(32);
  let pos = 12;
  while (pos + 8 <= buf.length) {
    const id = buf.toString('ascii', pos, pos + 4);
    const size = buf.readUInt32LE(pos + 4);
    if (id === 'data') return Math.min(size, buf.length - pos - 8) / (rate * bytesPerFrame);
    pos += 8 + size;
  }
  throw new Error(`no data chunk in ${path}`);
}
