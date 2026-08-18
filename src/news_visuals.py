import os
import re
import json
import time
import random
import requests
import subprocess
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from .config import CONFIG, ROOT

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

PORTAL_NAMES = ["DETIKNEWS", "KOMPAS.COM", "TRIBUNNEWS", "CNN INDONESIA", "TEMPO.CO", "KASUS KRIMINAL"]

def probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 60.0


def _search_detik(query: str) -> list[str]:
    """Fetch high-res news photos from Detik.com search."""
    url = f"https://www.detik.com/search/searchall?query={quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        matches = re.findall(r'<img[^>]+src="(https://akcdn\.detik\.net\.id/[^"]+)"', r.text)
        results = []
        for m in matches:
            if "logo" not in m.lower() and "icon" not in m.lower() and "avatar" not in m.lower():
                high_res = re.sub(r'\?.*$', '', m) + "?w=1080&q=95"
                if high_res not in results:
                    results.append(high_res)
        return results
    except Exception as e:
        return []


def _search_kompas(query: str) -> list[str]:
    """Fetch news photos from Kompas.com search."""
    url = f"https://search.kompas.com/search/?q={quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        matches = re.findall(r'src="(https://asset\.kompas\.com/crops/[^"]+)"', r.text)
        results = []
        for m in matches:
            if "logo" not in m.lower() and "icon" not in m.lower() and "kompascom" not in m.lower():
                if m not in results:
                    results.append(m)
        return results
    except Exception as e:
        return []


def _search_wikipedia(query: str) -> list[str]:
    """Fetch high-resolution archival photos from Wikipedia Indonesia."""
    url = f"https://id.wikipedia.org/w/api.php?action=query&format=json&generator=search&gsrsearch={quote(query)}&gsrlimit=5&prop=pageimages&piprop=original|thumbnail&pithumbsize=1080"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        pages = r.json().get("query", {}).get("pages", {})
        results = []
        for pid, page in pages.items():
            img = page.get("original", {}).get("source") or page.get("thumbnail", {}).get("source")
            if img and img not in results and "logo" not in img.lower():
                results.append(img)
        return results
    except Exception as e:
        return []


def _search_google_images(query: str) -> list[str]:
    """Fallback: Scrape Google Images for Indonesian news photos."""
    url = f"https://www.google.com/search?q={quote(query + ' berita foto')}&tbm=isch&hl=id&gl=ID"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        matches = re.findall(r'https://[^"]+\.(?:jpg|jpeg|png|webp)', r.text)
        clean = []
        for m in matches:
            if "gstatic" not in m and "google" not in m and "logo" not in m.lower() and len(m) > 25:
                if m not in clean:
                    clean.append(m)
        return clean
    except Exception as e:
        return []


def _download_image(url: str, out_path: Path) -> bool:
    """Download image to out_path with size check."""
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        if r.status_code == 200:
            content = r.content
            if len(content) > 3000:
                out_path.write_bytes(content)
                with Image.open(out_path) as im:
                    im.verify()
                return True
    except Exception:
        pass
    return False


def _get_font(size: int, bold: bool = False):
    """Load appropriate TrueType font."""
    font_paths = [
        ROOT / "Bevan.ttf",
        Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\impact.ttf"),
    ]
    for p in font_paths:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()


def create_news_portal_card(
    base_img_path: Path,
    out_path: Path,
    portal_name: str,
    headline_text: str,
    w: int = 1080,
    h: int = 1920,
    is_breaking_news: bool = True
):
    """
    Create a realistic Indonesian official news portal screenshot card.
    Overlays authentic news headers, breaking news badges, date, and dark cinematic true crime vignette.
    """
    try:
        im = Image.open(base_img_path).convert("RGBA")
    except Exception:
        im = Image.new("RGBA", (w, h), (20, 20, 30, 255))

    # Resize/Crop to 9:16 portrait
    iw, ih = im.size
    target_ratio = w / h
    img_ratio = iw / ih

    if img_ratio > target_ratio:
        new_w = int(ih * target_ratio)
        offset = (iw - new_w) // 2
        im = im.crop((offset, 0, offset + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        offset = (ih - new_h) // 2
        im = im.crop((0, offset, iw, offset + new_h))

    im = im.resize((w, h), Image.Resampling.LANCZOS)

    # True crime color grading: slight desaturation & contrast
    enhancer = ImageEnhance.Color(im)
    im = enhancer.enhance(0.85)
    contrast = ImageEnhance.Contrast(im)
    im = contrast.enhance(1.15)

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Dark true-crime gradient overlays (top and bottom)
    for y in range(400):
        alpha = int(220 * (1.0 - y / 400.0) ** 1.5)
        draw.line([(0, y), (w, y)], fill=(10, 10, 15, alpha))
    
    for y in range(h - 700, h):
        factor = (y - (h - 700)) / 700.0
        alpha = int(240 * (factor ** 1.3))
        draw.line([(0, y), (w, y)], fill=(10, 10, 15, alpha))

    # 2. Portal Header Bar at Top
    header_y = 120
    draw.rectangle([(40, header_y), (w - 40, header_y + 110)], fill=(15, 18, 28, 230))
    draw.rectangle([(40, header_y), (52, header_y + 110)], fill=(220, 30, 30, 255))

    font_portal = _get_font(42, bold=True)
    font_badge = _get_font(26, bold=True)
    font_date = _get_font(26, bold=False)

    draw.text((70, header_y + 18), portal_name.upper(), font=font_portal, fill=(255, 255, 255, 255))
    
    badge_text = "LIPUTAN KHUSUS" if not is_breaking_news else "BREAKING NEWS"
    draw.rectangle([(w - 320, header_y + 20), (w - 60, header_y + 55)], fill=(220, 30, 30, 255))
    draw.text((w - 305, header_y + 24), badge_text, font=font_badge, fill=(255, 255, 255, 255))

    today_str = time.strftime("%d %B %Y | Kasus & Fakta Hukum")
    draw.text((70, header_y + 68), today_str, font=font_date, fill=(180, 190, 210, 255))

    # 3. Headline Box at Bottom (if headline provided)
    if headline_text:
        box_y = h - 620
        draw.rectangle([(40, box_y), (w - 40, box_y + 320)], fill=(12, 14, 22, 235))
        draw.rectangle([(40, box_y), (w - 40, box_y + 6)], fill=(220, 30, 30, 255))

        draw.rectangle([(60, box_y + 25), (280, box_y + 65)], fill=(220, 30, 30, 255))
        draw.text((75, box_y + 30), "ALUR KASUS", font=font_badge, fill=(255, 255, 255, 255))

        font_headline = _get_font(44, bold=True)
        words = headline_text.split()
        lines = []
        cur_line = []
        for word in words:
            cur_line.append(word)
            test_line = " ".join(cur_line)
            if len(test_line) > 32 and len(cur_line) > 1:
                cur_line.pop()
                lines.append(" ".join(cur_line))
                cur_line = [word]
        if cur_line:
            lines.append(" ".join(cur_line))

        headline_draw_y = box_y + 85
        for line in lines[:4]:
            draw.text((60, headline_draw_y), line, font=font_headline, fill=(255, 255, 255, 255))
            headline_draw_y += 54

    final_img = Image.alpha_composite(im, overlay).convert("RGB")
    final_img.save(out_path, quality=95)
    return out_path


def _image_to_video(img_path: Path, out_path: Path, duration: float, w: int, h: int, fps: int, zoom_direction: int = 0):
    """Convert static news image to smooth 9:16 Ken Burns video clip."""
    frames = int(duration * fps)
    
    # 0 = zoom-in, 1 = zoom-out, 2 = pan
    if zoom_direction % 2 == 0:
        zoom_expr = f"zoompan=z='min(1.18,1.0+0.007*on)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
    else:
        zoom_expr = f"zoompan=z='max(1.0,1.15-0.007*on)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"{zoom_expr}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration:.3f}",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def _fallback_video(out_path: Path, duration: float, w: int, h: int, fps: int):
    """Create cinematic true-crime colored background as last resort."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=#0f111a:s={w}x{h}:r={fps}:d={duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True)


def _calculate_scene_durations(words: list[dict], scenes: list[dict], total_audio_dur: float) -> list[float]:
    """Calculate exact spoken duration for each scene to sync 100% with audio."""
    if not words or not scenes:
        per_scene = total_audio_dur / max(1, len(scenes))
        return [max(3.0, per_scene) for _ in scenes]

    spoken = [s.get("text", "").lower() for s in scenes]
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
        durations.append(max(2.5, end_t - start_t))
        cursor = end_idx

    # Scale durations to guarantee video covers entire voiceover audio
    tot = sum(durations)
    if tot < total_audio_dur:
        extra = total_audio_dur - tot + 0.5
        durations[-1] += extra
    return durations


def fetch_all(scenes: list[dict], out_dir: Path, words: list[dict] = None, voice_audio: Path = None) -> list[Path]:
    """
    Fetch authentic Indonesian news portal photos and create dynamic 2-3.5s video cuts covering the FULL audio length.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    all_clips = []
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]

    total_audio_dur = probe_duration(voice_audio) if (voice_audio and voice_audio.exists()) else (len(scenes) * 7.0)
    scene_durations = _calculate_scene_durations(words, scenes, total_audio_dur)

    used_images = set()
    clip_counter = 0

    print(f"    [News Visuals] Generating dynamic cuts for {len(scenes)} scenes covering {total_audio_dur:.1f}s total audio...")

    for i, scene in enumerate(scenes):
        total_scene_dur = scene_durations[i]
        
        # Sub-divide scene into 2.5s - 3.5s dynamic visual cuts
        num_subclips = max(1, int(round(total_scene_dur / 3.0)))
        subclip_dur = total_scene_dur / num_subclips

        # Build prioritized search queries for this scene
        queries = []
        factual = scene.get("factual_subject")
        if factual and isinstance(factual, str) and factual.lower() != "null":
            queries.append(factual.strip())

        news_q = scene.get("news_query") or scene.get("visual_query", "")
        if news_q:
            queries.append(news_q.strip())

        text = scene.get("text", "")
        clean_words = [cw for cw in text.split() if len(cw) > 3 and not cw.startswith("http")]
        if clean_words:
            queries.append(" ".join(clean_words[:5]))
            if len(clean_words) > 5:
                queries.append(" ".join(clean_words[3:8]))

        # Gather multiple candidate image URLs
        found_urls = []
        for q in queries:
            for u in _search_detik(q):
                if u not in used_images and u not in found_urls:
                    found_urls.append(u)
            for u in _search_kompas(q):
                if u not in used_images and u not in found_urls:
                    found_urls.append(u)
            for u in _search_wikipedia(q):
                if u not in used_images and u not in found_urls:
                    found_urls.append(u)
            for u in _search_google_images(q):
                if u not in used_images and u not in found_urls:
                    found_urls.append(u)
            if len(found_urls) >= num_subclips * 2:
                break

        for sub_idx in range(num_subclips):
            clip_name = f"clip_{clip_counter:03d}.mp4"
            out_clip_path = out_dir / clip_name
            raw_img_path = out_dir / f"raw_{clip_counter:03d}.jpg"
            final_img_path = out_dir / f"card_{clip_counter:03d}.jpg"

            img_downloaded = False
            for u in found_urls:
                if u not in used_images and _download_image(u, raw_img_path):
                    used_images.add(u)
                    img_downloaded = True
                    break

            if img_downloaded:
                portal = random.choice(PORTAL_NAMES)
                # Hook scene or alternate scenes get news card layout
                is_card = (i == 0 and sub_idx == 0) or (sub_idx == 0 and i % 2 == 1)
                headline = scene.get("text", "")[:85] if is_card else ""

                create_news_portal_card(
                    base_img_path=raw_img_path,
                    out_path=final_img_path,
                    portal_name=portal,
                    headline_text=headline,
                    w=w,
                    h=h,
                    is_breaking_news=(i == 0)
                )
                _image_to_video(final_img_path, out_clip_path, subclip_dur, w, h, fps, zoom_direction=clip_counter)
            else:
                _fallback_video(out_clip_path, subclip_dur, w, h, fps)

            all_clips.append(out_clip_path)
            clip_counter += 1

        print(f"    scene {i+1}/{len(scenes)}: {total_scene_dur:.1f}s -> {num_subclips} dynamic cuts generated")

    print(f"    [News Visuals] Ready: {len(all_clips)} dynamic clips covering full video duration.")
    return all_clips
