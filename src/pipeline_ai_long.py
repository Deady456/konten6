import argparse, re, time
from datetime import datetime
from . import script_long, voice, captions, visuals_ai, assemble_ai, backsound, upload, state
from .config import CONFIG, OUTPUT_DIR

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "dokumenter"

def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_once(publish_at: str | None = None, upload_to_youtube: bool = True) -> dict:
    _log("1/6 Generating long-form script with LLM")
    data = script_long.generate()
    segments = data["segments"]
    _log(f"    {len(segments)} segments, {len(data['full_text'])} chars")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = OUTPUT_DIR / f"{stamp}_{slug(data['title'])}"
    work.mkdir(parents=True, exist_ok=True)

    _log("2/6 Synthesizing voiceover with Edge TTS")
    voice_mp3 = voice.synth(data["full_text"], work / "voice.mp3")
    _log(f"    voice saved ({voice_mp3.stat().st_size/1024:.0f} KB)")

    voice_mixed = work / "voice_mixed.mp3"
    _log(f"    mixing backsound -> {voice_mixed.name}")
    backsound.mix(voice_mp3, voice_mixed, bg_volume=CONFIG.get("backsound_volume", 0.08))

    _log("3/6 Transcribing for word-level captions (Faster-Whisper)")
    t0 = time.time()
    words = captions.transcribe_words(voice_mp3)
    _log(f"    {len(words)} words in {time.time()-t0:.1f}s")

    _log("4/6 Generating AI images via Pollinations")
    image_dir = work / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    v = CONFIG["video"]
    img_w, img_h = v["width"], v["height"]
    for i, seg in enumerate(segments):
        prompt = seg.get("image_prompt", seg.get("title", "abstract background"))
        img_path = image_dir / f"seg_{i:02d}.jpg"
        _log(f"    seg {i+1}/{len(segments)}: \"{seg['title']}\"")
        t1 = time.time()
        visuals_ai.generate(prompt, img_path, width=img_w, height=img_h)
        _log(f"      done in {time.time()-t1:.0f}s")
        image_paths.append(img_path)

    _log("5/6 Writing caption file")
    v = CONFIG["video"]
    ass_path = captions.write_ass(words, work / "captions.ass", v["width"], v["height"])

    _log("6/6 Assembling video with ffmpeg")
    t0 = time.time()
    scenes = [{"text": s["text"]} for s in segments]
    final = assemble_ai.build(
        image_paths=image_paths,
        voice_audio=voice_mixed,
        captions_ass=ass_path,
        words=words,
        scenes=scenes,
        out_path=work / "final.mp4",
        work_dir=work / "ffmpeg",
    )
    dur = time.time() - t0
    sz = final.stat().st_size / (1024 * 1024)
    _log(f"    final: {final.name} ({sz:.0f} MB, {dur:.0f}s render)")

    video_id = None
    if upload_to_youtube:
        _log("Uploading to YouTube")
        video_id = upload.upload_video(
            video_path=final,
            title=data["title"],
            description=data.get("description", CONFIG.get("description", "Dokumenter AI - Sejarah Peradaban Kuno")),
            tags=data.get("tags", CONFIG["upload"]["default_tags"]),
            publish_at=publish_at,
        )
        _log(f"    uploaded: https://youtube.com/watch?v={video_id}")

    state.add_published({
        "ts": stamp,
        "title": data["title"],
        "path": str(final),
        "video_id": video_id,
        "publish_at": publish_at,
    })
    return {"video_id": video_id, "path": str(final), "title": data["title"]}

def main():
    p = argparse.ArgumentParser(description="Long-form AI documentary pipeline")
    p.add_argument("--no-upload", action="store_true")
    p.add_argument("--publish-at", default=None)
    args = p.parse_args()
    run_once(publish_at=args.publish_at, upload_to_youtube=not args.no_upload)
    print("\n" + "-" * 60)
    print("Done!")
    print("-" * 60)

if __name__ == "__main__":
    main()
