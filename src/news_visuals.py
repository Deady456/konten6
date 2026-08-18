import os
import re
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

def _search_detik(query: str) -> list[str]:
    """Fetch high-res news photos from Detik.com search."""
    url = f"https://www.detik.com/search/searchall?query={quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        matches = re.findall(r'<img[^>]+src="(https://akcdn\.detik\.net\.id/[^"]+)"', r.text)
        results = []
        for m in matches:
            if "logo" not in m.lower() and "icon" not in m.lower() and "avatar" not in m.lower():
                high_res = re.sub(r'\?.*$', '', m) + "?w=1080&q=95"
                if high_res not in results:
                    results.append(high_res)
        return results
    except Exception as e:
        print(f"      [Detik] Error: {e}")
        return []


def _search_kompas(query: str) -> list[str]:
    """Fetch news photos from Kompas.com search."""
    url = f"https://search.kompas.com/search/?q={quote(query)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        matches = re.findall(r'src="(https://asset\.kompas\.com/crops/[^"]+)"', r.text)
        results = []
        for m in matches:
            if "logo" not in m.lower() and "icon" not in m.lower() and "kompascom" not in m.lower():
                if m not in results:
                    results.append(m)
        return results
    except Exception as e:
        print(f"      [Kompas] Error: {e}")
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
        print(f"      [Wikipedia] Error: {e}")
        return []


def _search_google_images(query: str) -> list[str]:
    """Fallback: Scrape Google Images for Indonesian news photos."""
    url = f"https://www.google.com/search?q={quote(query + ' berita foto')}&tbm=isch&hl=id&gl=ID"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        matches = re.findall(r'https://[^"]+\.(?:jpg|jpeg|png|webp)', r.text)
        clean = []
        for m in matches:
            if "gstatic" not in m and "google" not in m and "logo" not in m.lower() and len(m) > 25:
                if m not in clean:
                    clean.append(m)
        return clean
    except Exception as e:
        print(f"      [Google Images] Error: {e}")
        return []


def _download_image(url: str, out_path: Path) -> bool:
    """Download image to out_path with size check."""
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=20)
        if r.status_code == 200:
            content = r.content
            if len(content) > 3000:
                out_path.write_bytes(content)
                # Verify PIL can open it
                with Image.open(out_path) as im:
                    im.verify()
                return True
    except Exception as e:
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
    # Top gradient
    for y in range(400):
        alpha = int(220 * (1.0 - y / 400.0) ** 1.5)
        draw.line([(0, y), (w, y)], fill=(10, 10, 15, alpha))
    
    # Bottom gradient
    for y in range(h - 700, h):
        factor = (y - (h - 700)) / 700.0
        alpha = int(240 * (factor ** 1.3))
        draw.line([(0, y), (w, y)], fill=(10, 10, 15, alpha))

    # 2. Portal Header Bar at Top
    header_y = 120
    draw.rectangle([(40, header_y), (w - 40, header_y + 110)], fill=(15, 18, 28, 230))
    # Red accent bar on left of header
    draw.rectangle([(40, header_y), (52, header_y + 110)], fill=(220, 30, 30, 255))

    font_portal = _get_font(42, bold=True)
    font_badge = _get_font(26, bold=True)
    font_date = _get_font(26, bold=False)

    # Portal Logo text
    draw.text((70, header_y + 18), portal_name.upper(), font=font_portal, fill=(255, 255, 255, 255))
    
    # LIVE / BREAKING badge
    badge_text = "LIPUTAN KHUSUS" if not is_breaking_news else "BREAKING NEWS"
    draw.rectangle([(w - 320, header_y + 20), (w - 60, header_y + 55)], fill=(220, 30, 30, 255))
    draw.text((w - 305, header_y + 24), badge_text, font=font_badge, fill=(255, 255, 255, 255))

    # Date / Category
    today_str = time.strftime("%d %B %Y | Kasus & Fakta Hukum")
    draw.text((70, header_y + 68), today_str, font=font_date, fill=(180, 190, 210, 255))

    # 3. Headline Box at Bottom (if headline provided)
    if headline_text:
        box_y = h - 620
        # Dark card backing
        draw.rectangle([(40, box_y), (w - 40, box_y + 320)], fill=(12, 14, 22, 235))
        # Red top border on news card
        draw.rectangle([(40, box_y), (w - 40, box_y + 6)], fill=(220, 30, 30, 255))

        # Headline category pill
        draw.rectangle([(60, box_y + 25), (280, box_y + 65)], fill=(220, 30, 30, 255))
        draw.text((75, box_y + 30), "ALUR KASUS", font=font_badge, fill=(255, 255, 255, 255))

        # Wrap headline text
        font_headline = _get_font(44, bold=True)
        words = headline_text.split()
        lines = []
        cur_line = []
        for word in words:
            cur_line.append(word)
            test_line = " ".join(cur_line)
            # Check length approx
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

    # Merge overlay with base image
    final_img = Image.alpha_composite(im, overlay).convert("RGB")
    final_img.save(out_path, quality=95)
    return out_path


def _image_to_video(img_path: Path, out_path: Path, duration: float, w: int, h: int, fps: int):
    """Convert static news image to smooth 9:16 Ken Burns video clip."""
    frames = int(duration * fps)
    zoom_rate = 0.008  # subtle smooth true-crime zoom
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"zoompan=z='if(eq(on,1),1,min(1.12,zoom+{zoom_rate}))':"
        f"d={frames}:"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"s={w}x{h}:fps={fps}",
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


def fetch_all(scenes: list[dict], out_dir: Path) -> list[Path]:
    """
    Fetch authentic Indonesian news portal photos and create video clips for all scenes.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    v = CONFIG["video"]
    w, h, fps = v["width"], v["height"], v["fps"]

    used_images = set()

    for i, scene in enumerate(scenes):
        scene_dur = scene.get("duration", 5.0)
        out_path = out_dir / f"scene_{i:02d}.mp4"
        raw_img_path = out_dir / f"raw_{i:02d}.jpg"
        final_img_path = out_dir / f"card_{i:02d}.jpg"

        # Build prioritized search queries
        queries = []
        
        # 1. Specific factual subject (entity/name/place)
        factual = scene.get("factual_subject")
        if factual and isinstance(factual, str) and factual.lower() != "null":
            queries.append(factual.strip())

        # 2. News query or visual query
        news_q = scene.get("news_query") or scene.get("visual_query", "")
        if news_q:
            queries.append(news_q.strip())

        # 3. Extract keywords from narration text
        text = scene.get("text", "")
        clean_words = [w for w in text.split() if len(w) > 3 and not w.startswith("http")]
        if clean_words:
            queries.append(" ".join(clean_words[:5]))

        print(f"    scene {i+1}/{len(scenes)}: queries={queries[:2]}")
        t0 = time.time()
        img_downloaded = False

        # Search across official sources
        for q in queries:
            if img_downloaded:
                break
            
            # Step A: Detik.com
            detik_urls = _search_detik(q)
            for u in detik_urls:
                if u not in used_images and _download_image(u, raw_img_path):
                    used_images.add(u)
                    img_downloaded = True
                    print(f"      [Detik.com] Found photo: {u[:70]}...")
                    break

            if img_downloaded:
                break

            # Step B: Kompas.com
            kompas_urls = _search_kompas(q)
            for u in kompas_urls:
                if u not in used_images and _download_image(u, raw_img_path):
                    used_images.add(u)
                    img_downloaded = True
                    print(f"      [Kompas.com] Found photo: {u[:70]}...")
                    break

            if img_downloaded:
                break

            # Step C: Wikipedia Indonesia
            wiki_urls = _search_wikipedia(q)
            for u in wiki_urls:
                if u not in used_images and _download_image(u, raw_img_path):
                    used_images.add(u)
                    img_downloaded = True
                    print(f"      [Wikipedia ID] Found photo: {u[:70]}...")
                    break

            if img_downloaded:
                break

            # Step D: Google Images News
            g_urls = _search_google_images(q)
            for u in g_urls:
                if u not in used_images and _download_image(u, raw_img_path):
                    used_images.add(u)
                    img_downloaded = True
                    print(f"      [Google Images] Found photo: {u[:70]}...")
                    break

        if img_downloaded:
            # Pick a news portal branding
            portal = random.choice(PORTAL_NAMES)
            headline = scene.get("text", "")[:90] if i == 0 else ""
            
            create_news_portal_card(
                base_img_path=raw_img_path,
                out_path=final_img_path,
                portal_name=portal,
                headline_text=headline,
                w=w,
                h=h,
                is_breaking_news=(i == 0)
            )
            _image_to_video(final_img_path, out_path, scene_dur, w, h, fps)
            print(f"      processed news clip ({time.time()-t0:.1f}s)")
        else:
            print(f"      no portal image found, using fallback")
            _fallback_video(out_path, scene_dur, w, h, fps)

        paths.append(out_path)

    return paths
