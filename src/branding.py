"""
Branding layer: intro, outro, watermark, and comment box.

Adds professional branding to videos for better channel identity.
"""
import random
import re
import subprocess
from pathlib import Path
from .config import CONFIG, ROOT


def _get_branding_config() -> dict:
    return CONFIG.get("branding", {})


def add_intro(video_path: Path, output_path: Path) -> Path:
    """Prepend intro video to the main video."""
    cfg = _get_branding_config().get("intro", {})
    if not cfg.get("enabled", False):
        return video_path

    intro_path = ROOT / cfg["path"]
    if not intro_path.exists():
        print(f"    branding: intro not found at {intro_path}, skipping")
        return video_path

    duration = cfg.get("duration", 2.5)
    print(f"    branding: adding intro ({duration}s)")

    # Concat intro + main video
    concat_list = output_path.parent / "concat_intro.txt"
    concat_list.write_text(
        f"file '{intro_path}'\nfile '{video_path}'\n",
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)

    if p.returncode != 0:
        print(f"    branding: intro concat failed, using original")
        return video_path

    return output_path


def add_outro(video_path: Path, output_path: Path, cta_text: str = "") -> Path:
    """Append outro video to the main video."""
    cfg = _get_branding_config().get("outro", {})
    if not cfg.get("enabled", False):
        return video_path

    outro_path = ROOT / cfg["path"]
    if not outro_path.exists():
        print(f"    branding: outro not found at {outro_path}, skipping")
        return video_path

    print(f"    branding: adding outro ({cfg.get('duration', 3.0)}s)")

    # Concat main video + outro
    concat_list = output_path.parent / "concat_outro.txt"
    concat_list.write_text(
        f"file '{video_path}'\nfile '{outro_path}'\n",
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)

    if p.returncode != 0:
        print(f"    branding: outro concat failed, using original")
        return video_path

    return output_path


def add_watermark(video_path: Path, output_path: Path) -> Path:
    """Overlay watermark image on video."""
    cfg = _get_branding_config().get("watermark", {})
    if not cfg.get("enabled", False):
        return video_path

    wm_path = ROOT / cfg["path"]
    if not wm_path.exists():
        print(f"    branding: watermark not found at {wm_path}, skipping")
        return video_path

    position = cfg.get("position", "top_right")
    opacity = cfg.get("opacity", 0.4)
    size = cfg.get("size", 80)

    import random
    x_offset = random.randint(-200, 200)

    # Position mapping
    pos_map = {
        "top_right": f"main_w-{size}-20:20",
        "top_left": f"20:20",
        "bottom_right": f"main_w-{size}-20:main_h-{size}-20",
        "bottom_left": f"20:main_h-{size}-20",
        "center": f"(main_w-{size})/2+{x_offset}:(main_h*0.20)",
    }
    overlay_pos = pos_map.get(position, pos_map["top_right"])

    print(f"    branding: adding watermark ({position}, {opacity*100:.0f}%)")

    vf = (
        f"[1:v]scale={size}:-1:force_original_aspect_ratio=decrease,"
        f"format=rgba,colorchannelmixer=aa={opacity}[wm];"
        f"[0:v][wm]overlay={overlay_pos}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(wm_path),
        "-filter_complex", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"    branding: watermark failed: {p.stderr[-300:]}")
        return video_path

    return output_path

