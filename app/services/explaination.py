# app/services/llm/explain.py
import base64
import json
import re

from pydantic import ValidationError

from app.schemas.explain import ExplainResponse, VisualAssetBrief
from app.schemas.language import OutputLanguage, normalize_output_language
from app.services.llm.factory import get_llm_provider
from app.services.llm.types import ImageUrlPart, Message, TextPart
from app.services.pdf_extract import extract_pdf_to_text


# ═══════════════════════════════════════════════════════════════════════════════
# NEW ── Language auto-detection from free text / topic_hint
# ═══════════════════════════════════════════════════════════════════════════════

# Maps trigger phrases (lowercase) → OutputLanguage
# Kept as a plain dict so it's easy to extend without touching any logic.
_LANG_TRIGGER_PHRASES: dict[str, OutputLanguage] = {
    # Telugu
    "in telugu": "telugu",
    "telugu lo": "telugu",
    "telugu లో": "telugu",
    # Tamil
    "in tamil": "tamil",
    "tamil il": "tamil",
    # Gujarati
    "in gujarati": "gujarati",
    "gujarati ma": "gujarati",
    "gujarati માં": "gujarati",
    # Marathi
    "in marathi": "marathi",
    "marathi madhe": "marathi",
    # Bengali
    "in bengali": "bengali",
    "in bangla": "bengali",
    "banglay": "bengali",
    # Kannada
    "in kannada": "kannada",
    "kannada alli": "kannada",
    # Malayalam
    "in malayalam": "malayalam",
    "malayalam il": "malayalam",
    # Punjabi
    "in punjabi": "punjabi",
    "punjabi vich": "punjabi",
    # Urdu
    "in urdu": "urdu",
    "urdu mein": "urdu",
    # Hindi
    "in hindi": "hindi",
    "hindi mein": "hindi",
    "hindi me": "hindi",
    # Roman Hindi
    "in roman hindi": "roman_hindi",
    "in hinglish": "roman_hindi",
    # English (explicit override)
    "in english": "english",
}


def detect_language_from_text(
    chapter_text: str,
    topic_hint: str | None,
) -> OutputLanguage | None:
    """
    NEW FEATURE — Scan chapter_text and topic_hint for natural language phrases
    like 'explain in Telugu' or 'hindi mein samjhao'.

    Returns the detected OutputLanguage, or None if nothing found.
    The endpoint calls this BEFORE falling back to the explicit output_language param,
    so mentioning language in the prompt always wins.

    To add a new trigger phrase: just add a key→value to _LANG_TRIGGER_PHRASES above.
    """
    combined = " ".join(filter(None, [chapter_text, topic_hint])).lower()
    for phrase, lang in _LANG_TRIGGER_PHRASES.items():
        if phrase in combined:
            return lang
    return None


def resolve_output_language(
    explicit_language: OutputLanguage,
    chapter_text: str,
    topic_hint: str | None,
) -> tuple[OutputLanguage, str | None]:
    """
    NEW FEATURE — Combine explicit param + auto-detection.

    Priority:
      1. Language detected from text/topic_hint  (highest — user said it in plain words)
      2. Explicit output_language param           (set by UI dropdown / API caller)
      3. Default: 'english'

    Returns:
      (resolved_language, detected_language_or_None)
      The second value is echoed in ExplainResponse.detected_language_from_prompt.
    """
    detected = detect_language_from_text(chapter_text, topic_hint)
    if detected:
        return detected, detected
    return explicit_language, None


# ═══════════════════════════════════════════════════════════════════════════════
# NEW ── Per-language instruction blocks
# ═══════════════════════════════════════════════════════════════════════════════

