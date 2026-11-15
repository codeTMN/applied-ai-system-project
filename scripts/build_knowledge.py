"""
Build the data-driven knowledge files for retrieval:

  knowledge/genres.md   one section per genre: curated description + Last.fm wiki summary
                        + facts computed from OUR catalog (typical energy, moods, artists)
  knowledge/artists.md  one section per catalog artist: Last.fm bio summary, tags, similar artists

The hand-written files (knowledge/naija_slang.md, knowledge/activities.md) are not touched.
Last.fm responses are cached in data/raw/lastfm_knowledge_cache.json.

    python scripts/build_knowledge.py
"""

import csv
import html
import json
import logging
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.build_catalog import LastFM, SEEDS_PATH, OUT_CSV, RAW  # noqa: E402

KNOWLEDGE = ROOT / "knowledge"
CACHE = RAW / "lastfm_knowledge_cache.json"
ATTRIBUTION = ("Wiki and bio text from Last.fm (user-contributed, CC BY-SA). "
               "Numbers and mood counts are computed from data/songs.csv.")

# Last.fm tag names to try for each genre, in order (first one with a real wiki wins)
TAG_NAMES = {
    "r&b": ["rnb", "r&b"], "hip hop": ["hip-hop", "hip hop"], "liquid dnb": ["liquid funk", "liquid drum and bass"],
    "afro-fusion": ["afrofusion", "afro-fusion"], "afro-house": ["afro house"], "lofi": ["lo-fi", "lofi"],
    "indie pop": ["indie pop"], "k-pop": ["k-pop"], "alte": ["alte"],
}

log = logging.getLogger("build_knowledge")


def clean_wiki(text: str, limit: int = 700) -> str:
    """Strip Last.fm's HTML and 'Read more' link, keep the first ~700 characters at a sentence end."""
    text = re.sub(r"<a [^>]*>Read more on Last\.fm</a>\.?", "", text or "")
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        cut = text[:limit]
        text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut + "..."
    return text


def genre_wiki(lastfm: LastFM, genre: str) -> str:
    for tag in TAG_NAMES.get(genre, [genre]):
        data = lastfm.call("tag.getinfo", tag=tag)
        summary = clean_wiki(data.get("tag", {}).get("wiki", {}).get("summary", ""))
        if len(summary) > 40:
            return summary
    return ""


def describe_range(values) -> str:
    q = statistics.quantiles(values, n=4) if len(values) >= 4 else [min(values), statistics.median(values), max(values)]
    return f"{q[0]:.2f}-{q[-1]:.2f} (median {statistics.median(values):.2f})"


def build_genres(lastfm: LastFM, songs: list, seeds: dict) -> str:
    by_genre = defaultdict(list)
    for song in songs:
        by_genre[song["genre"]].append(song)
    lines = ["# Genre guide", "", ATTRIBUTION, ""]
    for genre, cfg in seeds.items():
        rows = by_genre.get(genre, [])
        if not rows:
            continue
        moods = Counter(r["mood"] for r in rows).most_common(3)
        tags = Counter(t for r in rows for t in r["mood_tags"].split(";") if t).most_common(4)
        artists = list(dict.fromkeys(r["artist"] for r in rows))
        lines += [f"## {genre}", ""]
        if cfg.get("description"):
            lines.append(f"What it is: {cfg['description']}.")
        wiki = genre_wiki(lastfm, genre)
        if wiki:
            lines.append(f"Last.fm: {wiki}")
        lines += [
            f"In this catalog: {len(rows)} songs. Energy {describe_range([float(r['energy']) for r in rows])}, "
            f"valence {describe_range([float(r['valence']) for r in rows])}, "
            f"tempo {describe_range([float(r['tempo_bpm']) for r in rows]).replace('.00', '')} BPM.",
            f"Most common moods: {', '.join(f'{m} ({n})' for m, n in moods)}. "
            f"Common tags: {', '.join(t for t, _ in tags)}.",
            f"Artists: {', '.join(artists)}.", ""]
    return "\n".join(lines)


def build_artists(lastfm: LastFM, songs: list) -> str:
    by_artist = defaultdict(list)
    for song in songs:
        by_artist[song["artist"]].append(song)
    lines = ["# Artist guide", "", ATTRIBUTION, ""]
    for artist, rows in sorted(by_artist.items(), key=lambda kv: kv[0].lower()):
        data = lastfm.call("artist.getinfo", artist=artist).get("artist", {})
        bio = clean_wiki(data.get("bio", {}).get("summary", ""), limit=450)
        tags = [t["name"].lower() for t in data.get("tags", {}).get("tag", [])][:5]
        similar = [a["name"] for a in data.get("similar", {}).get("artist", [])][:5]
        genres = sorted({r["genre"] for r in rows})
        lines += [f"## {artist}", "",
                  f"Catalog genre: {', '.join(genres)}. Songs here: {', '.join(r['title'] for r in rows)}."]
        if bio:
            lines.append(f"Bio: {bio}")
        if tags:
            lines.append(f"Last.fm tags: {', '.join(tags)}.")
        if similar:
            lines.append(f"Similar artists: {', '.join(similar)}.")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))["genres"]
    with OUT_CSV.open(encoding="utf-8") as f:
        songs = list(csv.DictReader(f))
    lastfm = LastFM(refresh=False, cache_path=CACHE)
    try:
        KNOWLEDGE.mkdir(exist_ok=True)
        (KNOWLEDGE / "genres.md").write_text(build_genres(lastfm, songs, seeds), encoding="utf-8")
        (KNOWLEDGE / "artists.md").write_text(build_artists(lastfm, songs), encoding="utf-8")
    finally:
        lastfm.save()
    log.info("wrote knowledge/genres.md and knowledge/artists.md (%d live Last.fm calls)", lastfm.live_calls)


if __name__ == "__main__":
    main()
