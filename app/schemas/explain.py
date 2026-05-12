# app/schemas/explain.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Language type (single source of truth — imported from language.py) ────────
# Keep in sync with app/schemas/language.py OutputLanguage literal.
OutputLanguageLiteral = Literal[
    "english",
    "hindi",
    "roman_hindi",
    "telugu",
    "tamil",
    "gujarati",
    "marathi",
    "bengali",
    "kannada",
    "malayalam",
    "punjabi",
    "urdu",
]

_LANGUAGE_DESCRIPTION = (
    "Language for all learner-facing output. "
    "english | hindi (Devanagari) | roman_hindi (Hindi in Latin letters) | "
    "telugu | tamil | gujarati | marathi | bengali | kannada | malayalam | punjabi | urdu. "
    "Default: english. "
    "You can also leave this blank and mention the language in your text/topic_hint "
    "(e.g. 'explain in Telugu') — the API will auto-detect it."
)


# ── Request schemas ────────────────────────────────────────────────────────────

class ExplainFromTextRequest(BaseModel):
    chapter_text: str = Field(
        ...,
        min_length=1,
        description="Full or partial chapter content.",
    )
    output_language: OutputLanguageLiteral = Field(
        default="english",
        description=_LANGUAGE_DESCRIPTION,
    )
    topic_hint: str | None = Field(
        default=None,
        description=(
            "Optional focus (e.g. section title or 'explain in Hindi') if the text covers "
            "multiple topics. Language mentioned here overrides output_language."
        ),
    )


class ExplainFromImagesRequest(BaseModel):
    """Used for JSON-only metadata when images are sent as multipart files in the endpoint."""

    output_language: OutputLanguageLiteral = "english"
    topic_hint: str | None = None


# ── Sub-models ─────────────────────────────────────────────────────────────────

class VisualAssetBrief(BaseModel):
    """Structured hint for the client to render or request generated media."""

    title: str
    description: str
    kind: str = Field(
        ...,
        description="e.g. diagram, analogy_illustration, timeline, graph_concept",
    )
    suggested_format: str = Field(
        default="svg_or_image",
        description="svg_or_image, mermaid, or animation_storyboard",
    )


# ── Response schema ────────────────────────────────────────────────────────────

class ExplainResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    explanation_markdown: str
    simple_examples: list[str]
    visual_briefs: list[VisualAssetBrief]
    suggested_followup_topics: list[str] = Field(default_factory=list)
    video_lesson_prompt: str | None = Field(
        default=None,
        description=(
            "Single concise Sora-style prompt for a short educational animation "
            "(no copyrighted characters)."
        ),
    )
    mermaid_diagram: str | None = Field(
        default=None,
        description="Valid Mermaid source to render a diagram in the UI (flowchart/graph).",
    )
    diagram_caption: str | None = Field(
        default=None,
        description=(
            "Short legend: what the diagram shows, label meanings, or how to read it "
            "(same language as lesson)."
        ),
    )
    output_language_used: OutputLanguageLiteral | None = Field(
        default=None,
        description="Echo of the language the server applied (verify your selection reached the API).",
    )
    detected_language_from_prompt: str | None = Field(
        default=None,
        description=(
            "If the language was auto-detected from the user's text/topic_hint, "
            "this echoes what was detected (e.g. 'telugu'). None if output_language was used directly."
        ),
    )
    pdf_extraction_notes: str | None = Field(
        default=None,
        description="When explain came from a PDF upload: short summary (pages, tables, OCR).",
    )
    source_text_used_for_context: str | None = Field(
        default=None,
        description=(
            "Raw extracted PDF text echoed for client-side quiz/slides context "
            "(same as sent to the LLM)."
        ),
    )