# All language-specific LLM instructions live here in one place.
# To add a language: add a key to _LANG_INSTRUCTIONS and update language.py.
_LANG_INSTRUCTIONS: dict[OutputLanguage, str] = {
    "english": (
        "OUTPUT_LANGUAGE=english. All learner-facing strings must be in English."
    ),
    "hindi": (
        "OUTPUT_LANGUAGE=hindi (Devanagari). All learner-facing strings — "
        "explanation_markdown, simple_examples, visual_brief title/description, "
        "suggested_followup_topics, video_lesson_prompt — MUST be in Hindi using "
        "देवनागरी script. Do not use Roman/Latin letters for Hindi words. "
        "Translate from the chapter if it is in English."
    ),
    "roman_hindi": (
        "OUTPUT_LANGUAGE=roman_hindi (Hindi in Latin letters only). "
        "All learner-facing strings — explanation_markdown, simple_examples, "
        "visual_brief title/description, suggested_followup_topics, video_lesson_prompt — "
        "MUST be Hindi written with A–Z letters only "
        "(e.g. \"Prakash ki paravartan\", \"Darpan par padne wala kon\"). "
        "Do NOT use Devanagari (no Hindi script). "
        "JSON keys stay English; enum tokens kind/suggested_format stay as specified. "
        "Mermaid labels: Roman Hindi or very short English. "
        "Translate the teaching from the chapter even if the chapter is English."
    ),
    "telugu": (
        "OUTPUT_LANGUAGE=telugu. All learner-facing strings MUST be in Telugu script (తెలుగు). "
        "Use proper Telugu script for all explanations, examples, topics, and captions. "
        "Do not mix in English words unless they are proper nouns with no Telugu equivalent. "
        "Translate fully from the chapter even if it is in English."
    ),
    "tamil": (
        "OUTPUT_LANGUAGE=tamil. All learner-facing strings MUST be in Tamil script (தமிழ்). "
        "Use proper Tamil script for all explanations, examples, topics, and captions. "
        "Translate fully from the chapter even if it is in English."
    ),
    "gujarati": (
        "OUTPUT_LANGUAGE=gujarati. All learner-facing strings MUST be in Gujarati script (ગુજરાતી). "
        "Use proper Gujarati script for all explanations, examples, topics, and captions. "
        "Translate fully from the chapter even if it is in English."
    ),
    "marathi": (
        "OUTPUT_LANGUAGE=marathi. All learner-facing strings MUST be in Marathi (मराठी) "
        "using Devanagari script. "
        "Translate fully from the chapter even if it is in English."
    ),
    "bengali": (
        "OUTPUT_LANGUAGE=bengali. All learner-facing strings MUST be in Bengali script (বাংলা). "
        "Use proper Bengali script for all explanations, examples, topics, and captions. "
        "Translate fully from the chapter even if it is in English."
    ),
    "kannada": (
        "OUTPUT_LANGUAGE=kannada. All learner-facing strings MUST be in Kannada script (ಕನ್ನಡ). "
        "Use proper Kannada script for all explanations, examples, topics, and captions. "
        "Translate fully from the chapter even if it is in English."
    ),
    "malayalam": (
        "OUTPUT_LANGUAGE=malayalam. All learner-facing strings MUST be in Malayalam script (മലയാളം). "
        "Use proper Malayalam script for all explanations, examples, topics, and captions. "
        "Translate fully from the chapter even if it is in English."
    ),
    "punjabi": (
        "OUTPUT_LANGUAGE=punjabi. All learner-facing strings MUST be in Punjabi/Gurmukhi "
        "script (ਪੰਜਾਬੀ). "
        "Use proper Gurmukhi script for all explanations, examples, topics, and captions. "
        "Translate fully from the chapter even if it is in English."
    ),
    "urdu": (
        "OUTPUT_LANGUAGE=urdu. All learner-facing strings MUST be in Urdu script (اردو). "
        "Write right-to-left in Nastaliq style. "
        "Translate fully from the chapter even if it is in English."
    ),
}

_SCRIPT_LABEL: dict[OutputLanguage, str] = {
    "english":     "English only",
    "hindi":       "Hindi in Devanagari script only (देवनागरी)",
    "roman_hindi": "Roman Hindi only (Hindi in Latin alphabet, no Devanagari)",
    "telugu":      "Telugu script only (తెలుగు)",
    "tamil":       "Tamil script only (தமிழ்)",
    "gujarati":    "Gujarati script only (ગુજરાતી)",
    "marathi":     "Marathi in Devanagari script (मराठी)",
    "bengali":     "Bengali script only (বাংলা)",
    "kannada":     "Kannada script only (ಕನ್ನಡ)",
    "malayalam":   "Malayalam script only (മലയാളം)",
    "punjabi":     "Punjabi in Gurmukhi script only (ਪੰਜਾਬੀ)",
    "urdu":        "Urdu script only (اردو)",
}


def _user_language_block(output_language: OutputLanguage, *, closing: bool = False) -> str:
    """
    Build the per-message language instruction block injected into every LLM call.
    Uses _LANG_INSTRUCTIONS — add new languages there, not here.
    """
    line = _LANG_INSTRUCTIONS.get(
        output_language,
        f"OUTPUT_LANGUAGE={output_language}. All learner-facing strings must be in {output_language}.",
    )
    tag = "FINAL CHECK — " if closing else ""
    return f"{tag}{line}\n\n"


