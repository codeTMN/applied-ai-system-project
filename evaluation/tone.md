# Specialization test: DJ tone/style rules vs a plain baseline

Run 2026-11-15 14:56 with `python eval.py --tone`. Same request, same 5 songs, same facts; only the system prompt differs. *Specialized* = Vibe DJ's rules (match the user's language, describe numbers in words, never name other artists, max 35 words per song). *Baseline* = "You are a helpful assistant. Write a short description of this playlist for the user."

| Measure | Specialized | Baseline |
|---|---|---|
| Pidgin words per reply, Pidgin requests (higher = matches the user) | 4.0 | 1.0 |
| Pidgin words in replies to English requests (should be 0) | 0 | 0 |
| Raw numbers like 0.87 quoted (should be 0) | 0 | 0 |
| Replies that fail the output guardrail | 0/7 | 0/7 |
| Replies with every 'why' <= 35 words | 7/7 | 7/7 |

## Example intros

| Request | Specialized | Baseline |
|---|---|---|
| abeg I need gbedu for owambe this saturday | Oya, get ready because this heavy owambe gbedu go scatter the dancefloor this Saturday! | Get your dancing shoes and crisp naira notes ready, because this lineup is packed with non-stop gbedu crafted to keep the energy high and the dance floor packed all through your owambe this Saturday. |
| I dey feel somehow today | I feel you my friend, sometimes body just dey weak and person go dey feel somehow without reason. Relax your mind, I don arrange soft moody vibes to hold you down. | When you dey feel somehow and you can't quite place the feeling, music that mirrors that unsettled energy can help you process it. This playlist moves through introspective rhythms and gentle releases to match your current headspace. |
| Detty December vibes, make we turn up | Detty December don land, and we dey ready to scatter the dancefloor! Here na premium high-energy jams to make you turn up properly. | Get ready to turn up with the ultimate Detty December soundtrack packed with unstoppable energy and pure groove. |
| oya make we jaiye this weekend | Oya, it is time to chop life and jaiye properly with this celebration weekend selection! | Ready to jaiye and chop life this weekend? Here is an upbeat selection of celebratory jams to keep your energy high and the party moving. |
| upbeat songs for a summer road trip | Get ready to roll down the windows and hit the highway with this bright, high-energy summer road trip mix! | Roll the windows down and feel the warm breeze with this high-energy mix tailored for your summer road trip. |
| sad songs for a rainy day | When the rain starts pouring, sometimes you just need to lean into the melancholy. Here are five gentle, sorrowful tracks perfect for watching the raindrops fall. | When the rain starts falling, let yourself lean into the quiet melancholy with this gentle, reflective playlist. |
| songs like Arctic Monkeys | If you are craving that brooding rock sound Arctic Monkeys do so well, I've got a fantastic set lined up for you. | Here's a moody, guitar-driven selection capturing the dark, atmospheric indie rock sound of Arctic Monkeys. |
