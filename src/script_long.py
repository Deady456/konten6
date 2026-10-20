import json, re, time
from openai import OpenAI, RateLimitError
from .config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER,
    FALLBACK_API_KEY, FALLBACK_BASE_URL, FALLBACK_MODEL,
    GROQ_API_KEYS, GROQ_BASE_URL,
    CONFIG,
)
from . import state


def _call_llm(api_key, base_url, model, max_tokens, response_format, messages, retries=5, extra_keys=None):
    clients = [OpenAI(api_key=api_key, base_url=base_url)]
    if extra_keys:
        for k in extra_keys:
            clients.append(OpenAI(api_key=k, base_url=base_url))

    for attempt in range(retries):
        for key_idx, client in enumerate(clients):
            try:
                return client.chat.completions.create(
                    model=model, max_tokens=max_tokens,
                    response_format=response_format, messages=messages,
                )
            except RateLimitError:
                if key_idx < len(clients) - 1:
                    print(f"  Key {key_idx+1} rate limited, trying next key")
                    continue
                print(f"  All keys rate limited. Retry {attempt+1}/{retries}...")
                wait = 2 ** attempt
                time.sleep(wait)
                break
            except Exception as e:
                if "413" in str(e) or "Request too large" in str(e):
                    print(f"  Request too large ({max_tokens} max), halving to {max_tokens//2}")
                    max_tokens = max_tokens // 2
                    if max_tokens < 500:
                        raise
                    time.sleep(1)
                    break
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    print(f"  LLM error (retry {attempt+1}/{retries} in {wait}s): {e}")
                    time.sleep(wait)
                    break
                raise
    raise RuntimeError(f"LLM call failed after {retries} attempts across {len(clients)} keys")


