"""
Guardrail tests for Vibe DJ. These run offline: no Gemini or Last.fm calls.
The DJ is built by hand with a tiny catalog so each rule can be checked on its own.
"""

from src.recommender import recommend_songs
from src.vibe_dj import Explanation, Pick, PickNote, RequestProfile, VibeDJ, MAX_REQUEST_CHARS


def song(id, title, artist, genre, mood="chill", energy=0.5, valence=0.5, instrumentalness=0.0):
    return {"id": id, "title": title, "artist": artist, "genre": genre, "mood": mood, "energy": energy,
            "valence": valence, "acousticness": 0.3, "instrumentalness": instrumentalness, "mood_tags": []}


SONGS = [
    song(1, "Essence", "Wizkid", "afrobeats", "relaxed", 0.55, 0.7),
    song(2, "Active", "Asake", "afrobeats", "energetic", 0.88, 0.8),
    song(3, "just friends", "potsu", "lofi", "chill", 0.3, 0.5, instrumentalness=0.9),
    song(4, "Me & U", "Tems", "alte", "chill", 0.5, 0.5),
    song(5, "So What", "Miles Davis", "jazz", "chill", 0.35, 0.5, instrumentalness=0.8),
]


def make_dj(closest="jazz") -> VibeDJ:
    dj = VibeDJ.__new__(VibeDJ)          # skip __init__: no index, no API
    dj.use_rag, dj.few_shot = True, True
    dj.songs = SONGS
    dj.by_id = {s["id"]: s for s in SONGS}
    dj.genres = sorted({s["genre"] for s in SONGS})
    dj.artists = sorted({s["artist"] for s in SONGS} | {"Burna Boy", "Future"})
    dj.similar = {"tems": ["Burna Boy", "Wizkid"]}
    dj.profile_artists = set()
    dj.closest_genre = lambda text: closest
    return dj


def profile(**overrides) -> RequestProfile:
    base = dict(is_music_request=True, refusal_reason="", language_style="english", summary="test",
                requested_genre="", favorite_genre="", favorite_mood="chill", target_energy=0.5,
                target_valence=0.5, acoustic="any", favorite_tags=[], target_speechiness=-1,
                target_instrumentalness=-1, preferred_decade=0, similar_artists=[],
                scoring_mode="balanced", used_knowledge=[])
    return RequestProfile(**{**base, **overrides})


def picks(*ids):
    return [Pick(SONGS[i - 1], 10.0, []) for i in ids]


def explanation(ids, text=""):
    return Explanation(intro=text, closing="", picks=[PickNote(song_id=i, why="nice") for i in ids])


# ---------------------------------------------------------------- input guardrail

def test_numbers_out_of_range_are_clamped():
    prefs, _ = make_dj().check_profile(profile(target_energy=1.7, target_valence=-0.2), {})
    assert prefs["target_energy"] == 1.0 and prefs["target_valence"] == 0.0


def test_genre_spelling_aliases_are_mapped():
    prefs, notices = make_dj().check_profile(profile(favorite_genre="Afro Beats"), {})
    assert prefs["favorite_genre"] == "afrobeats" and notices == []


def test_unknown_requested_genre_maps_to_closest_with_notice():
    prefs, notices = make_dj(closest="jazz").check_profile(
        profile(requested_genre="bossa nova", favorite_genre="samba"), {})
    assert prefs["favorite_genre"] == "jazz"
    assert "bossa nova" in notices[0]


def test_bad_mood_and_tags_are_replaced_with_allowed_values():
    prefs, _ = make_dj().check_profile(profile(favorite_mood="confident", favorite_tags=["party", "spicy"]), {})
    assert prefs["favorite_mood"] == "energetic"
    assert prefs["favorite_tags"] == ["party"]


def test_no_preference_fields_are_left_out():
    prefs, _ = make_dj().check_profile(profile(acoustic="any", target_speechiness=-1, preferred_decade=0), {})
    assert "likes_acoustic" not in prefs and "target_speechiness" not in prefs and "preferred_decade" not in prefs


def test_empty_and_too_long_requests_stop_before_any_api_call():
    dj = make_dj()
    dj.index = None                      # would crash if retrieval were attempted
    assert not dj.recommend("   ").ok
    long = dj.recommend("x" * (MAX_REQUEST_CHARS + 1))
    assert not long.ok and "under" in long.refusal