# ═══════════════════════════════════════════════════════════════════════════════
# (unchanged) JSON contract + system prompt
# ═══════════════════════════════════════════════════════════════════════════════

_JSON_CONTRACT = """
Return a single JSON object only (no markdown code fences).
You MUST use the exact key names below. Do not return only book metadata (title, author, publisher, text)
as a substitute — the full lesson must live in explanation_markdown with the other required keys.
Keys (keep these key names in English): explanation_markdown (string), simple_examples (array of strings),
visual_briefs (array of {title, description, kind, suggested_format}),
suggested_followup_topics (array of strings), video_lesson_prompt (string or null), mermaid_diagram (string or null),
diagram_caption (string or null).

Rules:
- explanation_markdown: Must be clear, textbook-style Markdown in OUTPUT_LANGUAGE only. Use this structure (headings in OUTPUT_LANGUAGE):
  * One ## title line for the lesson topic.
  * ### sections in order (skip any that do not apply): Main ideas; Step-by-step (or reasoning); Real-life / numerical examples; Key terms; Quick recap.
  * Use **bold** for important terms, short bullet lists where helpful, short paragraphs (3–6 sentences).
  * Do NOT wrap the whole explanation in a single code block. No English mixed in when OUTPUT_LANGUAGE is hindi or roman_hindi.
- simple_examples: At least 3 items. Each string is ONE concrete example: include numbers/units when the topic allows, or a specific everyday situation (e.g. "If distance is 2 m and …"). Avoid vague one-liners like "study hard".
- kind must be one of: diagram, analogy_illustration, timeline, graph_concept, animation_idea, other.
- suggested_format must be one of: mermaid, animation_storyboard, svg_or_image.
- Put at least 2 items in visual_briefs; use full sentences in title and description.
- mermaid_diagram: valid Mermaid v10+ syntax only, or null. Prefer flowchart TD or graph LR. First line MUST be the diagram keyword (no title line before it). Use ASCII-only node IDs (A, B, C, …). Put ALL label text in double quotes: A["Light source"] --> B["Mirror"]. Use --> for links. Avoid raw parentheses inside unquoted brackets. Do NOT put a second copy of the diagram inside explanation_markdown fenced blocks — only here in mermaid_diagram. Newlines in JSON must be escaped as \\n.
- diagram_caption: If mermaid_diagram is non-null, add 1–3 sentences in OUTPUT_LANGUAGE explaining what the diagram shows (a legend: parts, arrows, or how to read it). If no diagram, use null.

LANGUAGE: Every string that students will read MUST follow OUTPUT_LANGUAGE from the messages above — not English unless OUTPUT_LANGUAGE is english.
"""


def _system_prompt(output_language: OutputLanguage, topic_hint: str | None) -> str:
    focus = f" Focus the explanation on: {topic_hint}." if topic_hint else ""
    lang = f"Learner-facing text: {_SCRIPT_LABEL.get(output_language, output_language)} only."
    return (
        "You are an expert school teacher. Simplify the chapter for students using clear structure, "
        "realistic examples, and language that matches OUTPUT_LANGUAGE exactly.\n"
        f"{lang}{focus}\n"
        "Include at least two visual_briefs: one animation_storyboard and one mermaid when possible.\n"
        + _JSON_CONTRACT
    )


# ═══════════════════════════════════════════════════════════════════════════════
# (unchanged) Mermaid sanitization helpers
# ═══════════════════════════════════════════════════════════════════════════════

