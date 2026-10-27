// Synthesizes vo/script.ssml in ONE request so the delivery is continuous, then splits the audio on the
// 700 ms breaks into out/vo/seg1..seg5.wav (48 kHz, 16-bit mono). Segment 1 has its leading silence removed.
// Needs SPEECH_KEY and SPEECH_REGION in the environment; FFMPEG/FFPROBE default to the PATH.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { execFileSync, spawnSync } from 'node:child_process';
import { segmentTexts } from './lib.ts';

const key = process.env.SPEECH_KEY;
const region = process.env.SPEECH_REGION;
if (!key || !region) throw new Error('SPEECH_KEY and SPEECH_REGION must be set');
const ffmpeg = process.env.FFMPEG ?? 'ffmpeg';
const ffprobe = process.env.FFPROBE ?? 'ffprobe';
const CEILING = 89;

mkdirSync('out/vo', { recursive: true });
const ssml = readFileSync('vo/script.ssml', 'utf8').replace(/<!--[\s\S]*?-->/g, '');
const res = await fetch(`https://${region}.tts.speech.microsoft.com/cognitiveservices/v1`, {
  method: 'POST',
  headers: {
    'Ocp-Apim-Subscription-Key': key,
    'Content-Type': 'application/ssml+xml',
    'X-Microsoft-OutputFormat': 'riff-48khz-16bit-mono-pcm',
    'User-Agent': 'matchproof-demo',
  },
  body: ssml,
});
if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
writeFileSync('out/vo/all.wav', Buffer.from(await res.arrayBuffer()));

const probe = (f: string): number => parseFloat(execFileSync(ffprobe, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
const total = probe('out/vo/all.wav');

// Cut through the silence nearest each expected break (by character share of the text) that is long enough to be a
// 700 ms break rather than a sentence pause. The silence threshold sits above this voice's noise floor.
const log = spawnSync(ffmpeg, ['-hide_banner', '-i', 'out/vo/all.wav', '-af', 'silencedetect=n=-30dB:d=0.35', '-f', 'null', '-'], { encoding: 'utf8' }).stderr;
const starts = [...log.matchAll(/silence_start: ([\d.]+)/g)].map((m) => parseFloat(m[1]!));
const ends = [...log.matchAll(/silence_end: ([\d.]+) \| silence_duration: ([\d.]+)/g)].map((m) => ({ end: parseFloat(m[1]!), len: parseFloat(m[2]!) }));
const gaps = ends.map((e, i) => ({ mid: (starts[i]! + e.end) / 2, len: e.len })).filter((g) => g.len >= 0.6 && g.mid < total - 0.3);
const texts = segmentTexts();
const chars = [1, 2, 3, 4, 5].map((n) => texts[n]!.length);
const all = chars.reduce((a, c) => a + c, 0);
const cuts: Array<{ mid: number; len: number }> = [];
let acc = 0;
for (let i = 0; i < 4; i++) {
  acc += chars[i]!;
  const expected = (acc / all) * total;
  cuts.push([...gaps].sort((a, b) => Math.abs(a.mid - expected) - Math.abs(b.mid - expected))[0]!);
}
console.log('breaks at', cuts.map((c) => `${c.mid.toFixed(2)} s (${c.len.toFixed(2)} s long)`).join(', '));

const bounds = [0, ...cuts.map((c) => c.mid), total];
let sum = 0;
for (let i = 0; i < 5; i++) {
  const args = ['-v', 'error', '-y', '-i', 'out/vo/all.wav', '-ss', String(bounds[i]), '-to', String(bounds[i + 1])];
  if (i === 0) args.push('-af', 'silenceremove=start_periods=1:start_threshold=-45dB');
  execFileSync(ffmpeg, [...args, `out/vo/seg${i + 1}.wav`]);
  const d = probe(`out/vo/seg${i + 1}.wav`);
  sum += d;
  console.log(`seg${i + 1}.wav  ${d.toFixed(2)} s`);
}
console.log(`total  ${sum.toFixed(2)} s  (ceiling ${CEILING})`);
if (sum > CEILING) { console.error('over the ceiling: apply the trim order and re-synthesize'); process.exit(1); }
