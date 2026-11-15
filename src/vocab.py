"""
Shared vocabulary: the only moods and mood tags the catalog and the scorer understand.
Used by scripts/build_catalog.py (cleaning Gemini's estimates) and src/vibe_dj.py
(cleaning Gemini's reading of a user request).
"""

MOODS = ["happy", "sad", "chill", "relaxed", "energetic", "intense", "moody", "focused", "romantic", "angry"]
MOOD_TAGS = ["euphoric", "uplifting", "playful", "confident", "party", "groovy", "smooth", "romantic",
             "cozy", "peaceful", "dreamy", "nostalgic", "hopeful", "focused", "melancholic",
             "heartbroken", "dark", "aggressive", "rebellious"]


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
