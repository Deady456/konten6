import os
import re
import time
import json
import subprocess
import urllib.request
from pathlib import Path
from openai import OpenAI
from .config import CONFIG, ROOT, GROQ_API_KEYS, OPENROUTER_API_KEYS, FALLBACK_PROVIDERS

SHELLSHOCK_AWS_BASE = os.environ.get("NINEROUTER_URL") or os.environ.get("SHELLSHOCK_URL") or "http://13.214.34.200:20128"
SHELLSHOCK_AWS_KEY = os.environ.get("NINEROUTER_KEY") or os.environ.get("NINEROUTER_API_KEY") or os.environ.get("SHELLSHOCK_API_KEY") or "sk-1f7d1788ce9c1aa7-gixqcc-64a9e8fd"

# Language mappings for Gemini TTS and Edge TTS
LANG_PROFILES = {
    "en": {
        "gemini_lang": "English",
        "gemini_voice": "gemini/gemini-2.5-flash-preview-tts/Puck",
        "edge_voice": "en-US-ChristopherNeural",
        "iso639_2": "eng",
        "label": "English (Sulih Suara)",
    },
    "es": {
        "gemini_lang": "Spanish",
        "gemini_voice": "gemini/gemini-2.5-flash-preview-tts/Puck",
        "edge_voice": "es-ES-AlvaroNeural",
        "iso639_2": "spa",
        "label": "Español (Doblado)",
    },
    "ar": {
        "gemini_lang": "Arabic",
        "gemini_voice": "gemini/gemini-2.5-flash-preview-tts/Puck",
        "edge_voice": "ar-SA-HamedNeural",
        "iso639_2": "ara",
        "label": "العربية (دبلجة)",
    },
    "ja": {
        "gemini_lang": "Japanese",
        "gemini_voice": "gemini/gemini-2.5-flash-preview-tts/Kore",
        "edge_voice": "ja-JP-KeitaNeural",
        "iso639_2": "jpn",
        "label": "日本語 (吹替)",
    },
}


def _call_translation_llm(prompt: str, system_prompt: str) -> str:
    """Call LLM with fallback cascade: Groq -> OpenRouter."""
    # 1. Try Groq (qwen/qwen3.8-27b or openai/gpt-oss-120b)
    if GROQ_API_KEYS:
        for key in GROQ_API_KEYS:
            try:
                client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
                resp = client.chat.completions.create(
                    model="qwen/qwen3.8-27b",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=4000,
                )
                return resp.choices[0].message.content
            except Exception as e:
                # Try gpt-oss-120b on Groq
                try:
                    resp = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        response_format={"type": "json_object"},
                        max_tokens=4000,
                    )
                    return resp.choices[0].message.content
                except Exception:
                    continue

    # 2. Try OpenRouter
    if OPENROUTER_API_KEYS:
        for key in OPENROUTER_API_KEYS:
            try:
                client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
                resp = client.chat.completions.create(
                    model="meta-llama/llama-3.3-70b-instruct",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=4000,
                )
                return resp.choices[0].message.content
            except Exception:
                continue

    raise RuntimeError("All LLM providers failed for script translation")


def translate_script(script_data: dict, target_lang: str = "en") -> dict:
    """
    Translates documentary script (title, description, tags, and all segments' narration text)
    into natural, engaging, voiceover-ready target language.
    """
    lang_info = LANG_PROFILES.get(target_lang, LANG_PROFILES["en"])
    target_lang_name = lang_info["gemini_lang"]

    system_prompt = f"""You are an elite bilingual documentary voiceover adapter and scriptwriter.
Your task is to translate and adapt an Indonesian educational documentary script into compelling, natural {target_lang_name} for an international YouTube audience.

Guidelines:
1. Retain the cinematic storytelling, curiosity-driven hooks, and scientific/architectural accuracy.
2. Adapt cultural idioms and units naturally (e.g. mention Fahrenheit alongside Celsius when appropriate for international viewers).
3. The narration must be voiceover-ready: rhythmic, clear, punchy, and conversational.
4. Return ONLY valid JSON with this exact schema:
{{
  "title": "{target_lang_name} title max 95 chars, curiosity-driven",
  "description": "{target_lang_name} description with 6-8 relevant hashtags",
  "tags": ["10-15 lowercase tags in {target_lang_name}"],
  "segments": [
    {{
      "title": "Segment title",
      "text": "Full narrated text of this segment in {target_lang_name}"
    }}
  ]
}}"""

    input_payload = {
        "title": script_data.get("title", ""),
        "description": script_data.get("description", ""),
        "tags": script_data.get("tags", []),
        "segments": [
            {"title": s.get("title", ""), "text": s.get("text", "")}
            for s in script_data.get("segments", [])
        ],
    }

    prompt = f"Please translate and adapt this script into {target_lang_name}:\n{json.dumps(input_payload, ensure_ascii=False, indent=2)}"
    
    raw = _call_translation_llm(prompt, system_prompt)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE)
    
    translated = json.loads(raw)
    
    # Calculate full_text for voice synthesis
    segments = translated.get("segments", [])
    full_text = " ... ".join(s.get("text", "") for s in segments)
    translated["full_text"] = full_text
    translated["target_lang"] = target_lang
    return translated


