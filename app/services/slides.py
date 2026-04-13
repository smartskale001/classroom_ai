import asyncio
import io
import json
import re
import uuid

from pydantic import ValidationError

from app.schemas.language import OutputLanguage
from app.schemas.slides import SlideDeckResponse, SlideItem
from app.services.llm.factory import get_llm_provider
from app.services.llm.types import Message

_lock = asyncio.Lock()
_decks: dict[str, tuple[bytes, str]] = {}


def _lang_rule(lang: OutputLanguage) -> str:
    if lang == "english":
        return "All slide text must be in English."
    if lang == "hindi":
        return "All slide text must be in Hindi (Devanagari script)."
    return "All slide text must be in Roman Hindi (Latin letters only, no Devanagari)."


def _prompt(
    *,
    topic: str,
    slide_count: int,
    output_language: OutputLanguage,
    context_text: str | None,
) -> str:
    ctx = (context_text or "").strip()
    ctx_excerpt = ctx[:26000]
    return (
        "You are an expert teacher preparing a classroom slide deck.\n"
        f"Topic: {topic}\n"
        f"Number of content slides (not counting the opening): {slide_count}\n"
        f"{_lang_rule(output_language)}\n\n"
        "Return JSON only (no markdown). Keys:\n"
        '- deck_title: short presentation title (max 80 characters)\n'
        f"- slides: array of exactly {slide_count} objects. Each object has title (slide heading), "
        "bullets (array of 3 to 6 concise strings), and optional speaker_notes (teacher script).\n\n"
        "Rules:\n"
        "- Bullets must be teaching points, not slide design instructions.\n"
        "- Order slides as you would teach: intro → concepts → examples → summary.\n"
        "- Ground content in the Context when it is provided.\n"
        "- No HTML or markdown in strings.\n"
        + (f"\nContext material:\n{ctx_excerpt}\n" if ctx_excerpt else "")
    )


def _extract_json_obj(raw: str) -> dict | None:
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _normalize_slides(raw_slides: list, *, expected: int, topic: str) -> list[SlideItem]:
    out: list[SlideItem] = []
    for i, item in enumerate(raw_slides[:expected]):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", f"Slide {i + 1}")).strip()[:200]
        bullets_raw = item.get("bullets") or []
        if not isinstance(bullets_raw, list):
            bullets_raw = [str(bullets_raw)]
        bullets = [str(b).strip()[:500] for b in bullets_raw if str(b).strip()][:8]
        if not bullets:
            bullets = [f"Key idea {i + 1} about {topic}."]
        notes = item.get("speaker_notes")
        sn = str(notes).strip()[:4000] if notes else None
        try:
            out.append(SlideItem(title=title or f"Slide {i + 1}", bullets=bullets, speaker_notes=sn))
        except ValidationError:
            continue
    while len(out) < expected:
        n = len(out)
        out.append(
            SlideItem(
                title=f"{topic} — point {n + 1}",
                bullets=[f"Review this section in the chapter.", "Ask students for one example."],
                speaker_notes=None,
            )
        )
    return out[:expected]


def _build_pptx_bytes(*, deck_title: str, topic: str, slides: list[SlideItem]) -> bytes:
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation()
    try:
        prs.core_properties.title = deck_title[:200]
    except Exception:
        pass

    title_layout = prs.slide_layouts[0]
    s0 = prs.slides.add_slide(title_layout)
    s0.shapes.title.text = deck_title[:200]
    try:
        if len(s0.shapes) > 1 and s0.shapes.placeholders[1] is not None:
            s0.shapes.placeholders[1].text = topic[:300]
    except Exception:
        pass

    bullet_layout = prs.slide_layouts[1]
    for item in slides:
        slide = prs.slides.add_slide(bullet_layout)
        slide.shapes.title.text = item.title[:250]
        body = slide.shapes.placeholders[1]
        tf = body.text_frame
        bullets = item.bullets[:8] or ["—"]
        tf.text = bullets[0][:500]
        for b in bullets[1:]:
            p = tf.add_paragraph()
            p.text = b[:500]
            p.level = 0
            try:
                p.font.size = Pt(20)
            except Exception:
                pass
        try:
            tf.paragraphs[0].font.size = Pt(22)
        except Exception:
            pass
        if item.speaker_notes:
            try:
                ns = slide.notes_slide.notes_text_frame
                ns.text = item.speaker_notes[:4000]
            except Exception:
                pass

    bio = io.BytesIO()
    prs.save(bio)
    return bio.getvalue()


def _safe_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "", name).strip()
    s = re.sub(r"\s+", " ", s)[:100]
    return s or "ClassroomAI-slides"


async def generate_slide_deck(
    *,
    topic: str,
    context_text: str | None,
    output_language: OutputLanguage,
    slide_count: int,
    llm_provider: str,
) -> SlideDeckResponse:
    provider = get_llm_provider(vision=False, provider=llm_provider)
    messages: list[Message] = [
        {"role": "system", "content": "You output strict JSON only for slide deck generation."},
        {
            "role": "user",
            "content": _prompt(
                topic=topic,
                slide_count=slide_count,
                output_language=output_language,
                context_text=context_text,
            ),
        },
    ]
    raw = await provider.complete_chat(messages, max_tokens=8000, temperature=0.35)
    data = _extract_json_obj(raw) or {}
    deck_title = str(data.get("deck_title", topic)).strip()[:200] or topic
    raw_slides = data.get("slides")
    if not isinstance(raw_slides, list):
        raw_slides = []
    slides = _normalize_slides(raw_slides, expected=slide_count, topic=topic)

    pptx_bytes = _build_pptx_bytes(deck_title=deck_title, topic=topic, slides=slides)
    deck_id = f"sdeck_{uuid.uuid4().hex[:16]}"
    filename = f"{_safe_filename(deck_title)}.pptx"

    async with _lock:
        _decks[deck_id] = (pptx_bytes, filename)

    return SlideDeckResponse(
        deck_id=deck_id,
        deck_title=deck_title,
        filename=filename,
        slides=slides,
    )


async def get_deck_file(deck_id: str) -> tuple[bytes, str] | None:
    async with _lock:
        return _decks.get(deck_id)