_MERMAID_HEADER = re.compile(
    r"^\s*(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|"
    r"gantt|pie|journey|mindmap|timeline|quadrantChart|block-beta|packet-beta)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_mermaid_fences(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    s = re.sub(r"^```mermaid\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^```\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip() or None


def _sanitize_mermaid_diagram(raw: str | None) -> str | None:
    md = _strip_mermaid_fences(raw)
    if not md:
        return None
    if "\\n" in md and "\n" not in md:
        md = md.replace("\\n", "\n")
    lines = md.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if _MERMAID_HEADER.match(line):
            start = i
            break
    else:
        body = "\n".join(ln.strip() for ln in lines if ln.strip())
        if not body:
            return None
        return f"flowchart TD\n{body}"
    diagram = "\n".join(lines[start:]).strip()
    if not diagram:
        return None
    diagram = (
        diagram.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u200b", "")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    return diagram


# ═══════════════════════════════════════════════════════════════════════════════
# (unchanged) JSON parsing + coercion helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_response_json_fences(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _extract_json_object(raw: str) -> dict | None:
    s = _strip_response_json_fences(raw)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start : i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


_ALLOWED_KIND = frozenset(
    {"diagram", "analogy_illustration", "timeline", "graph_concept", "animation_idea", "other"}
)
_ALLOWED_FORMAT = frozenset({"mermaid", "animation_storyboard", "svg_or_image"})


def _normalize_simple_examples(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    out = [str(x).strip() for x in items if x is not None and str(x).strip()]
    return out[:24] if out else []


def _normalize_visual_briefs(items: object) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "Visual")).strip() or "Visual"
        desc = str(item.get("description", "")).strip() or "See chapter."
        k = str(item.get("kind", "other")).lower()
        if k not in _ALLOWED_KIND:
            k = "other"
        f = str(item.get("suggested_format", "svg_or_image")).lower()
        if f not in _ALLOWED_FORMAT:
            f = "svg_or_image"
        out.append(
            {"title": title[:400], "description": desc[:4000], "kind": k, "suggested_format": f}
        )
    return out


def _coerce_explain_dict(data: dict) -> dict:
    d = dict(data)
    em = d.get("explanation_markdown")
    if not isinstance(em, str) or not em.strip():
        pieces: list[str] = []
        if isinstance(d.get("title"), str) and d["title"].strip():
            pieces.append(f"## {d['title'].strip()}")
        for key in ("text", "content", "body", "abstract", "summary", "description"):
            val = d.get(key)
            if isinstance(val, str) and val.strip():
                pieces.append(val.strip())
                break
        if pieces:
            d["explanation_markdown"] = "\n\n".join(pieces)
    ex = _normalize_simple_examples(d.get("simple_examples"))
    if len(ex) < 1:
        ex = [
            "State the main idea from the chapter in one sentence.",
            "Give a concrete example that uses one quantity or object from the reading.",
            "Connect one vocabulary term to the rest of the lesson.",
        ]
    d["simple_examples"] = ex
    vb = _normalize_visual_briefs(d.get("visual_briefs"))
    if len(vb) < 1:
        vb = [
            {
                "title": "Main concept diagram",
                "description": "A diagram linking the central ideas from the chapter for quick review.",
                "kind": "diagram",
                "suggested_format": "mermaid",
            },
            {
                "title": "Process or storyboard",
                "description": "A short animation-style sequence showing how the main process unfolds step by step.",
                "kind": "animation_idea",
                "suggested_format": "animation_storyboard",
            },
        ]
    d["visual_briefs"] = vb
    topics = d.get("suggested_followup_topics")
    if not isinstance(topics, list):
        d["suggested_followup_topics"] = []
    else:
        d["suggested_followup_topics"] = [str(t).strip() for t in topics if str(t).strip()][:20]
    if "video_lesson_prompt" not in d:
        d["video_lesson_prompt"] = None
    if "mermaid_diagram" not in d:
        d["mermaid_diagram"] = None
    if "diagram_caption" not in d:
        d["diagram_caption"] = None
    return d


def _fallback_explain_response(raw: str) -> ExplainResponse:
    return ExplainResponse(
        explanation_markdown=raw,
        simple_examples=[],
        visual_briefs=[
            VisualAssetBrief(
                title="Chapter summary",
                description="The model returned non-JSON text; use the markdown above or try again.",
                kind="other",
                suggested_format="svg_or_image",
            )
        ],
        suggested_followup_topics=[],
        video_lesson_prompt=None,
        mermaid_diagram=None,
        diagram_caption=None,
        output_language_used=None,
        detected_language_from_prompt=None,
        pdf_extraction_notes=None,
        source_text_used_for_context=None,
    )


def _parse_explain_json(raw: str) -> ExplainResponse:
    data = _extract_json_object(raw)
    if not data:
        return _fallback_explain_response(raw)
    data = _coerce_explain_dict(data)
    md = data.get("mermaid_diagram")
    if isinstance(md, str):
        data["mermaid_diagram"] = _sanitize_mermaid_diagram(md)
    try:
        return ExplainResponse.model_validate(data)
    except ValidationError:
        return _fallback_explain_response(raw)


def _explain_max_tokens(chapter_len: int) -> int:
    if chapter_len > 45_000:
        return 16_384
    if chapter_len > 15_000:
        return 8192
    if chapter_len > 6000:
        return 6144
    return 4096


def _finalize(
    parsed: ExplainResponse,
    output_language: OutputLanguage,
    detected_language: str | None = None,
) -> ExplainResponse:
    """Stamp output_language_used and detected_language_from_prompt onto the response."""
    return parsed.model_copy(
        update={
            "output_language_used": output_language,
            "detected_language_from_prompt": detected_language,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Public service functions (called by endpoint handlers)
# ═══════════════════════════════════════════════════════════════════════════════

async def explain_from_pdf_bytes(
    pdf_bytes: bytes,
    *,
    output_language: OutputLanguage,
    topic_hint: str | None,
    llm_provider: str | None,
    ocr_pages: bool,
    ocr_images: bool,
) -> ExplainResponse:
    ext = extract_pdf_to_text(pdf_bytes, ocr_pages=ocr_pages, ocr_images=ocr_images)
    prefix = (
        "[Source: PDF extraction — content from **all extracted pages** is included below "
        "(each page starts with === Page N ===). Tables appear in [Table …] blocks; "
        "text from figures or scans in [Text from image…] or [Page N — OCR from page image] blocks. "
        "Base your lesson on the **entire** excerpt, not only the opening lines.]\n\n"
    )
    out = await explain_from_text(
        prefix + ext.chapter_text,
        output_language=output_language,
        topic_hint=topic_hint,
        llm_provider=llm_provider,
    )
    return out.model_copy(
        update={
            "pdf_extraction_notes": ext.notes,
            "source_text_used_for_context": ext.chapter_text,
        }
    )


async def explain_from_text(
    chapter_text: str,
    *,
    output_language: OutputLanguage,
    topic_hint: str | None,
    llm_provider: str | None = None,
) -> ExplainResponse:
    # ── NEW: auto-detect language from text/topic_hint ────────────────────────
    resolved_lang, detected = resolve_output_language(
        output_language, chapter_text, topic_hint
    )
    # ─────────────────────────────────────────────────────────────────────────

    body = (
        _user_language_block(resolved_lang)
        + "Chapter content (source material; may be any language — translate and explain fully in OUTPUT_LANGUAGE):\n\n"
        + chapter_text.strip()
        + "\n\n"
        + _user_language_block(resolved_lang, closing=True)
    )
    messages: list[Message] = [
        {"role": "system", "content": _system_prompt(resolved_lang, topic_hint)},
        {"role": "user", "content": body},
    ]
    provider = get_llm_provider(vision=False, provider=llm_provider)
    body_len = len(chapter_text.strip())
    raw = await provider.complete_chat(
        messages,
        max_tokens=_explain_max_tokens(body_len),
        temperature=0.35,
    )
    return _finalize(_parse_explain_json(raw), resolved_lang, detected)


def _guess_mime(header: bytes) -> str:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


async def explain_from_image_bytes(
    files: list[tuple[str, bytes]],
    *,
    output_language: OutputLanguage,
    topic_hint: str | None,
    llm_provider: str | None = None,
) -> ExplainResponse:
    # ── NEW: auto-detect language from topic_hint ─────────────────────────────
    resolved_lang, detected = resolve_output_language(
        output_language, "", topic_hint
    )
    # ─────────────────────────────────────────────────────────────────────────

    intro = (
        _user_language_block(resolved_lang)
        + "These images are textbook chapter pages. Read them, then explain simply for students. "
        + "All learner-facing strings in your JSON must follow OUTPUT_LANGUAGE. "
        + (f"Emphasize: {topic_hint}. " if topic_hint else "")
        + _JSON_CONTRACT
    )
    closing = _user_language_block(resolved_lang, closing=True)

    content: list[TextPart | ImageUrlPart] = [{"type": "text", "text": intro}]

    for _filename, data in files:
        if not data:
            continue
        mime = _guess_mime(data[:12])
        if mime == "application/octet-stream":
            mime = "image/png"
        b64 = base64.standard_b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )

    content.append({"type": "text", "text": closing})

    messages: list[Message] = [
        {"role": "system", "content": _system_prompt(resolved_lang, topic_hint)},
        {"role": "user", "content": content},
    ]

    provider = get_llm_provider(vision=True, provider=llm_provider)
    raw = await provider.complete_chat(messages, max_tokens=4096, temperature=0.35)
    return _finalize(_parse_explain_json(raw), resolved_lang, detected)