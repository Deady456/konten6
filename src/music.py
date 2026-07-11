"""
Background music layer for FreeFaceless.

Supports:
- Local music files (assets/music/)
- Automatic mood selection based on content format
- Volume mixing with voiceover
"""
import json
import random
import subprocess
from pathlib import Path
from .config import CONFIG, ROOT


def _get_music_config() -> dict:
    return CONFIG.get("music", {})


def _get_local_music_dir() -> Path:
    cfg = _get_music_config()
    rel_dir = cfg.get("local_dir", "assets/music")
    return ROOT / rel_dir


def _get_music_music_dir() -> Path:
    """Alias for internal use."""
    return _get_local_music_dir()


def _detect_format(scenes: list[dict]) -> str:
    """Detect content format from scenes for mood mapping."""
    cfg = CONFIG.get("content_variation", {})
    formats = cfg.get("formats", ["list"])

    # Simple heuristic: check script patterns
    texts = " ".join(s.get("text", "").lower() for s in scenes)

    if any(w in texts for w in ["perbandingan", "beda", "vs", "sama"]):
        return "comparison"
    elif any(w in texts for w in ["mitos", "fakta", "ternyata", "sebenarnya"]):
        return "myth_busting"
    elif any(w in texts for w in ["kisah", "cerita", "sejarah", "dulu"]):
        return "story"
    else:
        return "list"


def _select_music_file(mood: str) -> Path | None:
    """Select a random music file matching the mood."""
    music_dir = _get_music_music_dir()
    if not music_dir.exists():
        return None

    # Look in mood-specific subdirectory first
    mood_dir = music_dir / mood
    if mood_dir.exists():
        candidates = []
        for ext in ["*.mp3", "*.wav", "*.m4a", "*.ogg"]:
            candidates.extend(mood_dir.glob(ext))
        if candidates:
            return random.choice(candidates)

    # Fallback: any audio file in root or subdirs
    candidates = []
    for ext in ["*.mp3", "*.wav", "*.m4a", "*.ogg"]:
        candidates.extend(music_dir.rglob(ext))

    return random.choice(candidates) if candidates else None


def mix_with_voice(voice_path: Path, output_path: Path, video_duration: float,
                   scenes: list[dict] = None) -> Path:
    """
    Mix background music with voiceover.

    Returns path to mixed audio file.
    """
    cfg = _get_music_config()

    if not cfg.get("enabled", False):
        # Just copy voice as-is
        output_path.write_bytes(voice_path.read_bytes())
        return output_path

    # Select music file
    mood = _detect_format(scenes or []) if scenes else "neutral"
    mood_map = cfg.get("mood_mapping", {})
    mood_key = mood_map.get(mood, "neutral")
    music_file = _select_music_file(mood_key)

    if music_file is None:
        print("    music: no music files found, using voice only")
        output_path.write_bytes(voice_path.read_bytes())
        return output_path

    print(f"    music: using {music_file.name} (mood: {mood_key})")

    volume = cfg.get("volume", 0.15)
    fade_in = cfg.get("fade_in", 2.0)
    fade_out = cfg.get("fade_out", 3.0)

    # ffmpeg: mix music (lowered) with voice
    fade_out_start = max(0, video_duration - fade_out)

    filter_complex = (
        f"[1:a]volume={volume},afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out}[music];"
        f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=3,atrim=0:{video_duration:.3f}[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-i", str(music_file),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"    music: mix failed: {p.stderr[-300:]}")
        output_path.write_bytes(voice_path.read_bytes())
        return output_path

    print(f"    music: mixed successfully")
    return output_path


def get_available_music_count() -> int:
    """Count available music files."""
    music_dir = _get_local_music_dir()
    if not music_dir.exists():
        return 0
    count = 0
    for ext in ["*.mp3", "*.wav", "*.m4a", "*.ogg"]:
        count += len(list(music_dir.glob(ext)))
    return count
