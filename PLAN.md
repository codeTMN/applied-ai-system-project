# Vibe DJ: Build Plan

Project 4 (Applied AI System). This extends **VibeMatch 1.0**, my Module 3 music recommender
(rule-based scoring over 62 made-up songs), into an AI system that understands plain-English
and Nigerian/Pidgin music requests, retrieves knowledge, and explains real-song playlists.

## Decisions

| Topic | Decision |
|---|---|
| LLM | Gemini (Google AI Studio key) for text and embeddings |
| UI | Streamlit (`app.py`); CLI kept for evaluation |
| Songs | Real songs, pulled once from Last.fm by a build script; energy/valence estimated by Gemini from real tags and marked `features_source=estimated` |
| Catalog size | About 200 songs. Afro section of about 60 (Afrobeats, Amapiano, Afro-fusion/Afropop, Alté, Highlife, Afro-house); every other genre at least 8 |
| Language | Understands Nigerian phrasing/Pidgin (gbedu, owambe, Detty December...) and answers in a matching tone |
| Ranking engine | Original `score_song` / `recommend_songs` stays as the scorer |
| Secrets | `.env` (gitignored); `.env.example` shows the names |

## Pipeline

```
request -> [1 parse: Gemini + few-shot -> UserProfile JSON]
        -> [2 input guardrail: ranges, unknown genre -> nearest + notice, off-topic -> refuse]
        -> [3 retrieve: embeddings over 4 sources]
               song vibe cards | genre & culture guides | activity guide | Naija slang glossary
        -> [4 score: original scorer ranks the catalog]
        -> [5 explain: Gemini writes the playlist, only from retrieved/ranked songs, cites song ids]
        -> [6 output guardrail: every song must exist in the catalog; else strip + retry]
        -> playlist + reasons + "listen" search links
```

Agent mode: the same steps exposed as Gemini function-calling tools
(`search_knowledge`, `score_catalog`, `validate_playlist`), max ~6 steps, every step logged to `logs/`.

## Course sections

| Course section | What it asks | Status |
|---|---|---|
| 0. Preparing your environment | New repo, push history, `assets/` + `diagrams/` folders | Done |
| 1. Functionality | At least one AI feature, fully integrated; runs reproducibly; logging/guardrails; clear setup | Tasks 1-6 |
| 2. Design and architecture | Mermaid diagram: components, data flow, where humans/tests check AI | Draft in `diagrams/architecture.mmd`; updated after each task, finalized in task 8 |
| 3. Documentation | README: base project named + 2-3 sentence summary, title & summary, architecture overview, setup steps, 2-3 sample interactions, design decisions, testing summary, brief reflection (graded reflection goes in `model_card.md`) | Task 8 |
| 4. Reliability and evaluation | At least one way to measure reliability (tests, confidence scores, logging, human eval in a parseable table) + a few-line testing summary ("x of y passed...") | Tasks 3, 7 (add a confidence score) |
| 5. Reflection and ethics | `model_card.md` with clear headers: limitations/biases, misuse + prevention, what surprised me in testing, AI collaboration (one suggestion accepted, one rejected/revised, and why) | Task 8 |
| 6. Presentation and portfolio | README **text evidence** (fenced code blocks or `.txt` logs): sample commands, inputs, outputs, guardrail/eval results; portfolio paragraph "what this project says about me as an AI engineer"; optional Loom link; 5-7 min presentation (you) | Task 8 |
| Submission checklist | Public repo, README.md, model_card.md, Mermaid diagram in `diagrams/`, images in `assets/`, multiple meaningful commits, pushed before the deadline | Task 8 |

## Tasks (one commit per task, pushed as we go)

