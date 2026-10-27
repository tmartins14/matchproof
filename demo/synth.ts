// Splits vo/script.ssml into one request per <voice> block and writes out/vo/segN.wav (48 kHz, 16-bit mono).
// Needs SPEECH_KEY and SPEECH_REGION in the environment.
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const key = process.env.SPEECH_KEY;
const region = process.env.SPEECH_REGION;
if (!key || !region) throw new Error('SPEECH_KEY and SPEECH_REGION must be set');
const ffprobe = process.env.FFPROBE ?? 'ffprobe';

const ssml = readFileSync('vo/script.ssml', 'utf8');
const blocks = [...ssml.matchAll(/<voice [^>]*id="seg(\d)"[^>]*>[\s\S]*?<\/voice>/g)];
let total = 0;
for (const m of blocks) {
  const n = m[1];
  const body = m[0].replace(/ id="seg\d"/, '');
  const doc = `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">${body}</speak>`;
  const res = await fetch(`https://${region}.tts.speech.microsoft.com/cognitiveservices/v1`, {
    method: 'POST',
    headers: {
      'Ocp-Apim-Subscription-Key': key,
      'Content-Type': 'application/ssml+xml',
      'X-Microsoft-OutputFormat': 'riff-48khz-16bit-mono-pcm',
      'User-Agent': 'matchproof-demo',
    },
    body: doc,
  });
  if (!res.ok) throw new Error(`seg${n}: ${res.status} ${await res.text()}`);
  writeFileSync(`out/vo/seg${n}.wav`, Buffer.from(await res.arrayBuffer()));
  const d = parseFloat(execFileSync(ffprobe, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', `out/vo/seg${n}.wav`]).toString());
  total += d;
  console.log(`seg${n}.wav  ${d.toFixed(2)} s`);
}
console.log(`total  ${total.toFixed(2)} s  (limit 98.00)`);
