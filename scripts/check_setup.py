"""
Check that Vibe DJ is ready to run, and say how to fix anything that isn't.

    python scripts/check_setup.py            # full check, makes 3 tiny Gemini calls (fractions of a cent)
    python scripts/check_setup.py --offline  # skip the Gemini calls
"""

import argparse
import csv
import importlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PACKAGES = {"google.genai": "google-genai", "numpy": "numpy", "pydantic": "pydantic", "dotenv": "python-dotenv",
            "requests": "requests", "streamlit": "streamlit", "pytest": "pytest"}

failures = 0


def report(ok: bool, message: str, fix: str = "") -> None:
    global failures
    print(f"  {'OK  ' if ok else 'FIX '} {message}")
    if not ok:
        failures += 1
        if fix:
            print(f"       -> {fix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that Vibe DJ is ready to run")
    parser.add_argument("--offline", action="store_true", help="skip the live Gemini checks")
    args = parser.parse_args()

    print("\n1. Python")
    version = sys.version_info
    report(version >= (3, 10), f"Python {version.major}.{version.minor}.{version.micro}",
           "Install Python 3.12 (tested) from python.org, then recreate the virtual environment.")

    print("\n2. Packages")
    for module, name in PACKAGES.items():
        try:
            importlib.import_module(module)
            report(True, f"{name} installed")
        except ImportError:
            report(False, f"{name} is missing", "Run: pip install -r requirements.txt")

    print("\n3. Data that ships with the repo")
    songs = ROOT / "data" / "songs.csv"
    if songs.exists():
        with songs.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        report(len(rows) > 0, f"song catalog: {len(rows)} songs, {len({r['genre'] for r in rows})} genres")
    else:
        report(False, "data/songs.csv is missing", "Re-clone the repo (it is committed).")
    for name in ["naija_slang.md", "activities.md", "genres.md", "artists.md"]:
        report((ROOT / "knowledge" / name).exists(), f"knowledge/{name}", "Re-clone the repo (it is committed).")
    meta = ROOT / "data" / "index" / "index.json"
    if meta.exists() and (ROOT / "data" / "index" / "vectors.npy").exists():
        info = json.loads(meta.read_text(encoding="utf-8"))
        report(True, f"search index: {len(info['digests'])} chunks embedded with {info['model']}")
    else:
        report(False, "search index is missing", "It rebuilds itself on first run (needs the Gemini key).")

    print("\n4. Gemini API key")
    from dotenv import load_dotenv
    env = ROOT / ".env"
    report(env.exists(), ".env file exists", "Run: cp .env.example .env   then paste your key into .env")
    load_dotenv(env)
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    report(bool(key), "GEMINI_API_KEY is set" + (f" ({len(key)} characters)" if key else ""),
           "Get a free key at https://aistudio.google.com/apikey and paste it after GEMINI_API_KEY= in .env")

    if not args.offline and key:
        print("\n5. Live Gemini check (3 tiny calls)")
        from src.gemini_client import embed, get_client, model_chain
        from src.vibe_dj import service_problem
        for model in model_chain():
            started = time.time()
            try:
                get_client().models.generate_content(model=model, contents="Reply with OK.")
                report(True, f"{model} answered in {time.time() - started:.1f}s")
            except Exception as exc:  # noqa: BLE001
                report(False, f"{model} failed", service_problem(exc))
        started = time.time()
        try:
            embed(["test"], "RETRIEVAL_QUERY")
            report(True, f"{os.environ.get('GEMINI_EMBED_MODEL', 'gemini-embedding-2')} answered in {time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            report(False, "embedding model failed", service_problem(exc))

    print()
    if failures:
        print(f"{failures} thing(s) to fix (see -> lines above), then run this again.")
        sys.exit(1)
    print("All good! Try:  python -m src.vibe_dj \"upbeat songs for a summer road trip\"   or   streamlit run app.py")


if __name__ == "__main__":
    main()
