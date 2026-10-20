import argparse
import re
import time
from datetime import datetime
from pathlib import Path
from . import script_long, voice, captions, visuals_ai, assemble_ai, thumbnail, upload, state, dubbing
from .config import CONFIG, OUTPUT_DIR

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "dokumenter"

def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def run_once(
    publish_at: str | None = None,
    upload_to_youtube: bool = True,
    use_subtitles: bool = False,
    enable_dubbing: bool = True,
    dub_lang: str = "en"
) -> dict:
    """
    Long-form AI Documentary Pipeline:
    - 16:9 Landscape Video (1920x1080)
    - Clean visual frame (No burned-in subtitles per user specification)
    - Full Sulih Suara (Dubbing) engine: English/Spanish/etc audio track + multi-track MP4
    """
    _log("1/5 Generating long-form script with LLM (Ancient Tech & Architecture)")
    data = script_long.generate()
    segments = data["segments"]
    _log(f"    {len(segments)} segments, {len(data['full_text'])} chars")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = OUTPUT_DIR / f"{stamp}_{slug(data['title'])}"
    work.mkdir(parents=True, exist_ok=True)

    _log("2/5 Synthesizing primary voiceover (9Router Gemini TTS / Orus)")
    voice_mp3 = voice.synth(data["full_text"], work / "voice.mp3")
    _log(f"    voice saved ({voice_mp3.stat().st_size/1024:.0f} KB)")

    words = None
    ass_path = None
    if use_subtitles:
        _log("    Transcribing for word-level captions (Faster-Whisper)")
        t0 = time.time()
        words = captions.transcribe_words(voice_mp3, original_text=data["full_text"])
        _log(f"    {len(words)} words in {time.time()-t0:.1f}s")
        v = CONFIG.get("video_long", {"width": 1920, "height": 1080, "fps": 30})
        ass_path = captions.write_ass(words, work / "captions.ass", v["width"], v["height"])
    else:
        _log("    Subtitles disabled: rendering clean visual frames (no hardcoded captions)")

    _log("3/5 Generating AI images (2D Comic Architecture Cutaways in 16:9)")
    image_dir = work / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_paths = []
    v = CONFIG.get("video_long", {"width": 1920, "height": 1080, "fps": 30})
    img_w, img_h = v.get("width", 1920), v.get("height", 1080)
    for i, seg in enumerate(segments):
        prompt = seg.get("image_prompt", seg.get("title", "ancient architecture cross-section"))
        img_path = image_dir / f"seg_{i:02d}.jpg"
        _log(f"    seg {i+1}/{len(segments)}: \"{seg['title']}\"")
        t1 = time.time()
        visuals_ai.generate(prompt, img_path, width=img_w, height=img_h)
        _log(f"      done in {time.time()-t1:.0f}s")
        image_paths.append(img_path)

    _log("4/5 Assembling clean 16:9 video with ffmpeg (music volume=0.15)")
    t0 = time.time()
    scenes = [{"text": s["text"]} for s in segments]
    final_clean = assemble_ai.build(
        image_paths=image_paths,
        voice_audio=voice_mp3,
        captions_ass=ass_path,
        words=words,
        scenes=scenes,
        out_path=work / "final_clean.mp4",
        work_dir=work / "ffmpeg",
        hook_text="",
        width=v.get("width", 1920),
        height=v.get("height", 1080),
        fps=v.get("fps", 30),
    )
    dur = time.time() - t0
    sz = final_clean.stat().st_size / (1024 * 1024)
    _log(f"    clean video rendered: {final_clean.name} ({sz:.0f} MB, {dur:.0f}s)")

    # Prepare primary mixed audio file for easy reference
    primary_mixed_audio = work / "voice_mixed_id.mp3"
    dubbing.mix_dubbed_audio_track(voice_mp3, primary_mixed_audio)

    # Sulih Suara (Dubbing) Engine
    dub_result = {}
    if enable_dubbing:
        _log(f"5/5 Processing Sulih Suara (Dubbing to {dub_lang.upper()})")
        try:
            dub_result = dubbing.process_dubbing(
                work_dir=work,
                script_data=data,
                clean_video_path=final_clean,
                primary_voice_audio=primary_mixed_audio,
                target_lang=dub_lang
            )
            _log(f"    standalone audio track ready: {Path(dub_result['standalone_audio_track']).name}")
            _log(f"    multi-audio MP4 ready: {Path(dub_result['multi_audio_video']).name}")
        except Exception as e:
            _log(f"    sulih suara failed (non-fatal): {e}")

    # Generate High-CTR 16:9 Thumbnail
    thumb_path = work / "thumbnail.jpg"
    thumb = None
    try:
        hook_text = data.get("thumbnail_text") or data["title"]
        thumb = thumbnail.generate(hook_text, thumb_path, bg_path=image_paths[0] if image_paths else None)
    except Exception as e:
        _log(f"    thumbnail generation failed (non-fatal): {e}")

    final_for_upload = final_clean

    video_id = None
    if upload_to_youtube:
        _log("Uploading clean video to YouTube")
        video_id = upload.upload_video(
            video_path=final_for_upload,
            title=data["title"],
            description=data.get("description", CONFIG.get("description", "Dokumenter AI - Sejarah & Arsitektur Kuno")),
            tags=data.get("tags", CONFIG["upload"]["default_tags"]),
            publish_at=publish_at,
        )
        _log(f"    uploaded: https://youtube.com/watch?v={video_id}")
        if thumb and thumb.exists():
            try:
                thumbnail.upload(upload.get_service(), video_id, thumb)
            except Exception as e:
                _log(f"    thumbnail upload failed (non-fatal): {e}")

    state.add_published({
        "ts": stamp,
        "title": data["title"],
        "path": str(final_for_upload),
        "video_id": video_id,
        "publish_at": publish_at,
        "dubbed_audio": dub_result.get("standalone_audio_track"),
        "multi_audio_video": dub_result.get("multi_audio_video"),
        "thumbnail": str(thumb) if thumb else None,
    })

    return {
        "video_id": video_id,
        "clean_video": str(final_clean),
        "dubbed_audio": dub_result.get("standalone_audio_track"),
        "multi_audio_video": dub_result.get("multi_audio_video"),
        "thumbnail": str(thumb) if thumb else None,
        "title": data["title"]
    }

def main():
    p = argparse.ArgumentParser(description="Clean 16:9 Documentary Pipeline with Sulih Suara (Dubbing)")
    p.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    p.add_argument("--publish-at", default=None, help="Schedule publish ISO8601 UTC timestamp")
    p.add_argument("--subtitles", action="store_true", help="Enable burned-in subtitles (default: False)")
    p.add_argument("--no-dub", action="store_true", help="Disable sulih suara dubbing generation")
    p.add_argument("--dub-lang", default="en", choices=["en", "es", "ar", "ja"], help="Target language for dubbing (default: en)")
    args = p.parse_args()

    run_once(
        publish_at=args.publish_at,
        upload_to_youtube=not args.no_upload,
        use_subtitles=args.subtitles,
        enable_dubbing=not args.no_dub,
        dub_lang=args.dub_lang
    )
    print("\n" + "=" * 60)
    print("Documentary Pipeline Completed Successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
