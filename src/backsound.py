import subprocess, json, requests, random
from pathlib import Path

SOURCES = [
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
]

def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])

def download_random(out_path: Path) -> Path:
    url = random.choice(SOURCES)
    print(f"    downloading backsound from SoundHelix...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    print(f"      saved ({out_path.stat().st_size//1024} KB)")
    return out_path

def mix(voice_audio: Path, out_path: Path, bg_volume: float = 0.08) -> Path:
    """Mix voice audio with background music at low volume."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg_raw = out_path.parent / "backsound_raw.mp3"
    download_random(bg_raw)

    voice_dur = probe_duration(voice_audio)
    bg_dur = probe_duration(bg_raw)

    if bg_dur < voice_dur:
        loops = int(voice_dur // bg_dur) + 1
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", str(loops), "-i", str(bg_raw),
            "-t", f"{voice_dur:.3f}",
            "-c", "copy", str(out_path.parent / "backsound_looped.mp3"),
        ], check=True, capture_output=True)
        bg = out_path.parent / "backsound_looped.mp3"
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(bg_raw),
            "-t", f"{voice_dur:.3f}",
            "-c", "copy", str(out_path.parent / "backsound_trimmed.mp3"),
        ], check=True, capture_output=True)
        bg = out_path.parent / "backsound_trimmed.mp3"

    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(voice_audio),
        "-i", str(bg),
        "-filter_complex",
        f"[1:a]volume={bg_volume}[bg];[0:a][bg]amix=inputs=2:duration=first[a]",
        "-map", "[a]",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ], check=True, capture_output=True)
    print(f"      mixed with backsound (bg_volume={bg_volume})")
    return out_path
