"""
Vibe DJ - Streamlit app.

    streamlit run app.py

Type a vibe in plain English or Nigerian Pidgin and get a 5-song playlist of real songs, with the
reason for each pick, what the AI looked up, and every step it took.
"""

import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

import streamlit as st

ROOT = Path(__file__).resolve().parent
(ROOT / "logs").mkdir(exist_ok=True)

st.set_page_config(page_title="Vibe DJ", page_icon="🎧", layout="centered")

EXAMPLES = [
    "abeg I need gbedu for owambe this saturday",
    "something chill to study to, no lyrics",
    "songs like Tems",
    "I dey feel somehow today",
    "hype k-pop for my workout",
    "bossa nova for a dinner party",
]

SOURCE_LABELS = {"slang": "Naija slang", "activity": "Activity guide", "genre": "Genre guide",
                 "artist": "Artist bio", "song": "Song card"}


# ---------------------------------------------------------------- setup

@st.cache_resource(show_spinner="Loading the catalog and knowledge index...")
def load_dj(use_rag: bool, few_shot: bool):
    from src.vibe_dj import VibeDJ
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(ROOT / "logs" / "vibe_dj.log", encoding="utf-8")],
                        force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return VibeDJ(use_rag=use_rag, few_shot=few_shot)


def api_key_ok() -> bool:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    return bool((os.environ.get("GEMINI_API_KEY") or "").strip())


def listen_links(song: dict) -> str:
    query = quote_plus(f"{song['title']} {song['artist']}")
    links = [f"[Spotify](https://open.spotify.com/search/{query})",
             f"[YouTube](https://www.youtube.com/results?search_query={query})"]
    if song.get("lastfm_url"):
        links.append(f"[Last.fm]({song['lastfm_url']})")
    return " · ".join(links)


# ---------------------------------------------------------------- rendering

def show_result(result) -> None:
    if not result.ok:
        st.info(f"🎧 {result.refusal}")
        show_details(result)
        return

    st.markdown(f"🎧 {result.intro}")
    for notice in result.notices:
        st.warning(notice, icon="⚠️")

    for n, pick in enumerate(result.picks, start=1):
        song = pick.song
        with st.container(border=True):
            left, right = st.columns([5, 1])
            left.markdown(f"**{n}. {song['title']}**  \n{song['artist']}")
            right.metric("score", f"{pick.score:.1f}", label_visibility="collapsed")
            st.caption(f"{song['genre']} · {song['mood']} · energy {float(song['energy']):.2f} · "
                       f"{int(float(song['tempo_bpm']))} BPM · {song['release_decade']}s")
            st.markdown(pick.why)
            st.caption(f"Listen: {listen_links(song)}")
            with st.expander("Scorer's reasons"):
                for reason in pick.reasons:
                    st.markdown(f"- {reason}")

    if result.closing:
        st.markdown(f"_{result.closing}_")
    show_details(result)


def show_details(result) -> None:
    with st.expander("🔍 How I got this playlist"):
        source = {"gemini": "Gemini (passed the output guardrail first try)",
                  "gemini-retry": "Gemini (passed the output guardrail on the retry)",
                  "fallback": "Scorer reasons (Gemini's write-up failed the guardrail twice)",
                  "agent": "Agent mode (finish() passed the guardrail)"}.get(result.explanation_source, "-")
        if result.ok:
            st.markdown(f"**Write-up:** {source}")

        profile = result.profile
        if profile:
            st.markdown(f"**What I understood:** {profile.summary}")
            st.markdown(f"**Knowledge I used:** {', '.join(profile.used_knowledge) or 'none'}")
            st.json({k: v for k, v in profile.model_dump().items()
                     if k not in ("summary", "used_knowledge", "refusal_reason", "is_music_request")}, expanded=False)

        knowledge = {s: hits for s, hits in result.knowledge.items() if hits and s != "song"}
        if knowledge:
            st.markdown("**What I looked up** (similarity 0-1):")
            for src, hits in knowledge.items():
                st.markdown(f"- *{SOURCE_LABELS.get(src, src)}:* "
                            + ", ".join(f"{h.chunk.title} ({h.score:.2f})" for h in hits))

        st.markdown("**Steps:**")
        rows = []
        for step in result.trace:
            name = step.get("step") or step.get("type", "")
            detail = {k: v for k, v in step.items() if k not in ("step", "ms", "type")}
            label = step.get("tool") or step.get("text", "") or ""
            rows.append({"step": name if isinstance(name, str) else f"turn {name} · {step.get('type', '')}",
                         "ms": step.get("ms", ""), "detail": str(label or detail)[:160]})
        st.dataframe(rows, hide_index=True, use_container_width=True)
        if result.trace_file:
            st.markdown(f"**Full agent trace saved to** `{result.trace_file}`")


