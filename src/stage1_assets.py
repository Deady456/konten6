import argparse
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
import zipfile

from . import script_long, voice, visuals_ai, thumbnail, captions
from .config import CONFIG, OUTPUT_DIR

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "ai-doc"

def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [STAGE 1] {msg}")

def run_stage1(out_zip: Path | None = None, use_subtitles: bool = False) -> Path:
    _log("Starting Stage 1: Asset Preparation (Script, Voiceover, Batch Images, Thumbnail)")
    
    # 1. Script Generation
    _log("1/4 Generating documentary script with LLM (ROVO-style global ancient engineering)...")
    data = script_long.generate()
    segments = data["segments"]
    _log(f"    Topic: \"{data['title']}\" ({len(segments)} narrative scenes)")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = OUTPUT_DIR / f"{stamp}_{slug(data['title'])}"
    work.mkdir(parents=True, exist_ok=True)

    # 2. Voiceover Synthesis
    _log("2/4 Synthesizing voiceover (9Router Gemini TTS / Charon / Orus)...")
    voice_mp3 = voice.synth(data["full_text"], work / "voice.mp3")
    _log(f"    Voice saved: {voice_mp3.name} ({voice_mp3.stat().st_size / 1024:.0f} KB)")

    words = None
    ass_path = None
    if use_subtitles:
        _log("    Transcribing for subtitles (Faster-Whisper)...")
        v = CONFIG.get("video_long", {"width": 1920, "height": 1080, "fps": 30})
        words = captions.transcribe_words(voice_mp3, original_text=data["full_text"])
        ass_path = captions.write_ass(words, work / "captions.ass", v["width"], v["height"])

    # 3. Batch Image Generation with Rate Limit Protection & Checkpoint
    _log(f"3/4 Generating {len(segments)} AI Images in 16:9 (AWS FLUX.2 / Pollinations)...")
    image_dir = work / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    v = CONFIG.get("video_long", {"width": 1920, "height": 1080, "fps": 30})
    img_w, img_h = v.get("width", 1920), v.get("height", 1080)
    image_paths = []

    BATCH_SIZE = 10
    for i, seg in enumerate(segments):
        prompt = seg.get("image_prompt", seg.get("title", "ancient architecture diagram"))
        img_path = image_dir / f"seg_{i:03d}.jpg"
        _log(f"    [{i+1}/{len(segments)}] \"{seg['title']}\"")
        visuals_ai.generate(prompt, img_path, width=img_w, height=img_h)
        image_paths.append(str(img_path.resolve()))
        
        # Brief pause between batches to protect API quota & prevent rate limits
        if (i + 1) % BATCH_SIZE == 0 and (i + 1) < len(segments):
            _log(f"    [Cooldown] Completed batch of {BATCH_SIZE} images. Pausing 3s...")
            time.sleep(3)

    # 4. High-CTR 16:9 Custom Thumbnail
    _log("4/4 Generating High-CTR 16:9 Custom Thumbnail...")
    thumb_path = work / "thumbnail.jpg"
    hook_text = data.get("thumbnail_text") or data["title"]
    first_img = Path(image_paths[0]) if image_paths else None
    thumb = thumbnail.generate(hook_text, thumb_path, bg_path=first_img)
    _log(f"    Thumbnail ready: {thumb.name} ({thumb.stat().st_size // 1024} KB)")

    # 5. Save bundle manifest
    bundle_manifest = {
        "timestamp": stamp,
        "title": data["title"],
        "description": data.get("description", CONFIG.get("description", "")),
        "tags": data.get("tags", CONFIG["upload"]["default_tags"]),
        "thumbnail_text": hook_text,
        "full_text": data["full_text"],
        "segments": segments,
        "image_paths": [Path(p).name for p in image_paths],
        "voice_file": voice_mp3.name,
        "captions_ass": ass_path.name if ass_path else None,
        "thumbnail_file": thumb_path.name,
        "words": words,
    }
    manifest_path = work / "bundle.json"
    manifest_path.write_text(json.dumps(bundle_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    _log("    bundle.json manifest created.")

    # 6. Create Zip Archive for Stage 2
    target_zip = out_zip or (OUTPUT_DIR / "bundle.zip")
    if target_zip.exists():
        target_zip.unlink()
    
    with zipfile.ZipFile(target_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, arcname="bundle.json")
        zf.write(voice_mp3, arcname=voice_mp3.name)
        zf.write(thumb_path, arcname=thumb_path.name)
        if ass_path and ass_path.exists():
            zf.write(ass_path, arcname=ass_path.name)
        for p in image_paths:
            img_file = Path(p)
            if img_file.exists():
                zf.write(img_file, arcname=f"images/{img_file.name}")

    _log(f"Stage 1 Complete! Bundle archive ready: {target_zip} ({target_zip.stat().st_size / (1024*1024):.1f} MB)")
    return target_zip

def main():
    p = argparse.ArgumentParser(description="Stage 1: Asset Preparation Pipeline")
    p.add_argument("--out-zip", default=None, help="Output zip file path (default: output/bundle.zip)")
    p.add_argument("--subtitles", action="store_true", help="Generate subtitles")
    args = p.parse_args()

    zip_path = Path(args.out_zip) if args.out_zip else None
    run_stage1(out_zip=zip_path, use_subtitles=args.subtitles)
    print("\n[STAGE 1] All assets prepared and zipped successfully!")

if __name__ == "__main__":
    main()