# ---------------------------------------------------------------- ranking constraints

def test_no_lyrics_request_pushes_vocal_songs_down():
    dj = make_dj()
    dj.use_rag = False
    bonus = dj.bonuses(profile(target_instrumentalness=0.85), {}, [])
    ranked = recommend_songs({"target_energy": 0.4}, SONGS, k=2, bonuses=bonus)
    assert {s["id"] for s, _, _ in ranked} == {3, 5}      # the two instrumental songs


def test_named_artist_and_similar_artists_get_bonuses():
    dj = make_dj()
    dj.use_rag = False
    bonus = dj.bonuses(profile(similar_artists=["Tems"]), {}, [])
    assert bonus[4][0][1].startswith("by Tems")
    assert "similar to Tems" in bonus[1][0][1]


def test_unknown_artist_gets_a_notice():
    notices = []
    make_dj().bonuses(profile(similar_artists=["Nobody Real"]), {}, notices)
    assert "Nobody Real" in notices[0]


def test_bonuses_add_points_and_reasons_to_the_original_scorer():
    plain = recommend_songs({"target_energy": 0.5}, SONGS, k=5)
    boosted = recommend_songs({"target_energy": 0.5}, SONGS, k=5, bonuses={3: [(5.0, "test bonus")]})
    assert boosted[0][0]["id"] == 3 and "test bonus (+5.00)" in boosted[0][2]
    assert [s["id"] for s, _, _ in recommend_songs({"target_energy": 0.5}, SONGS, k=5)] == [s["id"] for s, _, _ in plain]


# ---------------------------------------------------------------- output guardrail

def test_clean_explanation_passes():
    assert make_dj().check_explanation(explanation([1, 2]), picks(1, 2)) == []


def test_invented_or_missing_song_ids_are_caught():
    problems = make_dj().check_explanation(explanation([1, 99]), picks(1, 2))
    assert any("not in the playlist" in p for p in problems)
    assert any("missing" in p for p in problems)


def test_duplicate_song_is_caught():
    problems = make_dj().check_explanation(explanation([1, 1]), picks(1, 2))
    assert any("more than once" in p for p in problems)


def test_naming_an_artist_outside_the_playlist_is_caught():
    problems = make_dj().check_explanation(explanation([1, 2], "If you like this, try Burna Boy too!"), picks(1, 2))
    assert any("Burna Boy" in p for p in problems)


def test_common_word_artist_and_user_named_artist_are_not_false_alarms():
    dj = make_dj()
    dj.profile_artists = {"burna boy"}
    text = "The future is bright. Just like Burna Boy, these songs groove."
    assert dj.check_explanation(explanation([1, 2], text), picks(1, 2)) == []


def test_bad_write_up_is_retried_once_then_replaced_by_scorer_reasons(monkeypatch):
    calls = []

    def fake_generate_json(prompt, schema, system=None, temperature=0.0):
        calls.append(prompt)
        return explanation([1, 99], "Also try Burna Boy!")      # wrong every time

    monkeypatch.setattr("src.vibe_dj.generate_json", fake_generate_json)
    from src.vibe_dj import Tracer, VibeResult
    dj = make_dj()
    result = VibeResult(request="test", profile=profile(), picks=[Pick(SONGS[0], 9.0, ["mood match: relaxed (+2.00)"]),
                                                                   Pick(SONGS[1], 8.0, ["genre match: afrobeats (+1.50)"])])
    dj.explain(result, Tracer())
    assert len(calls) == 2 and "REJECTED" in calls[1]          # second try is told what was wrong
    assert result.explanation_source == "fallback"
    assert result.picks[0].why == "mood match: relaxed."
    assert "Burna Boy" not in result.intro


def test_good_second_attempt_is_used(monkeypatch):
    answers = [explanation([1, 99]), explanation([1, 2], "Great picks.")]
    monkeypatch.setattr("src.vibe_dj.generate_json", lambda *a, **k: answers.pop(0))
    from src.vibe_dj import Tracer, VibeResult
    result = VibeResult(request="test", profile=profile(), picks=picks(1, 2))
    make_dj().explain(result, Tracer())
    assert result.explanation_source == "gemini-retry" and result.intro == "Great picks."