# ---------------------------------------------------------------- page

st.title("🎧 Vibe DJ")
st.caption("Tell me the vibe in plain English or Pidgin. I'll build a 5-song playlist from 369 real songs "
           "across 32 genres, with Afrobeats, Amapiano, Alté and Highlife front and center.")

with st.sidebar:
    st.header("Settings")
    agent_mode = st.toggle("Agent mode", value=False,
                           help="Gemini plans and calls tools (look up, score, check, re-score). "
                                "Slower, and saves a full reasoning trace to logs/traces/.")
    with st.expander("Experiment switches"):
        use_rag = st.checkbox("Use retrieval (RAG)", value=True,
                              help="Turn off to see the baseline without slang/activity/genre knowledge.")
        few_shot = st.checkbox("Use few-shot examples", value=True,
                               help="Turn off to see the baseline without the worked examples.")
    st.divider()
    st.markdown("**How it works**\n1. Look up slang, activities, genres, artists\n2. Gemini reads your request\n"
                "3. Guardrails check it\n4. The original VibeMatch scorer ranks songs\n5. Gemini explains the picks\n"
                "6. Guardrails check the write-up")
    if st.button("Clear chat"):
        st.session_state.history = []

if not api_key_ok():
    st.error("**No Gemini API key found.** Vibe DJ needs one to understand requests.\n\n"
             "1. Get a free key at https://aistudio.google.com/apikey\n"
             "2. In the project folder run `cp .env.example .env`\n"
             "3. Paste the key after `GEMINI_API_KEY=` in `.env`, save, and refresh this page.")
    st.stop()

st.session_state.setdefault("history", [])

st.markdown("**Try one:**")
cols = st.columns(3)
clicked = None
for i, example in enumerate(EXAMPLES):
    if cols[i % 3].button(example, key=f"ex{i}", use_container_width=True):
        clicked = example

typed = st.chat_input("e.g. abeg play me something soft for my Sunday rice")
request = typed or clicked

for past in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(past["request"] + (" · *agent mode*" if past["agent"] else ""))
    with st.chat_message("assistant", avatar="🎧"):
        show_result(past["result"])

if request:
    with st.chat_message("user"):
        st.markdown(request + (" · *agent mode*" if agent_mode else ""))
    with st.chat_message("assistant", avatar="🎧"):
        with st.spinner("Agent is planning, looking things up and scoring..." if agent_mode
                        else "Reading your vibe and digging through the crates..."):
            try:
                dj = load_dj(use_rag, few_shot)
                if agent_mode:
                    from src.agent import VibeAgent
                    result = VibeAgent(dj).run(request)
                else:
                    result = dj.recommend(request)
            except Exception as exc:  # noqa: BLE001 - show a friendly message, details go to the log
                logging.getLogger("app").exception("request failed")
                st.error(f"Something went wrong: {exc}. Details are in logs/vibe_dj.log.")
                st.stop()
        show_result(result)
    st.session_state.history.append({"request": request, "agent": agent_mode, "result": result})
