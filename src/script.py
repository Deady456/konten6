import json
import re
import time
from datetime import datetime
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER, CONFIG
from . import state

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def _call_llm(model, max_tokens, response_format, messages, retries=5):
    for attempt in range(retries):
        try:
            return client.chat.completions.create(
                model=model, max_tokens=max_tokens,
                response_format=response_format, messages=messages,
            )
        except Exception as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  LLM error (retry {attempt+1}/{retries} in {wait}s): {e}")
                time.sleep(wait)
            else:
                raise

def _system_prompt():
    s = CONFIG["script"]
    lang = CONFIG.get("language", "en")
    target_words = int(s["target_seconds"] * s["words_per_second"])

    if lang == "id":
        ts, tw = s["target_seconds"], target_words
        return f"""Anda adalah penulis skrip YouTube Shorts.

Aturan:
- Skrip harus {ts} detik, ~{tw} kata total ({tw//ts} kata per detik).
- Mulai dengan HOOK 1 kalimat yang bikin penasaran dalam <3 detik, gaya semi-formal. Jangan pakai "Halo guys", "Hai", atau perkenalan.
- Isi: informasi relevan sesuai niche yang diminta. Berikan fakta, angka, data, atau berita terbaru yang akurat.
- Akhiri dengan CTA 1 kalimat semi-formal ajakan subscribe/ikuti.
- Gunakan bahasa Indonesia semi-formal: rapi dan informatif, tapi tetap enak didengar. Hindari bahasa terlalu santai atau terlalu kaku. Jangan pakai emoji atau format khusus.
- Setiap scene punya visual_query 2-4 kata benda bahasa Inggris untuk cari video stok di Pexels yang relevan dengan niche.

Kembalikan ONLY valid JSON, tanpa teks lain. Skema:
{{"topic": "slug topik sesuai niche", "title": "Judul YouTube max 95 chars, minimal 40 karakter, bikin penasaran dan engaging, jangan terlalu pendek", "description": "3-4 kalimat deskripsi menarik dengan 5-8 hashtag relevan", "tags": ["10-15 tag huruf kecil yang relevan"], "scenes": [{{"text": "kalimat narasi bahasa Indonesia", "visual_query": "2-4 kata benda Inggris"}}]}}"""
    else:
        return f"""You write viral YouTube Shorts scripts for a faceless educational facts channel.

Hard rules:
- The script must run ~{target_seconds} seconds spoken at ~{target_words} words total.
- Start with a strong 1-sentence HOOK that creates curiosity in <3 seconds.
- Body: 4-6 surprising, accurate, verifiable facts.
- End with a 1-sentence CTA.
- Plain spoken English. No emojis.
- Each scene's visual_query is 2-4 English nouns (e.g. "octopus swimming ocean").

Return ONLY valid JSON. Schema:
{{"topic": "short slug", "title": "title max 95 chars, min 40 chars, curiosity-driven and engaging", "description": "3-4 sentences with 5-8 relevant hashtags", "tags": ["10-15 lowercase relevant tags"], "scenes": [{{"text": "spoken sentence", "visual_query": "nouns"}}]}}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}")
        print(f"    Raw response (first 500 chars): {text[:500]}")
        raise


def generate():
    lang = CONFIG.get("language", "en")

    if lang == "id":
        user_msg = (
            f"Niche: {CONFIG['niche']}\n"
            f"Audience: {CONFIG['audience']}\n"
            f"Buat SATU Short baru."
        )
    else:
        user_msg = (
            f"Niche: {CONFIG['niche']}\n"
            f"Audience: {CONFIG['audience']}\n"
            f"Generate ONE fresh Short."
        )

    print(f"    calling {LLM_PROVIDER}/{LLM_MODEL}...")
    t0 = time.time()
    resp = _call_llm(
        model=LLM_MODEL,
        max_tokens=2000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = resp.choices[0].message.content
    print(f"    LLM responded in {time.time()-t0:.1f}s ({len(raw)} chars)")
    data = _extract_json(raw)

    # Validate each scene has visual_query
    for i, s in enumerate(data["scenes"]):
        if "visual_query" not in s or not s["visual_query"]:
            words = re.findall(r"[a-zA-Z]{3,}", s.get("text", ""))
            fallback = " ".join(words[-3:]) if len(words) >= 3 else "abstract background"
            print(f"    scene {i}: missing visual_query, using \"{fallback}\"")
            s["visual_query"] = fallback

    data["full_text"] = " ... ".join(s["text"] for s in data["scenes"])
    return data
