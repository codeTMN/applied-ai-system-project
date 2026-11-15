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

## Phases

- [x] **0. Setup:** new repo, origin repointed, `assets/`, `diagrams/`, `.env.example`
- [ ] **1. Catalog pipeline:** `scripts/build_catalog.py` (Last.fm `tag.getTopTracks` + track tags -> Gemini estimates -> `data/songs.csv`); filter noise (e.g. Fela-era `afrobeat`); review Afro rows by hand
- [ ] **2. Knowledge base:** `knowledge/` docs (genre guides, activity guide, slang glossary ~25 terms, reviewed by me); embedding index cached to disk
- [ ] **3. Core pipeline:** parse (few-shot) -> guardrails -> retrieve -> score -> explain -> check
- [ ] **4. Agent mode:** function calling + trace logs linked from `ai_interactions.md`
- [ ] **5. Streamlit UI:** chat box, playlist cards, "why" reasons, retrieved sources, guardrail notices
- [ ] **6. Evaluation:** `eval.py`, ~20 cases (English + Pidgin + edge cases), PASS/FAIL summary; baseline (zero-shot) vs few-shot comparison
- [ ] **7. Docs:** README (base project, setup, sample I/O), Mermaid diagram in `diagrams/`, model card, reflection, demo screenshots in `assets/`

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
