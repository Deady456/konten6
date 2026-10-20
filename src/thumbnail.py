from pathlib import Path
import re
import random
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

THUMB_W, THUMB_H = 1280, 720
_COLORS = [
    ["#1e293b", "#0f172a"], ["#18181b", "#27272a"],
    ["#1f2937", "#111827"], ["#292524", "#1c1917"],
]

def _load_font(size: int) -> ImageFont:
    candidates = [
        Path(__file__).parent.parent / "Bevan.ttf",
        Path("C:/Windows/Fonts/impact.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
        "Bevan.ttf",
        "impact.ttf",
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf",
        "NotoSans-Bold.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(str(c), size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()

def _extract_hook(text: str, max_words: int = 4) -> str:
    clean = re.sub(r"[:\-\–\—\(\)\[\]]", " ", text).strip()
    words = clean.split()
    return " ".join(words[:max_words]).upper()

def generate(title_or_hook: str, out_path: Path, bg_path: Path | None = None) -> Path:
    """
    Generate a high-CTR 16:9 thumbnail (1280x720) optimized for YouTube Long-Form Documentaries.
    - Punchy hook text (2-4 words, ALL CAPS) anchored at upper-left.
    - Two-tone high contrast colors (White + Golden Yellow) with thick black stroke outline.
    - Contrast/saturation boosted architectural cutaway background.
    - Safe zone: Bottom-right is completely unblocked for YouTube video duration badge (e.g. 14:20).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if bg_path and bg_path.exists():
        try:
            bg = Image.open(bg_path).convert("RGB")
            bw, bh = bg.size
            target_ratio = 16 / 9
            current_ratio = bw / bh
            if current_ratio > target_ratio:
                new_w = int(bh * target_ratio)
                left = (bw - new_w) // 2
                bg = bg.crop((left, 0, left + new_w, bh))
            elif current_ratio < target_ratio:
                new_h = int(bw / target_ratio)
                top = (bh - new_h) // 2
                bg = bg.crop((0, top, bw, top + new_h))
            bg = bg.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            bg = ImageEnhance.Contrast(bg).enhance(1.15)
            bg = ImageEnhance.Color(bg).enhance(1.20)
        except Exception:
            bg = Image.new("RGB", (THUMB_W, THUMB_H), (20, 24, 33))
    else:
        bg = Image.new("RGB", (THUMB_W, THUMB_H), (20, 24, 33))

    # Left-side dark gradient vignette to ensure text legibility over any background visual
    vignette = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    for x in range(750):
        alpha = int(170 * (1 - (x / 750) ** 1.5))
        v_draw.line([(x, 0), (x, THUMB_H)], fill=(0, 0, 0, alpha))
    bg.paste(vignette, (0, 0), vignette)

    # Process text hook (limit to max 5 words / max 40 chars)
    raw_text = title_or_hook.strip()
    if len(raw_text.split()) > 5 or len(raw_text) > 35:
        raw_text = _extract_hook(raw_text, max_words=4)
    words = raw_text.upper().split()

    if len(words) <= 2:
        lines = [" ".join(words)]
    elif len(words) <= 4:
        mid = (len(words) + 1) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = [" ".join(words[:2]), " ".join(words[2:4]), " ".join(words[4:6])]

    font_size = 78 if len(lines) <= 2 else 66
    font = _load_font(font_size)
    draw = ImageDraw.Draw(bg)

    start_x = 60
    start_y = 70
    line_spacing = font_size + 14
    colors = ["#FFFFFF", "#FFDE00", "#FFFFFF"]

    for i, line in enumerate(lines):
        color = colors[i % len(colors)]
        y = start_y + i * line_spacing
        draw.text((start_x, y), line, font=font, fill=color, stroke_width=7, stroke_fill="#000000")

    img = bg.convert("RGB")
    img.save(out_path, quality=92)
    print(f"    thumbnail saved: {out_path.name} ({out_path.stat().st_size//1024} KB)")
    return out_path

def upload(yt_service, video_id: str, thumb_path: Path):
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(str(thumb_path), mimetype="image/jpeg")
    yt_service.thumbnails().set(videoId=video_id, media_body=media).execute()
    print(f"    thumbnail uploaded for video {video_id}")
