"""
Build data/songs.csv from REAL songs.

Pipeline (run once, results are committed so the app works offline):
  1. data/catalog_seeds.json lists seed artists per genre (human-curated).
  2. Last.fm: each artist's real top tracks (with listener counts) + each track's crowd tags.
  3. Gemini: checks each song fits its genre and estimates the audio features the scorer
     needs (energy, valence, mood, ...). Spotify no longer offers these to new apps, so
     every row is marked features_source=gemini-estimate.
  4. data/catalog_overrides.json: human corrections (exclude songs / fix fields).
  5. Writes data/songs.csv and data/catalog_report.md (what was kept, what was dropped, why).

All API responses are cached in data/raw/, so re-running is fast, free and gives the
same result. Use --refresh-lastfm / --refresh-gemini to fetch fresh data.

    python scripts/build_catalog.py
    python scripts/build_catalog.py --genre amapiano --refresh-gemini
"""

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.gemini_client import generate_json, model_chain  # noqa: E402

DATA = ROOT / "data"
RAW = DATA / "raw"
SEEDS_PATH = DATA / "catalog_seeds.json"
OVERRIDES_PATH = DATA / "catalog_overrides.json"
LASTFM_CACHE = RAW / "lastfm_cache.json"
GEMINI_CACHE = RAW / "gemini_estimates.json"
OUT_CSV = DATA / "songs.csv"
REPORT = DATA / "catalog_report.md"
LOG_PATH = ROOT / "logs" / "build_catalog.log"

LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_DELAY = 0.25          # seconds between live calls (Last.fm asks for gentle use)
TOP_TRACKS_PER_ARTIST = 15
PROMPT_VERSION = "v1"        # bump to invalidate cached Gemini answers after a prompt change

MOODS = ["happy", "sad", "chill", "relaxed", "energetic", "intense", "moody", "focused", "romantic", "angry"]
MOOD_TAGS = ["euphoric", "uplifting", "playful", "confident", "party", "groovy", "smooth", "romantic",
             "cozy", "peaceful", "dreamy", "nostalgic", "hopeful", "focused", "melancholic",
             "heartbroken", "dark", "aggressive", "rebellious"]

# Titles that are usually alternate versions, not the song itself
JUNK_TITLE = re.compile(
    r"\b(remix|remixed|live|sped ?up|slowed|reverb|instrumental|acapella|a cappella|karaoke|"
    r"version|demo|cover|colors show|extended|radio edit|mixed)\b", re.IGNORECASE)

CSV_COLUMNS = ["id", "title", "artist", "genre", "mood", "energy", "tempo_bpm", "valence", "danceability",
               "acousticness", "popularity", "release_decade", "mood_tags", "speechiness",
               "instrumentalness", "lastfm_listeners", "lastfm_tags", "lastfm_url", "features_source"]

log = logging.getLogger("build_catalog")


# ---------------------------------------------------------------- caching helpers

def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")


# ---------------------------------------------------------------- Last.fm

class LastFM:
    def __init__(self, refresh: bool, cache_path: Path = LASTFM_CACHE):
        self.cache_path = cache_path
        self.cache = {} if refresh else load_json(cache_path, {})
        self.key = (os.environ.get("LASTFM_API_KEY") or "").strip()
        self.live_calls = 0

    def call(self, method: str, **params) -> dict:
        cache_key = method + "|" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        if cache_key in self.cache:
            return self.cache[cache_key]
        if not self.key:
            raise SystemExit("LASTFM_API_KEY is not set in .env (needed because this request isn't cached).")
        time.sleep(LASTFM_DELAY)
        try:
            response = requests.get(
                LASTFM_URL, timeout=20, headers={"User-Agent": "vibe-dj-catalog-builder/1.0"},
                params={"method": method, "api_key": self.key, "format": "json", "autocorrect": 1, **params})
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            # never log the URL: it contains the API key
            log.warning("lastfm %s failed: %s", method, type(exc).__name__)
            return {"error": -1, "message": type(exc).__name__}
        self.live_calls += 1
        if "error" in data:
            log.warning("lastfm %s %s -> error %s: %s", method, params, data.get("error"), data.get("message"))
        self.cache[cache_key] = data
        return data

    def save(self) -> None:
        save_json(self.cache_path, self.cache)

    def top_tracks(self, artist: str) -> List[dict]:
        data = self.call("artist.gettoptracks", artist=artist, limit=TOP_TRACKS_PER_ARTIST)
        return data.get("toptracks", {}).get("track", []) if "error" not in data else []

    def track_tags(self, artist: str, title: str) -> List[str]:
        data = self.call("track.gettoptags", artist=artist, track=title)
        tags = data.get("toptags", {}).get("tag", []) if "error" not in data else []
        return [t["name"].lower() for t in tags if int(t.get("count", 0)) >= 5][:8]


