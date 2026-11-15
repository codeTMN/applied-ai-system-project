"""
Retrieval over Vibe DJ's knowledge sources (the "R" in RAG).

Sources, each split into small chunks:
  slang     knowledge/naija_slang.md   one chunk per term          (hand-written, human-reviewed)
  activity  knowledge/activities.md    one chunk per activity      (hand-written, human-reviewed)
  genre     knowledge/genres.md        one chunk per genre         (Last.fm wiki + catalog stats)
  artist    knowledge/artists.md       one chunk per artist        (Last.fm bio, tags, similar artists)
  song      data/songs.csv             one "vibe card" per song    (real song + estimated features)

Chunks are embedded with Gemini and cached in data/index/, keyed by a hash of each chunk's
text, so only new or edited chunks are re-embedded.

    python -m src.knowledge "abeg I need gbedu for owambe"     # try a search
"""

import csv
import hashlib
import json
import logging
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from src.gemini_client import EMBED_DIMS, embed, _setting

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "knowledge"
SONGS_CSV = ROOT / "data" / "songs.csv"
INDEX_DIR = ROOT / "data" / "index"

log = logging.getLogger("knowledge")

# which markdown heading level starts a chunk in each file
MARKDOWN_SOURCES = {
    "slang": ("naija_slang.md", "### "),
    "activity": ("activities.md", "### "),
    "genre": ("genres.md", "## "),
    "artist": ("artists.md", "## "),
}


@dataclass
class Chunk:
    id: str          # e.g. "slang:gbedu", "song:42"
    source: str      # slang | activity | genre | artist | song
    title: str
    text: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Hit:
    chunk: Chunk
    score: float


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def markdown_chunks(source: str, filename: str, marker: str) -> List[Chunk]:
    path = KNOWLEDGE / filename
    if not path.exists():
        log.warning("missing knowledge file %s - run scripts/build_knowledge.py", filename)
        return []
    chunks, title, body = [], None, []

    def flush():
        if title and any(line.strip() for line in body):
            text = f"{title}\n" + "\n".join(line for line in body if line.strip())
            chunks.append(Chunk(f"{source}:{slug(title)}", source, title, text))

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(marker):
            flush()
            title, body = line[len(marker):].strip(), []
        elif line.startswith("#"):          # a higher-level heading ends the current chunk
            flush()
            title, body = None, []
        elif title:
            body.append(line)
    flush()
    return chunks


def song_card(song: Dict) -> str:
    """One short paragraph per song, written so a plain-English query can match it."""
    tags = song["mood_tags"].replace(";", ", ")
    crowd = song.get("lastfm_tags", "").replace(";", ", ")
    return (f"{song['title']} by {song['artist']}. Genre: {song['genre']}. Mood: {song['mood']}"
            f"{f' ({tags})' if tags else ''}. Energy {float(song['energy']):.2f}, "
            f"valence {float(song['valence']):.2f}, {int(float(song['tempo_bpm']))} BPM, "
            f"{song['release_decade']}s."
            f"{f' Listener tags: {crowd}.' if crowd else ''}")


def song_chunks() -> List[Chunk]:
    with SONGS_CSV.open(encoding="utf-8") as f:
        return [Chunk(f"song:{row['id']}", "song", f"{row['title']} - {row['artist']}", song_card(row))
                for row in csv.DictReader(f)]


def load_chunks() -> List[Chunk]:
    chunks = []
    for source, (filename, marker) in MARKDOWN_SOURCES.items():
        chunks += markdown_chunks(source, filename, marker)
    return chunks + song_chunks()


class KnowledgeIndex:
    """Embeddings for every chunk, cached on disk and refreshed incrementally."""

    def __init__(self, chunks: List[Chunk], vectors: np.ndarray):
        self.chunks = chunks
        self.vectors = vectors

    @classmethod
    def build(cls, chunks: Optional[List[Chunk]] = None) -> "KnowledgeIndex":
        chunks = chunks if chunks is not None else load_chunks()
        model = _setting("GEMINI_EMBED_MODEL", "gemini-embedding-2")
        cache_file, meta_file = INDEX_DIR / "vectors.npy", INDEX_DIR / "index.json"

        cached: Dict[str, np.ndarray] = {}
        if cache_file.exists() and meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("model") == model and meta.get("dims") == EMBED_DIMS:
                old = np.load(cache_file)
                cached = {digest: old[i] for i, digest in enumerate(meta["digests"])}

        missing = [c for c in chunks if c.digest not in cached]
        if missing:
            log.info("embedding %d new/changed chunks (%d cached)", len(missing), len(chunks) - len(missing))
            for chunk, vector in zip(missing, embed([c.text for c in missing], "RETRIEVAL_DOCUMENT")):
                cached[chunk.digest] = np.asarray(vector, dtype=np.float32)

        vectors = np.stack([cached[c.digest] for c in chunks]).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

        if missing or not cache_file.exists():
            INDEX_DIR.mkdir(parents=True, exist_ok=True)
            np.save(cache_file, vectors)
            meta_file.write_text(json.dumps({
                "model": model, "dims": EMBED_DIMS,
                "digests": [c.digest for c in chunks],
                "chunks": [asdict(c) for c in chunks],
            }, ensure_ascii=False, indent=0), encoding="utf-8")
        return cls(chunks, vectors)

    def search(self, query: str, k: int = 5, sources: Optional[List[str]] = None) -> List[Hit]:
        """Top-k chunks by cosine similarity, optionally only from some sources."""
        q = np.asarray(embed([query], "RETRIEVAL_QUERY")[0], dtype=np.float32)
        q /= np.linalg.norm(q)
        scores = self.vectors @ q
        order = np.argsort(-scores)
        hits = []
        for i in order:
            if sources and self.chunks[i].source not in sources:
                continue
            hits.append(Hit(self.chunks[i], float(scores[i])))
            if len(hits) >= k:
                break
        return hits

    def search_by_source(self, query: str, per_source: Dict[str, int]) -> Dict[str, List[Hit]]:
        """Multi-source retrieval: e.g. {"slang": 3, "activity": 2, "genre": 2, "song": 15}.
        One query embedding, then the best hits from each source separately, so a big source
        (songs) can't crowd out a small one (slang)."""
        q = np.asarray(embed([query], "RETRIEVAL_QUERY")[0], dtype=np.float32)
        q /= np.linalg.norm(q)
        scores = self.vectors @ q
        results: Dict[str, List[Hit]] = {source: [] for source in per_source}
        for i in np.argsort(-scores):
            source = self.chunks[i].source
            if source in results and len(results[source]) < per_source[source]:
                results[source].append(Hit(self.chunks[i], float(scores[i])))
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    query = " ".join(sys.argv[1:]) or "something chill to study to"
    index = KnowledgeIndex.build()
    print(f"\nQuery: {query}   ({len(index.chunks)} chunks indexed)\n")
    for source, hits in index.search_by_source(query, {"slang": 2, "activity": 2, "genre": 2, "artist": 2, "song": 5}).items():
        for hit in hits:
            print(f"  [{source:8s}] {hit.score:.3f}  {hit.chunk.title}")
