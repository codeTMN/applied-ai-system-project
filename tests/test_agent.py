"""
Agent-mode tests, offline: Gemini is replaced by a scripted fake so the tool rules, the step
budget and the pipeline fallback can be checked without API calls.
"""

from types import SimpleNamespace

import pytest
from google.genai import types

import src.agent as agent_module
from src.agent import MAX_SEARCHES, VibeAgent
from src.vibe_dj import VibeResult
from tests.test_guardrails import SONGS, make_dj


@pytest.fixture
def agent(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "TRACE_DIR", tmp_path)
    dj = make_dj()
    dj.index = SimpleNamespace(search=lambda q, k=4, sources=None: [],
                               search_by_source=lambda q, per: {"song": []})
    a = VibeAgent(dj=dj, max_steps=4)
    a.knowledge, a.candidates, a.song_hits = {}, {}, []
    a.final = a.refusal = None
    a.score_calls = a.rejections = a.searches = 0
    return a


def score(agent, **profile):
    return agent.tool_score_songs({"favorite_mood": "chill", "target_energy": 0.5, **profile})


def finish(agent, ids, text="Enjoy."):
    return agent.tool_finish(text, [{"song_id": i, "why": "fits"} for i in ids], "Bye.")


def test_finish_before_scoring_is_rejected(agent):
    assert finish(agent, [1, 2, 3, 4, 5]) == {"ok": False, "problems": ["call score_songs first"]}


def test_finish_with_unknown_song_is_rejected(agent):
    score(agent)
    result = finish(agent, [1, 2, 3, 4, 99])
    assert not result["ok"] and "never returned" in result["problems"][0]


def test_finish_needs_five_different_songs(agent):
    score(agent)
    assert not finish(agent, [1, 1, 2, 3, 4])["ok"]
    assert not finish(agent, [1, 2, 3])["ok"]


def test_finish_rejects_other_artists_in_the_write_up(agent):
    score(agent)
    result = finish(agent, [1, 2, 3, 4, 5], "Fans of Burna Boy will love this.")
    assert not result["ok"] and "Burna Boy" in result["problems"][0]


def test_valid_finish_is_accepted(agent):
    score(agent)
    assert finish(agent, [1, 2, 3, 4, 5]) == {"ok": True}
    assert len(agent.final[1]) == 5


def test_score_songs_applies_the_input_guardrail(agent):
    out = score(agent, target_energy=3.0, favorite_mood="confident")
    assert out["applied_profile"]["target_energy"] == 1.0
    assert out["applied_profile"]["favorite_mood"] == "energetic"


def test_search_limit(agent):
    for _ in range(MAX_SEARCHES):
        assert "results" in agent.tool_search_knowledge("gbedu", "slang")
    assert "limit" in agent.tool_search_knowledge("gbedu", "slang")["error"]


# ---------------------------------------------------------------- the loop with a fake Gemini

def turn(*calls, text="I am doing the next step."):
    parts = [types.Part(text=text)] + [types.Part(function_call=types.FunctionCall(name=n, args=a)) for n, a in calls]
    return SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=parts))]), "fake"


def test_agent_loop_scores_then_finishes_and_saves_a_trace(agent, monkeypatch):
    script = [turn(("score_songs", {"profile": {"favorite_mood": "chill", "target_energy": 0.4}})),
              turn(("finish", {"intro": "Here you go.", "closing": "Enjoy.",
                               "picks": [{"song_id": i, "why": "fits"} for i in [3, 5, 4, 1, 2]]}))]
    monkeypatch.setattr(agent, "call_gemini", lambda contents, config: script.pop(0))
    result = agent.run("something calm")
    assert result.ok and result.explanation_source == "agent"
    assert [p.song["id"] for p in result.picks] == [3, 5, 4, 1, 2]
    assert result.trace[0]["outcome"] == "finished"
    assert result.trace_file.endswith(".md")
    assert {"says", "tool_call", "tool_result"} <= {e.get("type") for e in result.trace}


def test_agent_that_never_finishes_falls_back_to_the_pipeline(agent, monkeypatch):
    monkeypatch.setattr(agent, "call_gemini", lambda contents, config: turn(("search_knowledge", {"query": "x", "source": "any"})))
    monkeypatch.setattr(agent.dj, "recommend", lambda request: VibeResult(request=request, intro="pipeline answer"))
    result = agent.run("something calm")
    assert result.intro == "pipeline answer"
    assert "standard pipeline" in result.notices[-1]
    assert "pipeline fallback" in result.trace[0]["outcome"]


def test_agent_refusal(agent, monkeypatch):
    monkeypatch.setattr(agent, "call_gemini", lambda contents, config: turn(("refuse", {"reason": "That's code, not music."})))
    result = agent.run("debug my python")
    assert not result.ok and "only help with playlists" in result.refusal
