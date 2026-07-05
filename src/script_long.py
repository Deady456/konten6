import json, re, time
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER, CONFIG

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

def generate():
    s = CONFIG["script"]
    lang = CONFIG.get("language", "en")
    ts = s["target_seconds"]
    target_words = int(ts * s["words_per_second"])
    sections = max(5, ts // 60)

    if lang == "id":
        system_prompt = f"""Anda adalah penulis naskah video dokumenter YouTube.

Aturan:
- Buat naskah video dokumenter {ts} detik, ~{target_words} kata, dibagi {sections} segmen.
- Gaya bahasa Indonesia formal-informatif, seperti narator dokumenter Discovery/National Geographic.
- Setiap segmen punya:
  - "title": judul singkat segmen (untuk prompt gambar, dalam Bahasa Inggris)
  - "text": narasi 30-60 detik
  - "image_prompt": deskripsi visual Bahasa Inggris untuk generate gambar (deskriptif, 1-2 kalimat)
- Mulai dengan hook kuat yang bikin penasaran.
- Akhiri dengan kesimpulan yang memuaskan.
- Jangan pakai emoji, format khusus, atau seruan subscribe di tengah.

Kembalikan ONLY valid JSON dengan skema berikut:
{{"title": "Judul video max 95 chars, minimal 40 karakter, bikin penasaran dan engaging", "description": "3-4 kalimat deskripsi menarik dengan 5-8 hashtag relevan", "tags": ["10-15 tag huruf kecil yang relevan"], "segments": [{{"title": "...", "text": "...", "image_prompt": "..."}}]}}"""
    else:
        system_prompt = f"""You write YouTube documentary scripts.

Rules:
- Write a {ts}-second documentary script, ~{target_words} words, divided into {sections} segments.
- Educational, engaging, narrative style.
- Each segment has:
  - "title": short title (for image prompt)
  - "text": 30-60 second narration
  - "image_prompt": visual description in English (1-2 sentences)
- Start with a strong hook.
- End with a satisfying conclusion.
- No emojis, no subscription prompts in the middle.

Return ONLY valid JSON with this schema:
{{"title": "title max 95 chars, min 40 chars, curiosity-driven and engaging", "description": "3-4 sentences with 5-8 relevant hashtags", "tags": ["10-15 lowercase relevant tags"], "segments": [{{"title": "...", "text": "...", "image_prompt": "..."}}]}}"""

    user_msg = (
        f"Niche: {CONFIG['niche']}\n"
        f"Audience: {CONFIG['audience']}\n"
        f"Buat SATU naskah dokumenter."
    )

    print(f"    calling {LLM_PROVIDER}/{LLM_MODEL}...")
    t0 = time.time()
    resp = _call_llm(
        model=LLM_MODEL,
        max_tokens=8000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = resp.choices[0].message.content
    print(f"    LLM responded in {time.time()-t0:.1f}s ({len(raw)} chars)")

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    result = json.loads(text)

    segments = result.get("segments", result if isinstance(result, list) else [])[:sections]
    title = result.get("title", segments[0]["title"]) if isinstance(result, dict) else segments[0]["title"]
    description = result.get("description", CONFIG.get("description", "")) if isinstance(result, dict) else ""
    tags = result.get("tags", CONFIG["upload"]["default_tags"]) if isinstance(result, dict) else CONFIG["upload"]["default_tags"]

    full_text = " ... ".join(s["text"] for s in segments)
    return {"segments": segments, "full_text": full_text, "title": title, "description": description, "tags": tags}
