# Specialization test: request reading with vs without few-shot examples

Run 2026-11-15 14:49 with `python eval.py --parser`. Each request was read 2 times by each variant; a check counts once per run.

| Request | Check | Few-shot | Zero-shot |
|---|---|---|---|
| need something with no vocals for deep work | asks for instrumental (>= 0.7) | 2/2 | 2/2 |
| play me some happy pop | pop marked as explicit | 2/2 | 2/2 |
| play me some happy pop | no made-up vocal/speech limits | 2/2 | 2/2 |
| wahala everywhere today, I need to cool down | calm mood | 2/2 | 2/2 |
| wahala everywhere today, I need to cool down | energy <= 0.5 | 2/2 | 2/2 |
| wahala everywhere today, I need to cool down | detected as Pidgin | 2/2 | 2/2 |
| oya make we jaiye this weekend | party energy >= 0.75 | 2/2 | 2/2 |
| oya make we jaiye this weekend | detected as Pidgin | 2/2 | 2/2 |
| chill afrobeats for my drive | afrobeats marked as explicit | 2/2 | 2/2 |
| chill afrobeats for my drive | energy 0.4-0.7 | 2/2 | 2/2 |
| something that sounds like the 90s | decade 1990 | 2/2 | 2/2 |
| music for a quiet night in | genre not marked explicit | 2/2 | 2/2 |
| music for a quiet night in | no decade invented | 2/2 | 2/2 |
| some country for my road trip | country marked as explicit | 2/2 | 2/2 |
| tango for my dance class | keeps 'tango' as the requested genre | 2/2 | 2/2 |
| write me a cover letter for a bank job | not a music request | 2/2 | 2/2 |
| body no fit, I dey feel low today | low valence <= 0.45 | 2/2 | 2/2 |
| body no fit, I dey feel low today | detected as Pidgin | 2/2 | 2/2 |
| rap with lots of bars | hip hop or wordy (speechiness >= 0.25) | 2/2 | 2/2 |

**Few-shot passed 38/38 checks (100%); zero-shot passed 38/38 (100%).**
