import asyncio
import time
from pathlib import Path
import edge_tts
from .config import CONFIG


def synth(text: str, out_path: Path) -> Path:
    v = CONFIG["voice"]
    print(f"    voice: {v['voice']}, {len(text)} chars")

    async def _go():
        com = edge_tts.Communicate(
            text,
            voice=v["voice"],
            rate=v.get("rate", "+0%"),
            pitch=v.get("pitch", "+0Hz"),
        )
        await com.save(str(out_path))

    t0 = time.time()
    asyncio.run(_go())
    print(f"    done in {time.time()-t0:.1f}s")
    return out_path
