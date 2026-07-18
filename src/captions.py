import time
import re
from pathlib import Path
from faster_whisper import WhisperModel
from .config import CONFIG

_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        size = CONFIG["captions"].get("whisper_model", "base")
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    return _model


def _normalize(word: str) -> str:
    """Normalize word for comparison (lowercase, strip punctuation)."""
    return re.sub(r"[^\w]", "", word.lower().strip())


def verify_transcription(words: list[dict], original_text: str) -> list[dict]:
    """Fix Whisper misspellings by comparing with original script text.

    Whisper writes phonetically (e.g. 'cacing' -> 'chatching').
    This function verifies each word against the original LLM script
    and replaces incorrect spellings while keeping timestamps.
    """
    original_words = [_normalize(w) for w in original_text.split() if _normalize(w)]
    verified = []
    orig_idx = 0

    for w in words:
        whisper_word = _normalize(w["word"])

        if not whisper_word:
            verified.append(w)
            continue

        # Try to find matching word in original text
        matched = False
        if orig_idx < len(original_words):
            # Check current position and nearby positions (fuzzy match)
            for offset in range(-2, 3):
                check_idx = orig_idx + offset
                if 0 <= check_idx < len(original_words):
                    orig_word = original_words[check_idx]
                    # Exact match
                    if whisper_word == orig_word:
                        w = {**w, "word": original_text.split()[check_idx]}
                        orig_idx = check_idx + 1
                        matched = True
                        break
                    # Similar match (edit distance 1-2 for short words)
                    elif len(whisper_word) > 3 and len(orig_word) > 3:
                        if _similar(whisper_word, orig_word):
                            w = {**w, "word": original_text.split()[check_idx]}
                            orig_idx = check_idx + 1
                            matched = True
                            break

        if not matched:
            # Keep original whisper word if no match found
            pass

        verified.append(w)

    return verified


def _similar(a: str, b: str) -> bool:
    """Check if two words are similar (simple character overlap)."""
    if a == b:
        return True
    # Check if most characters match (for typo-like differences)
    if len(a) >= 4 and len(b) >= 4:
        # Count matching characters in order
        matches = sum(1 for ca, cb in zip(a, b) if ca == cb)
        ratio = matches / max(len(a), len(b))
        return ratio > 0.7
    return False


def transcribe_words(audio_path: Path, original_text: str = "") -> list[dict]:
    model = _get_model()
    print(f"    model loaded, transcribing {audio_path.name}...")
    t0 = time.time()
    segments, info = model.transcribe(str(audio_path), word_timestamps=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})
    print(f"    done in {time.time()-t0:.1f}s")

    # Fix misspellings by verifying against original script
    if original_text:
        before_fix = [w["word"] for w in words]
        words = verify_transcription(words, original_text)
        after_fix = [w["word"] for w in words]
        changes = sum(1 for a, b in zip(before_fix, after_fix) if a != b)
        if changes:
            print(f"    fixed {changes} misspelled words")

    return words


def _fmt_ts(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def write_ass(words: list[dict], out_path: Path, video_w: int, video_h: int, offset: float = 0.0) -> Path:
    c = CONFIG["captions"]
    chunk_size = c["words_per_caption"]
    margin_v = int(video_h * (1 - c["position_y"]))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{c['font']},{c['font_size']},{c['primary_color']},&H00FFFFFF,{c['outline_color']},&H00000000,-1,0,0,0,100,100,0,0,1,{c['outline']},2,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = []
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        start = _fmt_ts(chunk[0]["start"] + offset)
        end = _fmt_ts(chunk[-1]["end"] + offset)
        text = " ".join(w["word"].strip() for w in chunk).upper()
        if chunk_size == 1:
            text = f"{{\\fscx120\\fscy120\\t(0,150,\\fscx100\\fscy100)}}{text}"
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    out_path.write_text(header + "\n".join(lines), encoding="utf-8")
    return out_path
