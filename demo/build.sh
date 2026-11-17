#!/usr/bin/env bash
# Assembles out/matchproof-demo.mp4 from the brag clip, the five recorded segments and their voiceover.
# Needs out/vo/seg{1..5}.wav and out/clips/seg{1..5}.{webm,json} (see synth.ts and record.ts).
set -euo pipefail
cd "$(dirname "$0")"

FFMPEG="${FFMPEG:-$(node -p "require('ffmpeg-static')")}"
FFPROBE="${FFPROBE:-$(node -p "require('ffprobe-static').path")}"
BRAG="${BRAG:-../brag-output/brag.mp4}"
LIMIT=115   # fail the build at 1:55; the hard ceiling is 2:00
XFADE=0.5    # brag -> seg1 video dissolve
AFADE=0.3    # brag -> seg1 audio crossfade
VO_DELAY=0.4 # seg1 voiceover starts this long after the dissolve completes
OUT=out/matchproof-demo.mp4
TMP=out/build
rm -rf "$TMP" && mkdir -p "$TMP"

dur() { "$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$1"; }
VF="scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
ENC=(-c:v libx264 -preset veryfast -crf 12 -pix_fmt yuv420p -r 30 -c:a pcm_s16le -ar 48000 -ac 2)

# Segment 0: the brag clip as recorded.
"$FFMPEG" -v error -y -i "$BRAG" -vf "$VF" -af "aresample=48000,aformat=channel_layouts=stereo" "${ENC[@]}" "$TMP/seg0.mkv"
BRAG_D=$(dur "$TMP/seg0.mkv")

# Segments 1-5: keep the cuts from the manifest, hold the last frame if short, trim to the voiceover.
CLIPLEN=("$BRAG_D") VOLEN=("$BRAG_D") FINAL=("$BRAG_D")
# Segment 1's clip carries the dissolve and the delay: video = XFADE + VO_DELAY + vo, audio = (XFADE - AFADE) + VO_DELAY + vo.
for n in 1 2 3 4 5; do
  vo=$(dur "out/vo/seg$n.wav")
  read -r kept filter < <(node -e '
    const m = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
    if (!m.cuts.length) { console.error("no cuts for seg" + process.argv[2]); process.exit(1); }
    const parts = m.cuts.map(([a, b], i) => `[0:v]trim=${a}:${b},setpts=PTS-STARTPTS,'"$VF"'[v${i}]`);
    const kept = m.cuts.reduce((t, [a, b]) => t + (b - a), 0);
    const cat = m.cuts.length > 1 ? `${m.cuts.map((_, i) => `[v${i}]`).join("")}concat=n=${m.cuts.length}:v=1:a=0[vc]` : "[v0]null[vc]";
    console.log(kept, (parts.concat(cat)).join(";"));
  ' "out/clips/seg$n.json" "$n")
  vlen=$vo alen=$vo delay=0 final=$vo
  if [ "$n" = 1 ]; then
    vlen=$(awk -v v="$vo" -v x="$XFADE" -v d="$VO_DELAY" 'BEGIN{printf "%.3f", v+x+d}')
    delay=$(awk -v x="$XFADE" -v f="$AFADE" -v d="$VO_DELAY" 'BEGIN{printf "%d", (x-f+d)*1000}')
    alen=$(awk -v v="$vo" -v m="$delay" 'BEGIN{printf "%.3f", v+m/1000}')
    final=$(awk -v v="$vo" -v d="$VO_DELAY" 'BEGIN{printf "%.3f", v+d}')
  fi
  "$FFMPEG" -v error -y -i "out/clips/seg$n.webm" -i "out/vo/seg$n.wav" \
    -filter_complex "$filter;[vc]tpad=stop_mode=clone:stop_duration=5,trim=duration=$vlen,setpts=PTS-STARTPTS[v];[1:a]adelay=${delay}:all=1,apad,atrim=0:$alen,aformat=channel_layouts=stereo[a]" \
    -map "[v]" -map "[a]" "${ENC[@]}" "$TMP/seg$n.mkv"
  CLIPLEN+=("$kept") VOLEN+=("$vo") FINAL+=("$final")
done

node captions.ts "$(awk -v b="$BRAG_D" -v d="$VO_DELAY" 'BEGIN{printf "%.3f", b+d}')" "${VOLEN[@]:1}"

# Concatenate, normalise to -16 LUFS in two passes, encode once.
INPUTS=() CAT=""
for n in 0 1 2 3 4 5; do INPUTS+=(-i "$TMP/seg$n.mkv"); CAT+="[$n:v][$n:a]"; done
OFFSET=$(awk -v b="$BRAG_D" -v x="$XFADE" 'BEGIN{printf "%.3f", b-x}')
VGRAPH="[0:v][1:v]xfade=transition=fade:duration=${XFADE}:offset=${OFFSET},format=yuv420p,setsar=1,fps=30[xv];[xv][2:v][3:v][4:v][5:v]concat=n=5:v=1:a=0[v]"
AGRAPH="[0:a][1:a]acrossfade=d=${AFADE}[xa];[xa][2:a][3:a][4:a][5:a]concat=n=5:v=0:a=1[a]"
CONCAT="${VGRAPH};${AGRAPH}"
LN="I=-16:TP=-1.5:LRA=11"
STATS=$("$FFMPEG" -hide_banner -y "${INPUTS[@]}" -filter_complex "${CONCAT};[v]nullsink;[a]loudnorm=${LN}:print_format=json[an]" -map "[an]" -f null - 2>&1)
get() { printf '%s' "$STATS" | sed -n "s/.*\"$1\" *: *\"\([^\"]*\)\".*/\1/p" | tail -1; }
MEAS="measured_I=$(get input_i):measured_TP=$(get input_tp):measured_LRA=$(get input_lra):measured_thresh=$(get input_thresh):offset=$(get target_offset)"
"$FFMPEG" -v error -y "${INPUTS[@]}" -i out/matchproof-demo.srt \
  -filter_complex "${CONCAT};[a]loudnorm=${LN}:${MEAS}:linear=true[an]" \
  -map "[v]" -map "[an]" -map 6:s -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ar 48000 -c:s mov_text -metadata:s:s:0 language=eng -movflags +faststart "$OUT"

# Per-segment table and the length gate.
TOTAL=$(dur "$OUT")
printf '\n%-8s %10s %10s %12s\n' segment clip_s vo_s cumulative_s
cum=0
for i in 0 1 2 3 4 5; do
  cum=$(awk -v c="$cum" -v f="${FINAL[$i]}" 'BEGIN{printf "%.2f", c+f}')
  label=$([ "$i" = 0 ] && echo "0 brag" || echo "$i")
  printf '%-8s %10.2f %10.2f %12s\n' "$label" "${CLIPLEN[$i]}" "${VOLEN[$i]}" "$cum"
done
printf 'total    %.2f s\n' "$TOTAL"
awk -v t="$TOTAL" -v l="$LIMIT" 'BEGIN{ if (t > l) { printf "FAIL: %.2f s exceeds %d s\n", t, l; exit 1 } }'
"$FFMPEG" -hide_banner -nostats -i "$OUT" -af ebur128 -f null - 2>&1 | grep -E "^\s+I:" | tail -1 | sed 's/^ */integrated loudness: /'
echo "wrote $OUT"