def add_comment_box(video_path: Path, output_path: Path) -> Path:
    """Add a random comment bubble with 2 fake users and comments."""
    cfg = _get_branding_config().get("comment_box", {})
    if not cfg.get("enabled", False):
        return video_path

    usernames = cfg.get("usernames", [])
    comments = cfg.get("comments", [])
    if not usernames or not comments:
        return video_path

    # Random social media usernames
    social_usernames = [
        "budi_santoso", "sitinurhaliza", "ahmad_kurniawan", "dewilestari23", "rizki_pratama",
        "anisa.putri", "dwifajar", "rinawati_99", "fajar_hermawan", "lestari_dwi",
        "andi_saputra", "putri.mega", "yoga_permadi", "mega_ayu", "arif_rahman",
        "sari_melati", "dimas_aditya", "citra_purnama", "bayu_sakti", "nisa_rahmawati",
        "fadil_ahmad", "ayu_laksmini", "raka_darmawan", "dina_permana", "ilham_fauzi",
        "wati_susanti", "reza_mahendra", "eka_sari", "gilang_ramadhan", "rani_puspita",
        "vina_anggraeni", "hendra_wijaya", "salsa_bila", "kiki_nurjannah", "lailatul_qodriah",
        "yusuf_mubarok", "amelia_sari", "rudi_hartono", "novi_rahmawati", "taufik_hidayat",
        "dian_kusuma", "hendra_nugraha", "yulianti_putri", "bagas_prasetyo", "rahma_dani",
        "prasetyo_budi", "putri_nabila", "aditya_nugroho", "ghea_pramudita", "firmansyah_ali",
        "anggun_permatasari", "zaki_mubarok", "syifa_nurhaliza", "alif_akbar", "nadhira_azzahra",
        "rifqi_maulana", "salwa_rahmania", "fauzan_hakim", "aulia_sari", "irgi_firmansyah",
        "naila_zahra", "rafa_pratama", "maya_sari", "raka_nugroho", "dita_ayu"
    ]
    u1, u2 = random.sample(social_usernames, 2)
    c1, c2 = random.sample(comments, 2)
    font = cfg.get("font", "Anton")
    font_size = cfg.get("font_size", 26)
    font_color = cfg.get("font_color", "black")
    box_color = cfg.get("box_color", "white@0.9")
    delay = cfg.get("delay_seconds", 1.5)
    margin = cfg.get("margin", 40)

    font_path = ROOT / "assets" / "fonts" / f"{font}-Regular.ttf"
    if not font_path.exists():
        print(f"    branding: font not found, skipping comment box")
        return video_path

    font_ff = str(font_path).replace("\\", "/").replace(":", "\\:")

    def _escape(s):
        for ch in ["\\", "'", '"', ":", "?", ";", "[", "]"]:
            s = s.replace(ch, f"\\{ch}")
        return s

    u1e = _escape(u1)
    u2e = _escape(u2)
    c1e = _escape(c1)
    c2e = _escape(c2)

    print(f"    branding: adding comment box")

    def _esc(s):
        """Escape special chars for ffmpeg drawtext."""
        for ch in ["\\", "'", '"', ":", "?", ";", "[", "]", ","]:
            s = s.replace(ch, f"\\{ch}")
        return s

    u1e = _esc(f"@{u1}")
    u2e = _esc(f"@{u2}")
    c1e = _esc(c1)
    c2e = _esc(c2)

    box_h = 190
    box_top_from_bottom = int(1920 * 0.35)
    line_spacing = 42
    pad_top = 15

    vf = (
        f"drawbox=x=20:y=ih-{box_top_from_bottom}:w=iw-40:h={box_h}:"
        f"color={box_color}:t=fill:"
        f"enable='gte(t,{delay})',"
        f"drawtext=fontfile='{font_ff}':"
        f"text='{u1e}':"
        f"fontcolor=gray:fontsize={font_size - 2}:"
        f"x=40:y=h-{box_top_from_bottom - pad_top}:"
        f"enable='gte(t,{delay})',"
        f"drawtext=fontfile='{font_ff}':"
        f"text='{c1e}':"
        f"fontcolor={font_color}:fontsize={font_size}:"
        f"x=40:y=h-{box_top_from_bottom - pad_top - line_spacing}:"
        f"enable='gte(t,{delay})',"
        f"drawtext=fontfile='{font_ff}':"
        f"text='{u2e}':"
        f"fontcolor=gray:fontsize={font_size - 2}:"
        f"x=40:y=h-{box_top_from_bottom - pad_top - line_spacing * 2}:"
        f"enable='gte(t,{delay})',"
        f"drawtext=fontfile='{font_ff}':"
        f"text='{c2e}':"
        f"fontcolor={font_color}:fontsize={font_size}:"
        f"x=40:y=h-{box_top_from_bottom - pad_top - line_spacing * 3}:"
        f"enable='gte(t,{delay})'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"    branding: comment box failed: {p.stderr[-300:]}")
        return video_path

    return output_path


def apply_all(video_path: Path, work_dir: Path) -> Path:
    """Apply all branding (intro, outro, watermark) to video."""
    cfg = _get_branding_config()
    if not cfg.get("enabled", False):
        return video_path

    brand_dir = work_dir / "branding"
    brand_dir.mkdir(parents=True, exist_ok=True)

    current = video_path

    # Intro
    if cfg.get("intro", {}).get("enabled", False):
        out = brand_dir / "with_intro.mp4"
        current = add_intro(current, out)

    # Watermark
    if cfg.get("watermark", {}).get("enabled", False):
        out = brand_dir / "with_watermark.mp4"
        current = add_watermark(current, out)

    # Comment Box
    if cfg.get("comment_box", {}).get("enabled", False):
        out = brand_dir / "with_comment.mp4"
        current = add_comment_box(current, out)

    # Outro
    if cfg.get("outro", {}).get("enabled", False):
        out = brand_dir / "with_outro.mp4"
        cta = cfg.get("outro", {}).get("cta_text", "")
        current = add_outro(current, out, cta)

    return current