- [x] **0. Setup:** new repo, origin repointed, `assets/`, `diagrams/`, `.env.example`, draft diagram
- [x] **1. Catalog builder:** `scripts/build_catalog.py` -> 369 real songs across 32 genres in `data/songs.csv` (old fictional catalog kept as `data/songs_v1_fictional.csv`)
  - Afro genres featured (60 songs); every other genre has 11-12 songs, incl. new funk, soul, disco, house, gospel, blues, punk, trap, k-pop
  - Known bias for the model card: real top tracks skew upbeat (95 energetic vs 23 sad, 7 angry, 5 focused)
  - Changed approach: Last.fm *tag* top-tracks were too noisy (`afrobeats` returned Beyoncé and K-pop; `highlife` returned Rick Astley), so songs come from human-picked **seed artists** (`data/catalog_seeds.json`) and their real top tracks instead
  - Gemini rejected songs that don't fit their genre (e.g. Tyla "Water" moved out of amapiano: "Afropop/R&B with amapiano log drums"); see `data/catalog_report.md`
  - [ ] Human review of Afro rows -> corrections go in `data/catalog_overrides.json`
  - Found: the API key's project was on the **free tier** (20 requests/day per model); the fallback model took over mid-build. Fixed by linking billing; full rebuild then ran on the main model
- [x] **2. Knowledge base:** 693 chunks from 5 sources, embedded with `gemini-embedding-2` (768 dims), cached in `data/index/`
  - `knowledge/naija_slang.md` (26 terms) and `knowledge/activities.md` (18 activities): hand-written, **human-reviewed**
  - `knowledge/genres.md` (32) and `knowledge/artists.md` (248): `scripts/build_knowledge.py` = Last.fm wiki/bio + stats from our catalog
  - `src/knowledge.py`: per-source retrieval so 369 song cards can't crowd out 26 slang terms
  - Found: `gemini-embedding-2` merges a list of plain strings into ONE vector; each text must be its own `Content`
  - Notes for task 3: every source always returns *something* (e.g. "bossa nova" -> jazz at 0.66, slang "vibe" for a study request), so the pipeline needs score thresholds; slang/activity hits above ~0.75 were the relevant ones. Song search alone matched "I dey feel somehow" to Igbo highlife, not sad songs, so songs must be ranked by the scorer using the slang hints, not by raw similarity
- [x] **3. Core pipeline:** `src/vibe_dj.py` (`python -m src.vibe_dj "request"`): input check -> retrieve -> parse (few-shot + knowledge) -> input guardrail -> rank (original scorer + AI bonuses) -> explain -> output guardrail (retry once, then scorer-reason fallback); every step timed in a trace + `logs/vibe_dj.log`
  - Order changed from the first draft: retrieval runs *before* parsing, so slang/activity knowledge shapes the profile
  - `recommend_songs` got an optional `bonuses` argument; without it scoring is exactly the original (tested)
  - Fixes found by running real requests: "no lyrics" was ignored (Otis Redding in a study list) -> instrumental requests now penalize vocal songs; "songs like Tems" drifted to rock/trap -> same-scene + Last.fm-similar bonuses; "2004 Remaster" stripped from titles
  - Baselines for the specialization/RAG comparisons: `--zero-shot`, `--no-rag`
  - 19 offline tests (`tests/test_guardrails.py`): clamping, aliases, unknown genre, bad mood/tags, empty/too-long input, no-vocals, artist bonuses, invented/missing/duplicate songs, other artists named, retry then fallback
  - ~12-18 s per request (two Gemini calls); refusals ~4 s
- [x] **4. Agent mode:** `src/agent.py` (`python -m src.vibe_dj --agent "..."`): Gemini function calling with `search_knowledge`, `score_songs`, `finish`, `refuse`; same guardrails as the pipeline; traces saved to `logs/traces/*.md|.json` and linked from `ai_interactions.md`
  - Iterations driven by traces: v1 ran out of steps on a Pidgin request (pipeline fallback answered) -> 3-search cap + "turns left" reminder; guardrail false alarm on "No Love (with SZA)" -> featured artists in titles allowed
  - Speed: `thinking_level="low"` (2.2 s vs 8.8 s per call in testing) -> pipeline ~16 s -> ~7 s, agent ~45 s -> ~11 s
  - 30 offline tests total (`tests/test_agent.py` drives the loop with a scripted fake Gemini)
- [x] **5. Streamlit UI:** `streamlit run app.py`: chat box, 6 one-click examples, playlist cards (why, scorer reasons, Spotify/YouTube/Last.fm links), guardrail notices, "How I got this playlist" panel (understood request, knowledge used with similarity scores, step timings), Agent mode toggle, RAG/few-shot switches for baselines, friendly setup message when the Gemini key is missing
  - Tested in the browser: pipeline (owambe example) and agent mode ("Sunday rice after church": 5 turns, re-scored once, 32.6 s)