def base_title(title: str) -> str:
    """'Calm Down (with Selena Gomez)' -> 'calm down', used to spot duplicates."""
    title = re.sub(r"[\(\[].*?[\)\]]", "", title)
    title = title.split(" - ")[0]
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def candidates_for_genre(lastfm: LastFM, genre: str, cfg: dict, seen_titles: set) -> List[dict]:
    """Each seed artist's top real tracks, minus alternate versions and duplicates."""
    per_artist = cfg.get("max_per_artist", 2) + 1      # one spare in case Gemini rejects a song
    candidates = []
    for seed in cfg["artists"]:
        tracks = lastfm.top_tracks(seed)
        if not tracks:
            log.warning("[%s] no Last.fm tracks for seed artist %r - skipped", genre, seed)
            continue
        kept = 0
        for track in tracks:
            title, artist = track["name"].strip(), track["artist"]["name"].strip()
            key = (artist.lower(), base_title(title))
            if JUNK_TITLE.search(title) or not base_title(title) or key in seen_titles:
                continue
            seen_titles.add(key)
            candidates.append({
                "title": title, "artist": artist, "seed": seed, "artist_rank": kept,
                "listeners": int(track.get("listeners", 0)), "url": track.get("url", ""),
                "tags": lastfm.track_tags(artist, title),
            })
            kept += 1
            if kept >= per_artist:
                break
    return candidates


# ---------------------------------------------------------------- Gemini estimates

class SongEstimate(BaseModel):
    idx: int
    fits_genre: bool
    note: str
    mood: str
    mood_tags: List[str]
    energy: float
    valence: float
    danceability: float
    acousticness: float
    speechiness: float
    instrumentalness: float
    tempo_bpm: int
    release_decade: int


class GenreEstimates(BaseModel):
    songs: List[SongEstimate]


SYSTEM = """You are a careful music analyst helping build a song catalog for a recommender.
For each real song you are given, you (1) judge whether it genuinely belongs to the stated genre,
and (2) estimate Spotify-style audio features from your knowledge of the song and its Last.fm tags.
Be honest: if you do not know a song, estimate from the artist's typical sound and the tags and say
"estimated from artist style" in the note."""

PROMPT = """Genre: {genre}
Genre description: {description}

For each song return:
- idx: the number shown
- fits_genre: true only if a listener of "{genre}" would agree this song belongs (artists cross genres; judge the SONG)
- note: max 12 words; if fits_genre is false say what genre it is instead
- mood: exactly one of {moods}
- mood_tags: 1-2 of {mood_tags}
- energy, valence, danceability, acousticness, speechiness, instrumentalness: 0.0-1.0
  (valence = musical happiness; speechiness = rap/spoken words; instrumentalness = share with no vocals)
- tempo_bpm: integer
- release_decade: e.g. 1970, 2010, 2020

Songs:
{songs}
"""


def estimate_genre(genre: str, cfg: dict, candidates: List[dict], cache: dict, refresh: bool) -> Dict[int, SongEstimate]:
    songs_text = "\n".join(
        f"{i}. {c['artist']} - {c['title']} | Last.fm tags: {', '.join(c['tags']) or 'none'}"
        for i, c in enumerate(candidates))
    prompt = PROMPT.format(genre=genre, description=cfg.get("description", genre), moods=MOODS,
                           mood_tags=MOOD_TAGS, songs=songs_text)
    # the model name is part of the key, so switching models re-estimates automatically
    cache_key = genre + "|" + model_chain()[0] + "|" + hashlib.sha256((PROMPT_VERSION + SYSTEM + prompt).encode()).hexdigest()[:16]

    if not refresh and cache_key in cache:
        result = GenreEstimates.model_validate(cache[cache_key])
    else:
        log.info("[%s] asking Gemini about %d songs", genre, len(candidates))
        result = generate_json(prompt, GenreEstimates, system=SYSTEM)
        cache[cache_key] = result.model_dump()
    return {est.idx: est for est in result.songs if 0 <= est.idx < len(candidates)}


