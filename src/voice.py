import asyncio
import os
import time
from pathlib import Path
import edge_tts
from .config import CONFIG
from elevenlabs.client import ElevenLabs


# ============================================================
# Voice Variety System
# ============================================================

def _get_voice_config() -> dict:
    """Get voice config with variety support."""
    cfg = CONFIG.get("voice", {})
    variety = cfg.get("variety", {})

    if variety.get("enabled", False):
        voices = variety.get("voices", [])
        strategy = variety.get("strategy", "round_robin")

        if voices:
            voice = _select_voice(voices, strategy)
            return {
                **cfg,
                "voice": voice.get("edge_id", cfg.get("voice")),
                "elevenlabs_voice_id": voice.get("elevenlabs_id"),
                "_voice_name": voice.get("name"),
                "_voice_gender": voice.get("gender"),
            }

    return cfg


def _select_voice(voices: list[dict], strategy: str) -> dict:
    """Select voice based on strategy."""
    from . import state

    s = state.load()
    voice_idx = s.get("_voice_idx", 0)

    if strategy == "round_robin":
        selected = voices[voice_idx % len(voices)]
        state.update({"_voice_idx": voice_idx + 1})
    elif strategy == "random":
        import random
        selected = random.choice(voices)
    else:
        selected = voices[voice_idx % len(voices)]
        state.update({"_voice_idx": voice_idx + 1})

    print(f"    voice: selected {selected.get('name', 'unknown')} ({selected.get('gender', '?')})")
    return selected


# ============================================================
# TTS Synthesis
# ============================================================

def _synth_edge(text: str, out_path: Path, v: dict) -> None:
    async def _go():
        com = edge_tts.Communicate(
            text,
            voice=v["voice"],
            rate=v.get("rate", "+0%"),
            pitch=v.get("pitch", "+0Hz"),
        )
        await com.save(str(out_path))
    asyncio.run(_go())


def _synth_elevenlabs(text: str, out_path: Path, v: dict, api_key: str) -> None:
    client = ElevenLabs(api_key=api_key)
    model_id = v.get("elevenlabs_model", "eleven_multilingual_v2")
    audio = client.text_to_speech.convert(
        voice_id=v.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"),
        text=text,
        model_id=model_id,
        output_format="mp3_44100_128",
    )
    with open(out_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)



def _speed_up(audio_path: Path, rate: float = 1.15):
    import subprocess
    tmp = audio_path.with_suffix(".tmp.mp3")
    subprocess.run(["ffmpeg", "-y", "-i", str(audio_path), "-filter:a", f"atempo={rate}", str(tmp)], capture_output=True)
    tmp.replace(audio_path)


def synth(text: str, out_path: Path) -> Path:
    v = _get_voice_config()
    voice_name = v.get("_voice_name", v["voice"])
    print(f"    voice: {voice_name}, {len(text)} chars")

    t0 = time.time()
    provider = CONFIG.get("voice", {}).get("provider", "elevenlabs")

    # ElevenLabs is PRIMARY - try all keys with retry
    if provider == "elevenlabs":
        keys_str = os.environ.get("ELEVENLABS_API_KEYS", "")
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]

        if keys:
            for i, api_key in enumerate(keys):
                for attempt in range(2):
                    try:
                        _synth_elevenlabs(text, out_path, v, api_key)
                        print(f"    done in {time.time()-t0:.1f}s (elevenlabs key[{i}], attempt {attempt+1})")
                        return out_path
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "rate" in err_msg or "limit" in err_msg or "429" in err_msg:
                            print(f"    key[{i}] rate limited (attempt {attempt+1}), trying next")
                            break
                        elif "paid_plan_required" in err_msg or "402" in err_msg:
                            print(f"    key[{i}] needs paid plan, trying next")
                            break
                        else:
                            print(f"    key[{i}] error (attempt {attempt+1}): {e}")
                            if attempt == 0:
                                import time as _time
                                _time.sleep(1)
                            continue
            print(f"    all {len(keys)} elevenlabs keys exhausted")
        else:
            print(f"    no elevenlabs keys found")

    # Edge-TTS is LAST RESORT fallback only
    print(f"    falling back to edge-tts (last resort)")
    _synth_edge(text, out_path, v)
    print(f"    done in {time.time()-t0:.1f}s (edge-tts fallback)")
    return out_path
