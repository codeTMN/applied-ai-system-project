# AI Interactions Log

This file has two parts:

1. **Project 4 (Vibe DJ):** the agent's saved reasoning traces (stretch feature: Agentic Workflow Enhancement).
2. **Module 3 (base project, VibeMatch 1.0):** my original log, kept unchanged below.

---

## Project 4: Vibe DJ agent traces

### What the agent does

Agent mode (`python -m src.vibe_dj --agent "..."`, or the Agent toggle in the app) lets Gemini 3.8 Flash
**plan and act with tools** instead of following the fixed pipeline. Code: [`src/agent.py`](src/agent.py).

| Tool | What it does |
|---|---|
| `search_knowledge(query, source)` | Looks up Naija slang, activity guides, genre guides, artist bios or song cards (at most 3 searches) |
| `score_songs(profile)` | Runs the input guardrail + the **original VibeMatch scorer** + AI bonuses, returns 8 candidates with reasons |
| `finish(intro, picks, closing)` | Submits 5 songs. **Rejected with a list of problems** if a song wasn't a candidate, a song repeats, an artist appears 3+ times, or the write-up names an artist outside the playlist |
| `refuse(reason)` | Declines non-music requests |

The decision-making chain: **look up what it doesn't know -> score -> check the candidates against the
request -> re-score with a corrected profile if they miss -> submit -> fix and resubmit if the
guardrail rejects it.** Safety nets: 8 model turns at most, a "turns left" reminder, and if the agent
still can't finish, the normal pipeline answers instead.

### Where the traces are

Every agent run saves its full trace, **not just terminal output**, as two committed files in
[`logs/traces/`](logs/traces/):

- `.md`: readable. Each step has Gemini's thinking summary, the one-line reason it gives before each tool call, the tool call, and the result.
- `.json`: the same events, machine-readable.

| Trace | Outcome | What it shows |
|---|---|---|
| [study, no lyrics](logs/traces/20261115-140213-something-chill-to-study-to-no-lyrics.md) | finished, 3 turns | Simple plan: look up the study guide, score, finish |
| [songs like Tems (v1)](logs/traces/20261115-140311-songs-like-tems.md) | finished, 7 turns, **1 rejection** | Write-up named an outside artist -> guardrail rejected it -> agent rewrote it |
| [I dey feel somehow (v1)](logs/traces/20261115-140430-my-guy-i-dey-feel-somehow-something-soft.md) | **ran out of steps -> pipeline fallback** | Agent kept searching. This trace is why I added the 3-search limit and the turn reminder |
| [debug my python code](logs/traces/20261115-140434-can-you-help-me-debug-my-python-code.md) | refused, 1 turn | Off-topic request declined |
| [I dey feel somehow (v2)](logs/traces/20261115-140536-my-guy-i-dey-feel-somehow-something-soft.md) | finished, 5 turns, **2 score calls, 1 rejection** | Re-scored with lower energy after judging candidates too loud; fixed a rejected write-up (excerpt below) |
| [songs like Tems (v2)](logs/traces/20261115-140625-songs-like-tems.md) | finished, 4 turns | Same request after the search limit: 7 turns -> 4 |
| [I dey feel somehow (v3)](logs/traces/20261115-140725-my-guy-i-dey-feel-somehow-something-soft.md) | finished in 10.6 s, 3 turns | After switching to low thinking: 45 s -> 10.6 s |
| [Sunday rice after church](logs/traces/20261115-141809-abeg-play-me-something-soft-for-my-sunda.md) | finished, 5 turns, **2 score calls** | Run from the web app: looked up "Sunday rice", re-scored to bring in more gospel |
| [songs like Tems (final)](logs/traces/20261115-151457-songs-like-tems.md) | finished | The run shown in the README's sample interactions |

The 22 agent-mode runs from the evaluation (22/22 passed) are saved separately in
[`evaluation/agent_traces/`](evaluation/agent_traces/).

### Excerpt: "my guy, I dey feel somehow. something soft for tonight, no loud gbedu" (v2)

Full trace: [`logs/traces/20261115-140536-...md`](logs/traces/20261115-140536-my-guy-i-dey-feel-somehow-something-soft.md)

**Step 1: plan and look things up.** Gemini's thinking: *"they're feeling a bit down or off. They're
looking for something mellow and peaceful tonight, definitely no high-energy party music."*
It says *"I am checking the meaning of the Nigerian slang terms"* and calls
`search_knowledge("feel somehow", slang)` -> **I dey feel somehow (0.78)** and `search_knowledge("gbedu", slang)` -> **gbedu (0.79)**.

