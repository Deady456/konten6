import argparse
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
import zipfile

from . import assemble_ai, dubbing, upload, state, thumbnail
from .config import CONFIG, OUTPUT_DIR

def _log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [STAGE 2] {msg}")

def run_stage2(
    bundle_zip: Path | None = None,
    bundle_dir: Path | None = None,
    upload_to_youtube: bool = True,
    enable_dubbing: bool = True,
    dub_lang: str = "en",
    publish_at: str | None = None
) -> dict:
    _log("Starting Stage 2: Video Rendering, Sulih Suara & YouTube Upload")

    # 1. Unpack bundle if zip provided
    work_dir = bundle_dir
    if bundle_zip and Path(bundle_zip).exists():
        extract_to = OUTPUT_DIR / f"stage2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        extract_to.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bundle_zip, "r") as zf:
            zf.extractall(extract_to)
        work_dir = extract_to
        _log(f"    Extracted bundle archive to {work_dir}")

    if not work_dir or not (work_dir / "bundle.json").exists():
        raise FileNotFoundError(f"bundle.json not found in work directory: {work_dir}")

    manifest = json.loads((work_dir / "bundle.json").read_text(encoding="utf-8"))
    title = manifest["title"]
    _log(f"    Loaded topic: \"{title}\"")

    image_paths = [work_dir / "images" / name for name in manifest["image_paths"]]
    voice_mp3 = work_dir / manifest["voice_file"]
    ass_path = work_dir / manifest["captions_ass"] if manifest.get("captions_ass") else None
    thumb_path = work_dir / manifest["thumbnail_file"]
    segments = manifest["segments"]
    words = manifest.get("words")

    # Validate assets
    missing = [str(p) for p in image_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} images in bundle!")
    if not voice_mp3.exists():
        raise FileNotFoundError(f"Missing voiceover audio: {voice_mp3}")

    _log(f"    Verified {len(image_paths)} images, voiceover audio ({voice_mp3.stat().st_size / 1024:.0f} KB)")

    # 2. Render Clean 16:9 Video with Fast-Paced Multi-Camera Cuts
    _log("1/3 Assembling clean 16:9 video with fast-paced cuts (FFmpeg volume=0.15)...")
    t0 = time.time()
    v = CONFIG.get("video_long", {"width": 1920, "height": 1080, "fps": 30})
    scenes = [{"text": s["text"]} for s in segments]
    final_clean = assemble_ai.build(
        image_paths=image_paths,
        voice_audio=voice_mp3,
        captions_ass=ass_path,
        words=words,
        scenes=scenes,
        out_path=work_dir / "final_clean.mp4",
        work_dir=work_dir / "ffmpeg",
        hook_text="",
        width=v.get("width", 1920),
        height=v.get("height", 1080),
        fps=v.get("fps", 30),
    )
    dur = time.time() - t0
    _log(f"    Clean video rendered: {final_clean.name} ({final_clean.stat().st_size / (1024*1024):.0f} MB, {dur:.0f}s)")

    # 3. Sulih Suara (Dubbing Engine)
    dub_result = {}
    if enable_dubbing:
        _log(f"2/3 Processing Sulih Suara (Dubbing to {dub_lang.upper()})...")
        try:
            primary_mixed_audio = work_dir / "voice_mixed_id.mp3"
            dubbing.mix_dubbed_audio_track(voice_mp3, primary_mixed_audio)
            dub_result = dubbing.process_dubbing(
                work_dir=work_dir,
                script_data=manifest,
                clean_video_path=final_clean,
                primary_voice_audio=primary_mixed_audio,
                target_lang=dub_lang
            )
            _log(f"    Standalone audio track: {Path(dub_result['standalone_audio_track']).name}")
            _log(f"    Multi-audio video: {Path(dub_result['multi_audio_video']).name}")
        except Exception as e:
            _log(f"    Sulih suara failed (non-fatal): {e}")

    # 4. YouTube Upload with High-CTR Custom Thumbnail
    video_id = None
    if upload_to_youtube:
        _log("3/3 Uploading clean video to YouTube Studio with High-CTR Custom Thumbnail...")
        video_id = upload.upload_video(
            video_path=final_clean,
            title=title,
            description=manifest.get("description", CONFIG.get("description", "Dokumenter AI - Sejarah & Arsitektur Kuno")),
            tags=manifest.get("tags", CONFIG["upload"]["default_tags"]),
            publish_at=publish_at,
            thumb_path=thumb_path if thumb_path.exists() else None,
        )
        _log(f"    Published: https://youtube.com/watch?v={video_id}")

    # 5. Record to state.json
    state.add_published({
        "ts": manifest.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")),
        "title": title,
        "path": str(final_clean),
        "video_id": video_id,
        "publish_at": publish_at,
        "dubbed_audio": dub_result.get("standalone_audio_track"),
        "multi_audio_video": dub_result.get("multi_audio_video"),
        "thumbnail": str(thumb_path) if thumb_path.exists() else None,
    })

    return {
        "video_id": video_id,
        "clean_video": str(final_clean),
        "thumbnail": str(thumb_path),
        "title": title
    }

def main():
    p = argparse.ArgumentParser(description="Stage 2: Video Rendering & YouTube Publishing")
    p.add_argument("--bundle-zip", default=None, help="Path to bundle zip archive (e.g. output/bundle.zip)")
    p.add_argument("--bundle-dir", default=None, help="Path to unpacked bundle directory containing bundle.json")
    p.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    p.add_argument("--publish-at", default=None, help="Schedule publish ISO8601 UTC timestamp")
    p.add_argument("--no-dub", action="store_true", help="Disable sulih suara dubbing generation")
    p.add_argument("--dub-lang", default="en", choices=["en", "es", "ar", "ja"], help="Target language for dubbing (default: en)")
    args = p.parse_args()

    zip_file = Path(args.bundle_zip) if args.bundle_zip else (OUTPUT_DIR / "bundle.zip" if (OUTPUT_DIR / "bundle.zip").exists() else None)
    dir_path = Path(args.bundle_dir) if args.bundle_dir else None

    if not zip_file and not dir_path:
        # Check if any bundle directory exists in output
        dirs = [d for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d / "bundle.json").exists()]
        if dirs:
            dir_path = sorted(dirs)[-1]
            _log(f"Auto-selected latest bundle directory: {dir_path.name}")
        else:
            raise FileNotFoundError("No bundle.zip or bundle directory found to render! Run Stage 1 first.")

    res = run_stage2(
        bundle_zip=zip_file if not dir_path else None,
        bundle_dir=dir_path,
        upload_to_youtube=not args.no_upload,
        enable_dubbing=not args.no_dub,
        dub_lang=args.dub_lang,
        publish_at=args.publish_at
    )
    print("\n" + "=" * 60)
    print(f"Stage 2 Completed Successfully! Video: {res.get('video_id') or 'Rendered'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
