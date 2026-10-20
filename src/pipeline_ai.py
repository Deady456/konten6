import argparse
import re
import time
from datetime import datetime
from pathlib import Path
from . import script, voice, captions, visuals_ai, assemble_ai, upload, state, branding, dubbing
from .config import CONFIG, OUTPUT_DIR

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "ai-short"

def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_once(
    publish_at: str | None = None,
    upload_to_youtube: bool = True,
    use_subtitles: bool = False,
    enable_dubbing: bool = True,
    dub_lang: str = "en"
) -> dict:
    _log("1/6 Generating script with LLM")
    data = script.generate()
    _log(f"    topic: {data['topic']} ({len(data['scenes'])} scenes)")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = OUTPUT_DIR / f"{stamp}_{slug(data['topic'])}"
    work.mkdir(parents=True, exist_ok=True)

    _log("2/6 Synthesizing voiceover (9Router Gemini TTS / Orus)")
    voice_mp3 = voice.synth(data["full_text"], work / "voice.mp3")
    _log(f"    voice saved ({voice_mp3.stat().st_size/1024:.0f} KB)")

    words = None
    ass_path = None
    if use_subtitles:
        _log("3/6 Transcribing for word-level captions (Faster-Whisper)")
        t0 = time.time()
        words = captions.transcribe_words(voice_mp3, original_text=data["full_text"])
        _log(f"    {len(words)} words in {time.time()-t0:.1f}s")
        ass_path = captions.write_ass(
            words, work / "captions.ass",
            CONFIG["video"]["width"], CONFIG["video"]["height"]
        )
    else:
        _log("3/6 Subtitles disabled: clean visual presentation without burned-in text")

    _log("4/6 Generating AI images (2D Comic Architecture Cutaways)")
    image_dir = work / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    
    hook_text = data.get("thumbnail_text", "")
    hook_cfg = CONFIG.get("hook_text", {})
    if not hook_cfg.get("enabled", False):
        hook_text = ""
        
    for i, scene in enumerate(data["scenes"]):
        prompt = scene.get("visual_query", "ancient architecture diagram")
        rich_prompt = f"{prompt}, 2D comic architectural cutaway, blueprint infographic, bold clean lines"
        img_path = image_dir / f"scene_{i:02d}.jpg"
        _log(f"    scene {i+1}/{len(data['scenes'])}: \"{prompt}\"")
        t1 = time.time()
        
        scene_hook = hook_text if i == 0 else ""
        visuals_ai.generate(rich_prompt, img_path, hook_text=scene_hook)
        
        _log(f"      done in {time.time()-t1:.0f}s")
        image_paths.append(img_path)

    _log("5/6 Assembling clean video with ffmpeg (music volume=0.15)")
    t0 = time.time()
    final = assemble_ai.build(
        image_paths=image_paths,
        voice_audio=voice_mp3,
        captions_ass=ass_path,
        words=words,
        scenes=data["scenes"],
        out_path=work / "final_clean.mp4",
        work_dir=work / "ffmpeg",
        hook_text="",
    )
    dur = time.time() - t0
    sz = final.stat().st_size / (1024 * 1024)
    _log(f"    clean video: {final.name} ({sz:.0f} MB, {dur:.0f}s render)")

    _log("Applying branding (watermark)")
    branded = branding.apply_all(final, work / "branding")
    if branded != final:
        final_branded = work / "final_clean.mp4"
        branded.replace(final_branded)
        final = final_branded

    primary_mixed_audio = work / "voice_mixed_id.mp3"
    dubbing.mix_dubbed_audio_track(voice_mp3, primary_mixed_audio)

    dub_result = {}
    if enable_dubbing:
        _log(f"6/6 Processing Sulih Suara (Dubbing to {dub_lang.upper()})")
        # Format script_data for dubbing
        dubbing_script = {
            "title": data.get("title", data.get("topic", "")),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
            "segments": [{"title": s.get("visual_query", ""), "text": s.get("text", "")} for s in data["scenes"]]
        }
        try:
            dub_result = dubbing.process_dubbing(
                work_dir=work,
                script_data=dubbing_script,
                clean_video_path=final,
                primary_voice_audio=primary_mixed_audio,
                target_lang=dub_lang
            )
            _log(f"    standalone audio track ready: {Path(dub_result['standalone_audio_track']).name}")
            _log(f"    multi-audio MP4 ready: {Path(dub_result['multi_audio_video']).name}")
        except Exception as e:
            _log(f"    sulih suara failed (non-fatal): {e}")

    video_id = None
    if upload_to_youtube:
        _log("Uploading to YouTube Shorts")
        video_id = upload.upload_video(
            video_path=final,
            title=data["title"],
            description=data["description"],
            tags=data["tags"],
            publish_at=publish_at,
        )
        _log(f"    uploaded: https://youtube.com/shorts/{video_id}")

    state.add_topic(data["topic"])
    state.add_published({
        "ts": stamp,
        "topic": data["topic"],
        "title": data["title"],
        "path": str(final),
        "video_id": video_id,
        "publish_at": publish_at,
        "dubbed_audio": dub_result.get("standalone_audio_track"),
        "multi_audio_video": dub_result.get("multi_audio_video"),
    })
    return {
        "video_id": video_id,
        "path": str(final),
        "topic": data["topic"],
        "dubbed_audio": dub_result.get("standalone_audio_track"),
        "multi_audio_video": dub_result.get("multi_audio_video"),
    }

def main():
    p = argparse.ArgumentParser(description="AI Pipeline without subtitles + Sulih Suara (Dubbing)")
    p.add_argument("--no-upload", action="store_true")
    p.add_argument("--publish-at", default=None, help="ISO8601 UTC timestamp for scheduled publish")
    p.add_argument("--subtitles", action="store_true", help="Enable burned-in subtitles (default: False)")
    p.add_argument("--no-dub", action="store_true", help="Disable sulih suara dubbing generation")
    p.add_argument("--dub-lang", default="en", choices=["en", "es", "ar", "ja"], help="Target dubbing language (default: en)")
    args = p.parse_args()

    run_once(
        publish_at=args.publish_at,
        upload_to_youtube=not args.no_upload,
        use_subtitles=args.subtitles,
        enable_dubbing=not args.no_dub,
        dub_lang=args.dub_lang
    )
    print("\n" + "=" * 60)
    print("Short Pipeline Completed Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