**Step 2: score.** `score_songs` with mood `moody`, energy 0.4, valence 0.35, similar artists Omah Lay / Tems / Tay Iwar.
The candidates include *Last Last* (energy 0.78) and *Ndisize* (0.69): too loud for "soft".

**Step 3: decide the candidates miss, and re-score.** It says *"I am refining the score profile with
slightly lower energy and calm tags to ensure we get truly mellow, soft selections without
high-energy tracks"*, and calls `score_songs` again with energy 0.35.

**Step 4: submit -> rejected by the guardrail.**
`finish` returned `{"ok": false, "problems": ["mentions SZA, who is not in this playlist"]}`.

**Step 5: fix and resubmit.** It says *"I am updating the playlist to remove the mention of any
featured artist not listed as a primary pick artist."* -> `{"ok": true}`.

*What I learned from this trace:* SZA is in the song title *"No Love (with SZA)"*, so the guardrail
was too strict. I changed it to allow artists named in a picked song's title, and added a test
(`test_featured_artist_in_a_song_title_is_allowed`).

---

## Module 3 (base project) log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

### Agentic Workflow (SF8)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

I used Claude Code (in agent mode in VS Code) to do Challenge 1: add 5 or more new song details to the dataset and make the scoring use them. I also had it do the other optional challenges in the same run: scoring modes, a diversity penalty, and a table for the output.

**Prompts used:**

- "let's do phase 5 and optional" (with screenshots of the Phase 5 and Optional Extensions instructions)
- Earlier, for the dataset: "add more songs, so the dataset is enough for the experiment" and "also add like afrobeats and other stuff, i will let you know if you are on the right track"

**What did the agent generate or change?**

- `data/songs.csv`: added 5 new columns to all 62 songs: `popularity` (0 to 100), `release_decade`, `mood_tags` (like "euphoric;playful"), `speechiness` (how much rapping or talking), and `instrumentalness` (how much of the song has no vocals)
- `src/recommender.py`:
  - `load_songs` now reads the new columns.
  - `score_song` gives points for the new details, but only if the user asks for them.
  - Added the scoring modes and the diversity penalty.
- `src/main.py`:
  - Added an "Afrobeats Night Out" profile that uses all the new details.
  - Results now print as a table.
  - Added the `--mode`, `--diverse`, and `--profile` options.
- `README.md` and `model_card.md`: wrote up the new features and pasted in the new output.
- Commands it ran: `pytest` (2 passed), `python -m src.main` with different options, and a check that compared the new results with the old ones.

**What did you verify or fix manually?**

- The agent checked that all 8 older profiles still got the exact same songs and scores as before. Because the new details only count when you ask for them, nothing old changed.
- The new numbers (popularity, decade, mood tags, and so on) are AI guesses for made-up songs. I looked over the afrobeats and hip hop rows to make sure they matched how those genres feel to me.
- I read the "Afrobeats Night Out" results to check that they made sense: *Owambe Party* first, then reggaeton and other afrobeats songs.

---

### Design Pattern (SF10)

> Document how AI helped you choose or implement a design pattern.

**Which design pattern did you use?**

The **Strategy pattern**. Each scoring mode is its own "strategy," a set of points for each rule. The scorer can swap them in and out without changing its code.

**How did AI help you brainstorm or implement it?**

The course asked for at least two ranking strategies (like "Genre-First" or "Energy-Focused") and suggested the Strategy pattern. My scoring already worked by giving points per rule, so the AI suggested the simplest version of the pattern: keep one scoring function, and make each mode an object that holds its own set of points. That way, adding a new mode is just adding one new line, not writing a whole new scoring function. It also made my earlier experiments (like doubling energy) easier, because a weight change is just a new mode.

**How does the pattern appear in your final code?**

- `ScoringMode` in `src/recommender.py` is the strategy. It holds the points for energy, valence, mood, genre, acoustic, and the new details.
- `BALANCED`, `GENRE_FIRST`, `MOOD_FIRST`, and `ENERGY_FOCUSED` are the 4 strategies, and `MODES` maps each name to its strategy.
- `score_song(user_prefs, song, mode)` and `recommend_songs(..., mode=...)` take a strategy and use its points. They don't care which one it is.
- In `src/main.py`, `--mode genre-first` (for example) picks which strategy to use.
