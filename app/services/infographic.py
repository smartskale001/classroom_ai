import json
import re

from app.core.config import get_settings
from app.schemas.language import OutputLanguage, normalize_output_language
from app.services import illustration_openai, illustration_opensource
from app.services.llm.factory import get_llm_provider
from app.services.llm.types import Message


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


def _lang_note(lang: OutputLanguage) -> str:
    if lang == "english":
        return "Concept labels in the scene should be implied by icons only; image must contain NO readable text."
    if lang == "hindi":
        return "The topic is taught in Hindi; use culturally neutral school visuals, NO Devanagari text in the image."
    return "Roman Hindi context; use neutral visuals, NO letters or words in the image."


def _prompt_llm(*, topic: str, context_text: str | None, output_language: OutputLanguage) -> str:
    ctx = (context_text or "").strip()[:12000]
    return (
        "You write ONE concise image-generation prompt for an educational INFOGRAPHIC (diagram poster).\n"
        f"Topic: {topic}\n"
        f"{_lang_note(output_language)}\n"
        "Describe layout: sections, flow, icons, simple charts, arrows, color regions. "
        "No longer than 600 characters in the prompt field.\n"
        'Return JSON only: {"visual_prompt": "<single English prompt for the image model>"}\n'
        + (f"\nLesson context to reflect:\n{ctx}\n" if ctx else "")
    )


async def generate_infographic(
    *,
    topic: str,
    context_text: str | None,
    output_language: str,
    stack: str,
    style: str,
) -> tuple[str, str, str]:
    settings = get_settings()
    lang = normalize_output_language(output_language)
    llm_provider = "openai" if stack.lower().strip() == "openai" else "ollama"
    provider = get_llm_provider(vision=False, provider=llm_provider)
    messages: list[Message] = [
        {"role": "system", "content": "You output strict JSON only."},
        {"role": "user", "content": _prompt_llm(topic=topic, context_text=context_text, output_language=lang)},
    ]
    raw = await provider.complete_chat(messages, max_tokens=1200, temperature=0.4)
    data = _extract_json_obj(raw) or {}
    vp = str(data.get("visual_prompt") or data.get("prompt") or "").strip()
    if len(vp) < 20:
        vp = (
            f"Educational infographic poster about {topic}: clear sections, flowchart arrows, "
            f"icons for key concepts, color-coded blocks, minimal style, no text."
        )
    vp = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", vp)[:3500]

    full_prompt = (
        f"Professional educational infographic, 1024x1024, readable layout: {vp}. "
        f"Vertical or grid layout, vector-like clarity, school-friendly."
    )
    style_suffix = (style or "").strip() or (
        "flat vector infographic, bold shapes, no text, no watermark, crisp edges"
    )

    if stack.lower().strip() == "opensource":
        b64, mime = await illustration_opensource.generate_illustration_png_b64(
            settings,
            prompt=full_prompt,
            style_suffix=style_suffix,
        )
    else:
        b64, mime = await illustration_openai.generate_illustration_png_b64(
            settings,
            prompt=full_prompt,
            style_suffix=style_suffix,
        )
    return b64, mime, full_prompt[:2000]
