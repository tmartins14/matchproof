# Matchproof demo video — script, shot list and build

**Timing:** brag 0:21 + walkthrough 1:35 = **1:56 total** (hard ceiling 2:00).
Walkthrough segments: 0:12 + 0:28 + 0:24 + 0:19 + 0:12 = **1:35**.
The voiceover is about 232 words, roughly 1:30 spoken, so each segment holds a beat or two longer than its words.

Numbers are from main's export (Oct 27). **Re-check the Table before recording; the screen wins over the script.**

Naming: **Matchproof** is the system; **Narrator Trials** is the exam it is running here. Never present them as two products.

## Segments

| # | Length | On screen | Voiceover (spoken form) |
| --- | --- | --- | --- |
| 0 | 0:21 | The existing brag clip (`brag-output/`). | (as recorded) |
| 1 | 0:12 | Desk mid-match: a claim reading CHECKING, then the STANDS stamp landing. | Broadcasters want AI commentary. But a fluent sentence can still be wrong, and live, there's no undo. So before any model gets the mic, it has to pass this test. |
| 2 | 0:28 | Table. Slow scroll down the rows, then highlight: the Traps column, Grok's p90, the GPT-4.1 row, the Live pick card, nano's NOT CLEARED tag. | Six narrators call the same seeded matches, each with planted traps: a red card, a stoppage-time penalty, a late winner. One fixed referee scores every claim. Grok four point seven tops the table, but takes seventy seconds a claim. GPT four point one fell for none of the fourteen traps, in under three seconds. That's the live pick. GPT five nano fell for eight. Not cleared. |
| 3 | 0:24 | Compare at `/compare/fx-02/bt-001815-set_piece_goal?focus=gpt-5-nano`. Pan the cards, zoom on nano's OVERTURNED reason, then cut to an AMENDED redline. | Click any narrator to see its worst moment beside the others. Same frame, same facts. Here, five narrators named the right scorer. But nano couldn't point to the fact that names him, so it never aired. True isn't enough. It has to be provable. And when the referee fixes wording, you see exactly what changed. |
| 4 | 0:19 | Use on Desk → Run live, GPT-4.1 on fx-05 (the 11′ penalty is the first trap). CHECKING, then the stamp, then the evidence on the pitch. | Then deploy. Use on Desk puts a cleared narrator on a live match. GPT four point one narrates, and every claim shows checking, then stands, amended or overturned, with the evidence on the pitch. Nothing goes on air until it survives review. |
| 5 | 0:12 | Back to the Table. Overlay: matchproof.tylermartins.com and "Microsoft Foundry · Agent Framework · Azure". | The narrator is replaceable. The exam and the referee are the asset. That's Matchproof. Built on Microsoft Foundry, Agent Framework and Azure. Rig the match. Catch the narrator. |

## Trim order, if the voiceover runs past 1:35

1. Segment 2: drop "a red card, a stoppage-time penalty, a late winner".
2. Segment 3: drop "And when the referee fixes wording, you see exactly what changed" and the redline shot.
3. Segment 5: drop "Rig the match. Catch the narrator."
4. Segment 1: drop "So before any model gets the mic, it has to pass this test."

## If the live run fails on the day

Use Replay pack run for the same model and change segment 4's second line to: "Use on Desk replays a cleared narrator over the same match." Never call a cached replay live.

## Voice settings

Azure AI Speech, neural voice (en-US-AndrewNeural or en-US-AvaNeural), rate +5%. A 400 ms break after: "pass this test.", "Not cleared.", "It has to be provable.", "That's Matchproof." Keep "GPT" as letters; check "Grok", "Matchproof" and "nano" on playback.