- [x] **6. Setup reproducibility:** exact versions in `requirements.txt` (Python 3.12), `scripts/check_setup.py` (plain-language OK/FIX report + 3 tiny live Gemini calls), friendly messages instead of crashes for a missing/invalid key or rate limit
  - Fresh clone from GitHub into an empty folder: install OK, 31/31 tests pass; without a key the checker and CLI explain the fix; with a key the pipeline and agent work and the committed index is reused (0 chunks re-embedded), so graders need only a Gemini key, no Last.fm key
  - App examples rebalanced to mostly general English (road trip, study, rainy day, gym, date night, Arctic Monkeys, 70s/80s) + 2 Naija ones; checked each gives a sensible playlist
  - "songs like Arctic Monkeys" let a drill track in -> same-scene bonus 1.0 -> 1.75. Known limit: when an artist's Last.fm similar artists aren't in the catalog, matching falls back to mood
- [x] **7. Evaluation:** `eval.py` + `evaluation/` (summary in `evaluation/README.md`)
  - Match confidence added to every result (base score / best possible score; AI bonuses excluded; low < 0.6 tells the user)
  - 22 cases: full system 21/22 (worship energy 0.61 > 0.60: gospel catalog leans praise), agent 22/22, no-RAG 17/22 (Naija 2/6), zero-shot 21/22
  - Eval-driven fixes: explicit genres capped at 2 songs (19/22 -> 21/22); agent dropped the bossa nova notice; "Nigerian Pidgin" label broke the tone lookup
  - Specialization: tone rules 4.0 vs 1.0 Pidgin words per reply; few-shot examples made no measurable difference (38/38 both) -> honest finding for the model card
  - Consistency 0.87 average overlap; human review sheet `evaluation/human_review.md` for the user to fill in
- [ ] **8. Docs:** README (every section 3 item + section 6 text evidence, plain language, incl. how a grader gets their own Gemini key), final diagram, `model_card.md` (section 5 headers + baseline vs specialized + RAG before/after), portfolio paragraph, demo screenshots in `assets/`

## Models (checked with `models.list()` on 2026-11-15)

Set in `.env` (`GEMINI_MODEL`, `GEMINI_EMBED_MODEL`, `GEMINI_FALLBACK_MODEL`) so they are a one-line change.

| Role | Model | Why |
|---|---|---|
| Main | `gemini-3.8-flash` | Newest Flash. 3/3 calls OK in ~5s once billing was linked (on the free tier it returned 503 "high demand" and one call took 8 min with SDK retries) |
| Fallback | `gemini-3.6-flash` | ~2-3s and reliable. Used when the main model is overloaded (429/5xx/timeout) |
| Embeddings | `gemini-embedding-2` | Newest embedding model, 3072 dims |

Lesson for the build: every Gemini call needs a short timeout, limited retries, and the fallback model.
`gemini-2.5-flash` is still listed by `models.list()` but returns 404, so the list alone isn't proof a model works.
Aliases move: `gemini-3.5-flash` is actually served by 3.6, and `gemini-3.7-flash` by 3.8 (`response.model_version`), so we pin the real names.
Catalog features were re-estimated with `gemini-3.8-flash` after the switch. 3.8 sometimes put a tag word ("confident") in the mood field; the builder now maps stray words to the closest allowed mood instead of defaulting to "chill".

## Rubric map

| Rubric item | Where it's covered |
|---|---|
| Base project identified | README "Base project: VibeMatch 1.0" section |
| Substantial AI feature | Phases 2-4 (RAG + agent) |
| Architecture diagram | `diagrams/architecture.mmd` (Phase 7) |
| End-to-end demo | Streamlit app + README sample runs |
| Reliability / guardrails | Phase 3 guardrails + Phase 6 eval |
| Documentation | Phase 7 |
| Reflection | Phase 7 (`model_card.md`) |
| Stretch: multi-source RAG | 4 retrieval sources + before/after example |
| Stretch: agentic workflow | Phase 4 traces in `logs/` |
| Stretch: specialization | Few-shot Pidgin parsing + tone; baseline vs specialized in model card |
| Stretch: test harness | `eval.py` |