# Gemini sometimes puts a mood TAG in the mood field; map it to the closest allowed mood
MOOD_SYNONYMS = {
    "confident": "energetic", "party": "energetic", "euphoric": "happy", "uplifting": "happy",
    "playful": "happy", "groovy": "happy", "hopeful": "happy", "smooth": "chill", "dreamy": "chill",
    "cozy": "relaxed", "peaceful": "relaxed", "calm": "relaxed", "melancholic": "sad",
    "heartbroken": "sad", "nostalgic": "moody", "dark": "moody", "aggressive": "angry",
    "rebellious": "intense",
}


def mood_from_numbers(energy: float, valence: float) -> str:
    """Last resort when the mood word is unknown: pick a mood from energy and valence."""
    if energy >= 0.7:
        return "energetic" if valence >= 0.5 else "intense"
    if energy <= 0.45:
        return "relaxed" if valence >= 0.5 else "sad"
    return "happy" if valence >= 0.6 else "moody" if valence < 0.4 else "chill"


def clamp(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 2)


def clean_estimate(est: SongEstimate) -> dict:
    """Keep Gemini's answer inside the values the scorer understands."""
    mood = est.mood.strip().lower()
    if mood not in MOODS:
        fixed = MOOD_SYNONYMS.get(mood) or mood_from_numbers(est.energy, est.valence)
        log.warning("Gemini gave mood %r (not allowed) -> %r", est.mood, fixed)
        mood = fixed
    tags = [t.strip().lower() for t in est.mood_tags if t.strip().lower() in MOOD_TAGS][:2]
    decade = int(est.release_decade) // 10 * 10
    return {
        "mood": mood, "mood_tags": ";".join(tags),
        "energy": clamp(est.energy), "valence": clamp(est.valence), "danceability": clamp(est.danceability),
        "acousticness": clamp(est.acousticness), "speechiness": clamp(est.speechiness),
        "instrumentalness": clamp(est.instrumentalness),
        "tempo_bpm": int(min(220, max(40, est.tempo_bpm))),
        "release_decade": decade if 1940 <= decade <= 2020 else 2020,
    }


# ---------------------------------------------------------------- selection

def pick_songs(candidates: List[dict], estimates: Dict[int, SongEstimate], cfg: dict, dropped: List[dict]) -> List[dict]:
    """Round-robin across artists (best track of each artist first) until the target is reached."""
    usable = []
    for i, cand in enumerate(candidates):
        est = estimates.get(i)
        if est is None:
            dropped.append({**cand, "reason": "Gemini returned no estimate"})
        elif not est.fits_genre:
            dropped.append({**cand, "reason": f"doesn't fit genre: {est.note}"})
        else:
            usable.append({**cand, **clean_estimate(est), "note": est.note})

    target, cap = cfg["target"], cfg.get("max_per_artist", 2)
    picked, per_artist = [], {}
    for round_no in range(cap):
        for song in sorted(usable, key=lambda s: s["artist_rank"]):
            if len(picked) >= target:
                break
            if song in picked or per_artist.get(song["seed"], 0) != round_no:
                continue
            picked.append(song)
            per_artist[song["seed"]] = round_no + 1
    for song in usable:
        if song not in picked:
            dropped.append({**song, "reason": "spare (genre target already reached)"})
    return picked


def apply_overrides(songs: List[dict]) -> List[dict]:
    overrides = load_json(OVERRIDES_PATH, {})

    def matches(song, rule):
        return song["artist"].lower() == rule["artist"].lower() and song["title"].lower() == rule["title"].lower()

    kept = [s for s in songs if not any(matches(s, rule) for rule in overrides.get("exclude", []))]
    for rule in overrides.get("fix", []):
        for song in kept:
            if matches(song, rule):
                song.update(rule.get("set", {}))
                song["features_source"] = "gemini-estimate+human-fix"
    log.info("overrides: %d excluded, %d fix rules", len(songs) - len(kept), len(overrides.get("fix", [])))
    return kept