def _convert_wav_to_mp3(wav_bytes: bytes, out_path: Path) -> Path:
    """Convert raw WAV audio bytes to MP3 via ffmpeg."""
    tmp_wav = out_path.with_suffix(".tmp.wav")
    tmp_wav.write_bytes(wav_bytes)
    try:
        res = subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_wav), "-vn", "-c:a", "libmp3lame", "-q:a", "2", str(out_path)],
            capture_output=True,
            check=True
        )
        tmp_wav.unlink(missing_ok=True)
        return out_path
    except Exception:
        out_path.write_bytes(wav_bytes)
        tmp_wav.unlink(missing_ok=True)
        return out_path


def synth_dubbed(
    text: str,
    out_path: Path,
    target_lang: str = "en",
    voice_model: str = None
) -> Path:
    """
    Synthesize dubbed speech.
    1. Primary: 9Router AWS Gemini 2.5 Flash TTS
    2. Fallback: Edge-TTS
    """
    lang_info = LANG_PROFILES.get(target_lang, LANG_PROFILES["en"])
    gemini_lang = lang_info["gemini_lang"]
    model = voice_model or lang_info["gemini_voice"]
    
    # 1. Primary: 9Router AWS Gemini TTS
    try:
        payload = json.dumps({
            "model": model,
            "input": text,
            "language": gemini_lang
        }).encode("utf-8")
        req = urllib.request.Request(
            SHELLSHOCK_AWS_BASE + "/v1/audio/speech",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {SHELLSHOCK_AWS_KEY}",
                "Content-Type": "application/json",
            }
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            audio = r.read()
        if len(audio) > 512:
            if audio[:4] == b'RIFF':
                _convert_wav_to_mp3(audio, out_path)
            else:
                out_path.write_bytes(audio)
            return out_path
    except Exception as e:
        print(f"    [dubbing] 9Router Gemini TTS failed ({e}), falling back to Edge-TTS")

    # 2. Fallback: Edge-TTS
    import asyncio
    import edge_tts

    edge_voice = lang_info.get("edge_voice", "en-US-ChristopherNeural")
    async def _edge_synth():
        comm = edge_tts.Communicate(text, voice=edge_voice)
        await comm.save(str(out_path))

    asyncio.run(_edge_synth())
    if not out_path.exists() or out_path.stat().st_size < 512:
        raise RuntimeError("Failed to synthesize dubbed audio across all providers")
    return out_path


def get_background_music() -> Path:
    """Select background music from assets directory."""
    import random
    music_candidates = []
    music_dir = ROOT / "assets" / "music"
    if music_dir.is_dir():
        for ext in ("*.mp3", "*.wav", "*.m4a", "*.ogg"):
            music_candidates.extend(list(music_dir.rglob(ext)))
    if not music_candidates:
        music_candidates = [p for p in (ROOT / "assets").glob("*.mp3") if p.is_file() and p.name != "bg.mp3"]
    return random.choice(music_candidates) if music_candidates else (ROOT / "assets" / "bg.mp3")