def generate():
    s = CONFIG["script"]
    lang = CONFIG.get("language", "en")
    ts = s.get("target_seconds_long", 480) # Default 8 menit (480 detik) untuk syarat monetisasi & mid-roll ads
    target_words = int(ts * s.get("words_per_second", 2.5))
    sections = max(8, ts // 40)

    if lang == "id":
        system_prompt = f"""Anda adalah kepala penulis naskah video dokumenter edukasi mendalam (Long-Form) YouTube untuk channel 'Reka Kuno' (gaya visual storytelling komik/diagram cutaway arsitektur kuno seperti channel ROVO).

Cakupan Niche Luas (WAJIB ROTASI antar peradaban dunia, DILARANG hanya berputar di Mesir):
1. Rekayasa Arsitektur & Teknologi Fisika Kuno:
   - Persia Kuno: Yakhchal (kulkas es raksasa di padang pasir tanpa listrik), Qanat (saluran air bawah tanah ratusan km), Badgir (menara penangkap angin).
   - Romawi Kuno: Beton Opus Caementicium yang mengeras di air laut ribuan tahun, sistem pemanas lantai Hypocaust, jembatan air Aqueduct presisi gravitasi, kubah beton Pantheon.
   - Tiongkok Dinasti: Sambungan kayu tanpa paku tahan gempa (Dougong), adukan bubur ketan Tembok Besar, irigasi Dujiangyan yang beroperasi 2200 tahun tanpa bendungan.
   - Suku Maya & Inka: Pemotongan batu poligon presisi tanpa semen di Saksaywaman/Machu Picchu, akustik gema burung kuil Kukulkan Chichen Itza.
   - Turki (Anatolia): Kota bawah tanah bertingkat 18 di Derinkuyu & cerobong ventilasi vertikal alami.
   - India Kuno: Kuil Kailasa (dipahat dari satu bukit batu utuh dari atas ke bawah), jembatan akar pohon hidup Meghalaya, kuil Brihadisvara.
   - Yunani Kuno: Komputer analog tertua di dunia Mekanisme Antikythera, mercusuar Alexandria, jam air Clepsydra.
   - Mesir Kuno: Kanal Nil, dinamika luncuran batu piramida.
2. Trik Bertahan Hidup & Sains Manusia Prasejarah:
   - Bagaimana orang kuno mengawetkan makanan berbulan-bulan tanpa kulkas (garam, fermentasi bawah tanah, guci minyak).
   - Bagaimana tentara kuno menyaring air bersih di padang tandus.
   - Bagaimana nenek moyang zaman es bertahan hidup dari dingin mematikan sebelum ada pemanas modern.
   - Teknik medis kuno: jahitan luka semut tentara, trepanasi kepala yang sembuh, perban madu dan herba alami.
3. Asal-Usul Kebiasaan & Perkakas Manusia (Antropologi & Fakta Mengejutkan):
   - Apa yang dilakukan manusia purba seharian sebelum ada pekerjaan dan jam kantor?
   - Bagaimana manusia pertama kali menemukan garam dan cara mengekstraknya?
   - Bagaimana manusia pertama kali menemukan cara memancing ikan dan membuat perahu?
   - Mengapa manusia di seluruh benua terobsesi dengan emas?
   - Bagaimana manusia purba menyalakan api dan menjaganya tidak padam berminggu-minggu?

Struktur Video ({ts} detik, ~{target_words} kata, dibagi {sections} segmen narasi):
1. Segmen 1 (Hook Misteri & Paradoks): Pertanyaan provokatif yang membongkar anggapan umum tentang keterbelakangan orang kuno.
2. Segmen 2-3 (Kondisi Ekstrem & Tantangan Nyata): Penjelasan lingkungan ekstrem yang dihadapi (suhu 50 derajat, ancaman gempa, air asin, banjir tahunan).
3. Segmen 4-6 (Anatomi & Rekayasa Arsitektur): Bedah denah, potongan melintang (cutaway), material bahan (bata lumpur, kapur tohor, abu vulkanik pozzolana, saluran bawah tanah), dan desain cerobong.
4. Segmen 7-9 (Prinsip Sains & Fisika Alami): Hukum termodinamika alami, pendinginan evaporatif, massa termal, gravitasi hidrolika, dan konveksi udara.
5. Segmen Penutup: Hubungan dengan dunia modern & kesimpulan memukau, diakhiri ajakan subscribe ke Reka Kuno.

Aturan Penting:
- DILARANG menggunakan angka digit/numerik (1, 2, 50, 100, 2000). SEMUA ANGKA WAJIB DITULIS LENGKAP DALAM KATA BAHASA INDONESIA (misal: "lima puluh", "dua ribu tahun", "tiga ratus").
- Bahasa Indonesia yang renyah, imersif, seperti bercerita di depan api unggun, tidak kaku, dan mudah dimengerti.
- Setiap segmen WAJIB memiliki:
  - "title": Judul topik segmen (Bahasa Inggris singkat)
  - "text": Naskah narasi segmen (30-50 kata, Bahasa Indonesia)
  - "image_prompt": Prompt visual 100% BAHASA INGGRIS untuk AI Image Generator (FLUX/Gemini). WAJIB bergaya: "2D cartoon architectural cutaway, comic diagram style, bold clean vector outlines, warm atmospheric lighting, expressive cartoon characters, vibrant colors, clear educational infographic, cross-section blueprint, no realistic photograph".

Kembalikan ONLY valid JSON dengan skema:
{{"title": "Judul video max 95 chars, minimal 40 karakter, berupa pertanyaan misteri sejarah/arsitektur yang bikin penasaran", "thumbnail_text": "Teks super pendek (3-5 kata, ALL CAPS) untuk teks thumbnail YouTube", "description": "3-4 paragraf rangkuman dokumenter dengan 6-8 hashtag relevan", "tags": ["10-15 tag huruf kecil relevan"], "segments": [{{"title": "...", "text": "...", "image_prompt": "..."}}]}}"""
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
{{"title": "title max 95 chars, min 40 chars, curiosity-driven and engaging", "thumbnail_text": "Super short hook text (3-5 words, ALL CAPS) for YouTube thumbnail", "description": "3-4 sentences with 5-8 relevant hashtags", "tags": ["10-15 lowercase relevant tags"], "segments": [{{"title": "...", "text": "...", "image_prompt": "..."}}]}}"""

    s = state.load()
    used = s.get("used_topics", [])
    used_str = ", ".join(used[-30:]) if used else "(none yet)"

    user_msg = (
        f"Niche: {CONFIG['niche']}\n"
        f"Audience: {CONFIG['audience']}\n"
        f"Topik yang sudah pernah dibuat: {used_str}\n"
        f"Buat SATU naskah dokumenter dengan topik yang BENAR-BENAR BARU. DILARANG menggunakan topik yang sudah pernah dibuat. Judul dan isi harus orisinal dan tidak mirip dengan yang sudah ada."
    )

    providers = [
        (LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL),
    ]
    if LLM_PROVIDER != "groq" and FALLBACK_API_KEY:
        providers.append(("groq", FALLBACK_API_KEY, FALLBACK_BASE_URL, FALLBACK_MODEL))

    raw = None
    last_err = None
    for prov_name, api_key, base_url, model in providers:
        extra = []
        if prov_name == "groq":
            extra = [k for k in GROQ_API_KEYS if k != api_key]
        print(f"    calling {prov_name}/{model}...")
        t0 = time.time()
        try:
            resp = _call_llm(
                api_key=api_key, base_url=base_url,
                model=model,
                max_tokens=8000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                extra_keys=extra,
            )
            raw = resp.choices[0].message.content
            print(f"    {prov_name} responded in {time.time()-t0:.1f}s ({len(raw)} chars)")
            break
        except Exception as e:
            last_err = e
            print(f"    {prov_name} failed: {e}")
    if raw is None:
        raise last_err or RuntimeError("All LLM providers failed")

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    result = json.loads(text)
    segments = result.get("segments", result if isinstance(result, list) else [])[:sections]
    title = result.get("title", segments[0]["title"]) if isinstance(result, dict) else segments[0]["title"]
    description = result.get("description", CONFIG.get("description", "")) if isinstance(result, dict) else ""
    tags = result.get("tags", CONFIG["upload"]["default_tags"]) if isinstance(result, dict) else CONFIG["upload"]["default_tags"]
    thumbnail_text = result.get("thumbnail_text", "") if isinstance(result, dict) else ""

    from .script import replace_numbers_id
    for s in segments:
        s["text"] = replace_numbers_id(s.get("text", ""))

    full_text = " ... ".join(s["text"] for s in segments)
    return {
        "segments": segments,
        "full_text": full_text,
        "title": title,
        "description": description,
        "tags": tags,
        "thumbnail_text": thumbnail_text,
    }