def popularity_scores(songs: List[dict]) -> None:
    """Real Last.fm listener counts -> 0-100 on a log scale across this catalog."""
    logs = [math.log10(max(1, s["listeners"])) for s in songs]
    low, high = min(logs), max(logs)
    for song, value in zip(songs, logs):
        song["popularity"] = round(100 * (value - low) / (high - low)) if high > low else 50


# ---------------------------------------------------------------- output

def write_csv(songs: List[dict]) -> None:
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for i, song in enumerate(songs, start=1):
            writer.writerow({**song, "id": i, "lastfm_listeners": song["listeners"],
                             "lastfm_tags": ";".join(song["tags"][:5]), "lastfm_url": song["url"]})


def write_report(songs: List[dict], dropped: List[dict], seeds: dict) -> None:
    lines = ["# Catalog build report", "",
             f"{len(songs)} songs kept, {len(dropped)} candidates dropped. Generated by `scripts/build_catalog.py`.", "",
             "**Human review:** check the featured (Afro) genres. To remove a song or fix a value, add it to",
             "`data/catalog_overrides.json` and re-run the script (cached, so it's instant and free).", ""]
    for genre, cfg in seeds.items():
        rows = [s for s in songs if s["genre"] == genre]
        star = " (featured)" if cfg.get("featured") else ""
        lines += [f"## {genre}{star} - {len(rows)}/{cfg['target']}", "",
                  "| Song | Artist | Mood | Energy | Valence | Tags | Gemini note |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {s['title']} | {s['artist']} | {s['mood']} | {s['energy']} | {s['valence']} | "
                  f"{s['mood_tags']} | {s['note']} |" for s in rows]
        gone = [d for d in dropped if d.get("genre") == genre and not d["reason"].startswith("spare")]
        if gone:
            lines += ["", "Dropped:", *[f"- {d['artist']} - {d['title']}: {d['reason']}" for d in gone]]
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the real-song catalog")
    parser.add_argument("--refresh-lastfm", action="store_true", help="ignore cached Last.fm responses")
    parser.add_argument("--refresh-gemini", action="store_true", help="ignore cached Gemini estimates")
    parser.add_argument("--genre", help="refresh only this genre's Gemini estimates (others stay cached)")
    args = parser.parse_args()

    LOG_PATH.parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()])
    logging.getLogger("httpx").setLevel(logging.WARNING)

    seeds = load_json(SEEDS_PATH, {})["genres"]
    lastfm = LastFM(refresh=args.refresh_lastfm)
    # a full refresh starts from an empty cache so stale answers don't pile up in git
    gemini_cache = {} if args.refresh_gemini else load_json(GEMINI_CACHE, {})
    seen_titles, songs, dropped = set(), [], []

    try:
        for genre, cfg in seeds.items():
            candidates = candidates_for_genre(lastfm, genre, cfg, seen_titles)
            refresh = args.refresh_gemini or args.genre == genre
            estimates = estimate_genre(genre, cfg, candidates, gemini_cache, refresh) if candidates else {}
            genre_dropped: List[dict] = []
            picked = pick_songs(candidates, estimates, cfg, genre_dropped)
            for song in picked:
                song.update(genre=genre, features_source="gemini-estimate")
            dropped += [{**d, "genre": genre} for d in genre_dropped]
            songs += picked
            log.info("[%s] %d candidates -> kept %d/%d", genre, len(candidates), len(picked), cfg["target"])
    finally:
        # save progress even if a call fails halfway, so the next run resumes from cache
        lastfm.save()
        save_json(GEMINI_CACHE, gemini_cache)

    songs = apply_overrides(songs)
    popularity_scores(songs)
    write_csv(songs)
    write_report(songs, dropped, seeds)
    log.info("wrote %d songs to %s (%d live Last.fm calls)", len(songs), OUT_CSV.relative_to(ROOT), lastfm.live_calls)


if __name__ == "__main__":
    main()
