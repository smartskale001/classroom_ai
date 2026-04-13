import base64
import json
import re

from pydantic import ValidationError

from app.schemas.explain import ExplainResponse, VisualAssetBrief
from app.schemas.language import OutputLanguage
from app.services.llm.factory import get_llm_provider
from app.services.llm.types import ImageUrlPart, Message, TextPart


def _user_language_block(output_language: OutputLanguage, *, closing: bool = False) -> str:
    """Strong, repeated instructions; JSON schema examples were biasing models toward English."""
    if output_language == "english":
        line = "OUTPUT_LANGUAGE=english. All learner-facing strings must be in English."
    elif output_language == "hindi":
        line = (
            "OUTPUT_LANGUAGE=hindi (Devanagari). All learner-facing strings — explanation_markdown, "
            "simple_examples, visual_brief title/description, suggested_followup_topics, "
            "video_lesson_prompt — MUST be in Hindi using देवनागरी script. "
            "Do not use Roman/Latin letters for Hindi words. Translate from the chapter if it is in English."
        )
    else:
        line = (
            "OUTPUT_LANGUAGE=roman_hindi (Hindi in Latin letters only). "
            "All learner-facing strings — explanation_markdown, simple_examples, "
            "visual_brief title/description, suggested_followup_topics, video_lesson_prompt — "
            "MUST be Hindi written with A–Z letters only (e.g. \"Prakash ki paravartan\", "
            "\"Darpan par padne wala kon\"). "
            "Do NOT use Devanagari (no Hindi script). "
            "JSON keys stay English; enum tokens kind/suggested_format stay as specified. "
            "Mermaid labels: Roman Hindi or very short English. "
            "Translate the teaching from the chapter even if the chapter is English."
        )
    tag = "FINAL CHECK — " if closing else ""
    return f"{tag}{line}\n\n"


_JSON_CONTRACT = """
Return a single JSON object only (no markdown code fences).
Keys (keep these key names in English): explanation_markdown (string), simple_examples (array of strings),
visual_briefs (array of {title, description, kind, suggested_format}),
suggested_followup_topics (array of strings), video_lesson_prompt (string or null), mermaid_diagram (string or null).

Rules:
- kind must be one of: diagram, analogy_illustration, timeline, graph_concept, animation_idea, other.
- suggested_format must be one of: mermaid, animation_storyboard, svg_or_image.
- Put at least 2 items in visual_briefs; use full sentences in title and description.
- mermaid_diagram: valid Mermaid v10+ syntax only, or null. Prefer flowchart TD or graph LR. First line MUST be the diagram keyword (no title line before it). Use ASCII-only node IDs (A, B, C, …). Put ALL label text in double quotes: A["Light source"] --> B["Mirror"]. Use --> for links. Avoid raw parentheses inside unquoted brackets. Do NOT put a second copy of the diagram inside explanation_markdown fenced blocks — only here in mermaid_diagram. Newlines in JSON must be escaped as \\n.

LANGUAGE: Every string that students will read MUST follow OUTPUT_LANGUAGE from the messages above — not English unless OUTPUT_LANGUAGE is english.
"""


def _system_prompt(output_language: OutputLanguage, topic_hint: str | None) -> str:
    focus = f" Focus the explanation on: {topic_hint}." if topic_hint else ""
    if output_language == "english":
        lang = "Learner-facing text: English only."
    elif output_language == "hindi":
        lang = "Learner-facing text: Hindi in Devanagari only (देवनागरी)."
    else:
        lang = "Learner-facing text: Roman Hindi only (Hindi in Latin alphabet, no Devanagari)."
    return (
        "You are an expert school teacher. Simplify the chapter for students.\n"
        f"{lang}{focus}\n"
        "Include at least two visual_briefs: one animation_storyboard and one mermaid when possible.\n"
        + _JSON_CONTRACT
    )


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
    """Drop preamble lines; ensure a Mermaid diagram keyword starts the chart (v11 is strict)."""
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
    # Smart quotes / unicode dashes often break Mermaid 11 parsers in labels.
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


def _parse_explain_json(raw: str) -> ExplainResponse:
    try:
        data = json.loads(raw)
        md = data.get("mermaid_diagram")
        if isinstance(md, str):
            md = _sanitize_mermaid_diagram(md)
            data["mermaid_diagram"] = md
        return ExplainResponse.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
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
            output_language_used=None,
        )


def _finalize(parsed: ExplainResponse, output_language: OutputLanguage) -> ExplainResponse:
    return parsed.model_copy(update={"output_language_used": output_language})


async def explain_from_text(
    chapter_text: str,
    *,
    output_language: OutputLanguage,
    topic_hint: str | None,
    llm_provider: str | None = None,
) -> ExplainResponse:
    body = (
        _user_language_block(output_language)
        + "Chapter content (source material; may be any language):\n\n"
        + chapter_text.strip()
        + "\n\n"
        + _user_language_block(output_language, closing=True)
    )
    messages: list[Message] = [
        {"role": "system", "content": _system_prompt(output_language, topic_hint)},
        {"role": "user", "content": body},
    ]
    provider = get_llm_provider(vision=False, provider=llm_provider)
    raw = await provider.complete_chat(messages, max_tokens=4096, temperature=0.35)
    return _finalize(_parse_explain_json(raw), output_language)


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
    intro = (
        _user_language_block(output_language)
        + "These images are textbook chapter pages. Read them, then explain simply for students. "
        + "All learner-facing strings in your JSON must follow OUTPUT_LANGUAGE. "
        + (f"Emphasize: {topic_hint}. " if topic_hint else "")
        + _JSON_CONTRACT
    )
    closing = _user_language_block(output_language, closing=True)

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
        {"role": "system", "content": _system_prompt(output_language, topic_hint)},
        {"role": "user", "content": content},
    ]

    provider = get_llm_provider(vision=True, provider=llm_provider)
    raw = await provider.complete_chat(messages, max_tokens=4096, temperature=0.35)
    return _finalize(_parse_explain_json(raw), output_language)
