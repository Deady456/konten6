import json, subprocess
from pathlib import Path
from .config import CONFIG, ROOT

def _run(cmd: list[str], desc: str = ""):
    if desc:
        print(f"    ffmpeg: {desc}")
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        tail = (p.stderr or "")[-4000:]
        raise RuntimeError(f"Command failed (exit {p.returncode}): {cmd[0]} ...\n--- ffmpeg stderr ---\n{tail}")

def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])

def _scene_durations(words: list[dict], scenes: list[dict]) -> list[float]:
    spoken = [s["text"].lower() for s in scenes]
    flat = [w["word"].strip().lower().strip(".,!?;:\"'") for w in words]
    durations = []
    cursor = 0
    for i, sentence in enumerate(spoken):
        scene_words = [w.strip(".,!?;:\"'") for w in sentence.split()]
        start_idx = cursor
        end_idx = min(cursor + len(scene_words), len(words))
        if i == len(spoken) - 1:
            end_idx = len(words)
        start_t = words[start_idx]["start"] if start_idx < len(words) else words[-1]["end"]
        end_t = words[end_idx - 1]["end"] if end_idx > 0 else start_t
        durations.append(max(0.5, end_t - start_t))
        cursor = end_idx
    return durations

def build(
    image_paths: list[Path],
    voice_audio: Path,
    captions_ass: Path | None = None,
    words: list[dict] | None = None,
    scenes: list[dict] = None,
    out_path: Path = None,
    work_dir: Path = None,
    hook_text: str = "",
    has_hook: bool = False,
    width: int = None,
    height: int = None,
    fps: int = None,
) -> Path:
    v = CONFIG["video"]
    w = width or v["width"]
    h = height or v["height"]
    fps = fps or v["fps"]
    scenes = scenes or []
    work_dir.mkdir(parents=True, exist_ok=True)

    MAX_CLIP = 5.0

    def _zoom_expr(zs, ze, dur, x_expr=None, y_expr=None):
        n = int(dur * fps)
        inc = (ze - zs) / max(1, n - 1)
        x = x_expr or "(iw-iw/zoom)/2"
        y = y_expr or "(ih-ih/zoom)/2"
        return f"z='if(eq(on,1),{zs},min({ze},zoom+{inc:.6f}))':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={fps}"

    audio_dur = probe_duration(voice_audio)

    if words and len(words) > 0 and scenes:
        durations = _scene_durations(words, scenes)
    else:
        # Proportional durations based on scene word counts against total audio length
        counts = [max(1, len(s.get("text", "").split())) for s in scenes] if scenes else [1] * max(1, len(image_paths))
        total_counts = max(1, sum(counts))
        durations = [max(1.0, (c / total_counts) * audio_dur) for c in counts]
        # Pad or trim to match number of images
        if len(durations) < len(image_paths):
            durations.extend([audio_dur / len(image_paths)] * (len(image_paths) - len(durations)))
        durations = durations[:len(image_paths)]
    
    # Ensure hook stays on screen for at least 3 seconds
    if has_hook and len(durations) > 1:
        target_hook_dur = 3.0
        if durations[0] < target_hook_dur:
            deficit = target_hook_dur - durations[0]
            durations[0] = target_hook_dur
            for i in range(1, len(durations)):
                if deficit <= 0:
                    break
                can_borrow = durations[i] - 1.0 # leave at least 1.0s for other scenes
                if can_borrow > 0:
                    borrow = min(deficit, can_borrow)
                    durations[i] -= borrow
                    deficit -= borrow
                    
    total_video = sum(durations)
    if total_video < audio_dur:
        extra = audio_dur - total_video + 1.0
        durations[-1] += extra
        print(f"    last scene extended +{extra:.1f}s to match audio")

    seg_files = []
    for i, (img, dur) in enumerate(zip(image_paths, durations)):
        n_clips = max(1, int(round(dur / MAX_CLIP)))
        clip_dur = dur / n_clips
        n_frames = max(1, int(clip_dur * fps))

        # 6 Cinematic camera focal shot profiles (ROVO-style fast pacing & multi-angle cuts):
        camera_shots = [
            (1.0, 1.08, "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"),                               # 1. Wide Establishing Zoom-In
            (1.22, 1.28, "(iw-iw/zoom)/2", "(ih-ih/zoom)*0.15"),                           # 2. Close-up Top (Roof / Intake / Ceiling)
            (1.18, 1.18, f"(iw-iw/zoom)*(on/{n_frames})", "(ih-ih/zoom)/2"),                # 3. Dynamic Pan Left-to-Right
            (1.22, 1.28, "(iw-iw/zoom)/2", "(ih-ih/zoom)*0.85"),                           # 4. Close-up Bottom (Subterranean Canal / Foundation)
            (1.20, 1.26, "(iw-iw/zoom)*0.85", "(ih-ih/zoom)*0.4"),                         # 5. Feature Zoom-In (Characters / Mechanism Detail)
            (1.10, 1.0, "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"),                               # 6. Wide Reveal Zoom-Out
        ]

        for j in range(n_clips):
            zs, ze, x_expr, y_expr = camera_shots[(i * 2 + j) % len(camera_shots)]
            seg = work_dir / f"seg_{i:04d}_{j:02d}.mp4"
            _run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(img),
                "-vf", (
                    f"scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h},"
                    f"unsharp=5:5:0.6:3:3:0.3,"
                    f"zoompan=" + _zoom_expr(zs, ze, clip_dur, x_expr, y_expr)
                ),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-t", f"{clip_dur:.3f}",
                str(seg),
            ], f"scene {i+1}/{len(image_paths)} cut {j+1}/{n_clips} ({clip_dur:.1f}s)")
            seg_files.append(seg)

    concat_list = work_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{seg.name}'" for seg in seg_files), encoding="utf-8")

    combined = work_dir / "combined.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy",
        str(combined),
    ], "concat scenes")

    # Build video filter chain: optional hook_text drawtext + optional subtitles
    vf_parts = []
    hook_cfg = CONFIG.get("hook_text", {})
    if hook_text and hook_cfg.get("enabled", False):
        ht_font = str(ROOT / "assets" / "fonts" / "Anton-Regular.ttf").replace("\\", "/").replace(":", "\\:")
        ht_size = hook_cfg.get("font_size", 80)
        ht_duration = hook_cfg.get("duration", 3)
        safe_text = hook_text.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
        vf_parts.append(
            f"drawtext=fontfile='{ht_font}':text='{safe_text}'"
            f":fontsize={ht_size}:fontcolor=white"
            f":borderw=4:bordercolor=black"
            f":x=(w-tw)/2"
            f":y=(h-th)/2"
            f":enable='between(t\\,0\\,{ht_duration})'"
        )

    if captions_ass and Path(captions_ass).exists():
        ass_arg = str(captions_ass).replace("\\", "/").replace(":", "\\:")
        fonts_arg = str(ROOT / "assets" / "fonts").replace("\\", "/").replace(":", "\\:")
        vf_parts.append(f"subtitles='{ass_arg}':fontsdir='{fonts_arg}'")
    
    vf_chain = ",".join(vf_parts)

    # Select background music (random if multiple exist in assets/music or assets/)
    import random
    music_candidates = []
    music_dir = ROOT / "assets" / "music"
    if music_dir.is_dir():
        for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg"):
            music_candidates.extend(list(music_dir.rglob(ext)))
    if not music_candidates:
        music_candidates = [p for p in (ROOT / "assets").glob("*.mp3") if p.is_file() and p.name != "bg.mp3"]
    
    bg_music = random.choice(music_candidates) if music_candidates else (ROOT / "assets" / "bg.mp3")
    cmd = ["ffmpeg", "-y", "-i", str(combined), "-i", str(voice_audio)]
    if bg_music.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(bg_music)])
        audio_filter = "[1:a]volume=1.0[v];[2:a]volume=0.15[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=2[a]"
        if vf_chain:
            cmd.extend(["-filter_complex", f"[0:v]{vf_chain}[vout];{audio_filter}", "-map", "[vout]", "-map", "[a]"])
        else:
            cmd.extend(["-filter_complex", audio_filter, "-map", "0:v", "-map", "[a]"])
    else:
        if vf_chain:
            cmd.extend(["-vf", vf_chain, "-map", "0:v", "-map", "1:a"])
        else:
            cmd.extend(["-map", "0:v", "-map", "1:a"])
            
    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-shortest",
        str(out_path),
    ])
    _run(cmd, "final render (video+audio+captions)")
    return out_path