def mix_dubbed_audio_track(voice_path: Path, out_path: Path, bg_music: Path = None) -> Path:
    """
    Mixes dubbed voiceover with background music using strictly volume=0.15 for BGM.
    Outputs a standalone mp3 audio track ready for upload into YouTube Studio 'Sulih Suara'.
    """
    bg = bg_music or get_background_music()
    if bg.exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-stream_loop", "-1", "-i", str(bg),
            "-filter_complex", "[0:a]volume=1.0[v];[1:a]volume=0.15[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[a]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(out_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if res.returncode == 0 and out_path.exists():
            return out_path
    
    # If no BGM or mix failed, convert voice directly to high quality mp3
    subprocess.run(["ffmpeg", "-y", "-i", str(voice_path), "-c:a", "libmp3lame", "-b:a", "192k", str(out_path)], capture_output=True)
    return out_path


def create_multi_audio_video(
    clean_video_path: Path,
    primary_audio_path: Path,
    dubbed_audio_path: Path,
    out_path: Path,
    primary_lang: str = "ind",
    dubbed_lang: str = "eng"
) -> Path:
    """
    Embeds both original audio and dubbed audio tracks into an MP4 container with stream metadata:
      Stream 0: Clean Video
      Stream 1: Original Audio (Bahasa Indonesia) [default]
      Stream 2: Dubbed Audio (English / etc.)
    """
    p_label = "Bahasa Indonesia (Asli)"
    d_label = LANG_PROFILES.get(dubbed_lang, {}).get("label", "English (Sulih Suara)")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(clean_video_path),
        "-i", str(primary_audio_path),
        "-i", str(dubbed_audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-map", "2:a",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        f"-metadata:s:a:0", f"language={primary_lang}",
        f"-metadata:s:a:0", f"title={p_label}",
        f"-metadata:s:a:1", f"language={dubbed_lang}",
        f"-metadata:s:a:1", f"title={d_label}",
        "-disposition:a:0", "default",
        "-disposition:a:1", "none",
        "-movflags", "+faststart",
        str(out_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"Failed to create multi-audio video: {res.stderr[-2000:]}")
    return out_path


def process_dubbing(
    work_dir: Path,
    script_data: dict,
    clean_video_path: Path,
    primary_voice_audio: Path,
    target_lang: str = "en",
    voice_model: str = None
) -> dict:
    """
    Full automated pipeline for Sulih Suara (Multi-Language Dubbing):
    1. Translate script segments -> script_dubbed_{lang}.json
    2. Synthesize dubbed voice -> voice_dubbed_{lang}.mp3
    3. Mix dubbed voice with BGM (volume=0.15) -> audio_sulih_suara_{lang}.mp3 (standalone for YT Studio)
    4. Package dual-audio MP4 -> final_multi_audio.mp4
    """
    print(f"    [sulih-suara] 1/4 Translating script to {target_lang.upper()}...")
    translated = translate_script(script_data, target_lang=target_lang)
    trans_json_path = work_dir / f"script_dubbed_{target_lang}.json"
    trans_json_path.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"    [sulih-suara] 2/4 Synthesizing voiceover ({target_lang.upper()}) via 9Router Gemini TTS...")
    raw_dub_path = work_dir / f"voice_dubbed_{target_lang}.mp3"
    synth_dubbed(translated["full_text"], raw_dub_path, target_lang=target_lang, voice_model=voice_model)

    print(f"    [sulih-suara] 3/4 Mixing backsound (volume=0.15) for standalone audio track...")
    audio_track_path = work_dir / f"audio_sulih_suara_{target_lang}.mp3"
    mix_dubbed_audio_track(raw_dub_path, audio_track_path)

    print(f"    [sulih-suara] 4/4 Packaging dual-audio MP4 with language metadata...")
    lang_info = LANG_PROFILES.get(target_lang, LANG_PROFILES["en"])
    iso_code = lang_info.get("iso639_2", "eng")
    multi_audio_path = work_dir / "final_multi_audio.mp4"
    create_multi_audio_video(
        clean_video_path=clean_video_path,
        primary_audio_path=primary_voice_audio,
        dubbed_audio_path=audio_track_path,
        out_path=multi_audio_path,
        primary_lang="ind",
        dubbed_lang=iso_code
    )

    return {
        "target_lang": target_lang,
        "translated_script": translated,
        "script_path": str(trans_json_path),
        "raw_dub_path": str(raw_dub_path),
        "standalone_audio_track": str(audio_track_path),
        "multi_audio_video": str(multi_audio_path)
    }
