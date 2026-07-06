import subprocess, json, random
from pathlib import Path

SOURCES = [
    "https://www.youtube.com/watch?v=5XEotddQbPY",  # Clear Skies - Scott Buckley
    "https://www.youtube.com/watch?v=hzb9DsLguJo",  # The Great Sea - Scott Buckley
    "https://www.youtube.com/watch?v=z6Zpo1ipCPQ",  # Audio Library daily
    "https://www.youtube.com/watch?v=nr32COcc90s",  # Audio Library daily
    "https://www.youtube.com/watch?v=4hjQD1aPMVw",  # Audio Library daily
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
    print(f"    downloading backsound from YouTube Audio Library...")
    bg_pattern = str(out_path.parent / "backsound_raw.%(ext)s")
    subprocess.run([
        "yt-dlp", "-f", "bestaudio", "--extract-audio",
        "--audio-format", "mp3", "--audio-quality", "192K",
        "--no-playlist",
        "-o", bg_pattern,
        url,
    ], check=True, capture_output=True)
    bg_mp3 = out_path.parent / "backsound_raw.mp3"
    print(f"      saved ({bg_mp3.stat().st_size//1024} KB)")
    return bg_mp3

def mix(voice_audio: Path, out_path: Path, bg_volume: float = 0.08) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        bg_raw = download_random(out_path)
    except Exception as e:
        print(f"    backsound download failed ({e}), falling back to voice-only")
        out_path.write_bytes(voice_audio.read_bytes())
        return out_path

    voice_dur = probe_duration(voice_audio)
    bg_dur = probe_duration(bg_raw)

    bg_adj = out_path.parent / "backsound_prepared.wav"
    if bg_dur < voice_dur:
        import math
        loops = int(math.ceil(voice_dur / bg_dur))
        list_path = out_path.parent / "backsound_list.txt"
        list_path.write_text("\n".join([f"file '{bg_raw.resolve()}'"] * loops) + "\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            "-t", f"{voice_dur:.3f}",
            "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le", str(bg_adj),
        ], check=True, capture_output=True)
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(bg_raw),
            "-t", f"{voice_dur:.3f}",
            "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le", str(bg_adj),
        ], check=True, capture_output=True)
    bg = bg_adj

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(voice_audio),
            "-i", str(bg),
            "-filter_complex",
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[voice];"
            f"[1:a]volume={bg_volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bg];"
            f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[a]",
            "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ], check=True, capture_output=True)
        print(f"      mixed with backsound (bg_volume={bg_volume})")
        return out_path
    except subprocess.CalledProcessError:
        print(f"    backsound mix failed, falling back to voice-only")
        out_path.write_bytes(voice_audio.read_bytes())
        return out_path
