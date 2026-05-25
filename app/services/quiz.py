import json
import re

from pydantic import ValidationError

from app.schemas.language import OutputLanguage
from app.schemas.quiz import QuizGenerateResponse, QuizQuestion
from app.services.llm.factory import get_llm_provider
from app.services.llm.types import Message


# ---------------------------------------------------------------------------
# Language helpers
# ---------------------------------------------------------------------------

def _lang_rule(lang: OutputLanguage) -> str:
    if lang == "english":
        return "All learner-facing text must be in English."
    if lang == "hindi":
        return "All learner-facing text must be in Hindi (Devanagari script)."
    return "All learner-facing text must be in Roman Hindi (Latin letters only, no Devanagari)."


# ---------------------------------------------------------------------------
# Main quiz-generation prompt
# ---------------------------------------------------------------------------

def _prompt(
    *,
    topic: str,
    difficulty: str,
    question_count: int,
    output_language: OutputLanguage,
    context_text: str | None,
) -> str:
    context = (context_text or "").strip()
    ctx_excerpt = context[:26000]

    grounded = (
        "\nCONTEXT-GROUNDING RULES:\n"
        "- Every question MUST test conceptual understanding, NOT pattern-matching to sentence fragments.\n"
        "- NEVER copy a sentence from the context as an answer option.\n"
        "- Rewrite all answer options in your own words — short, clear, testable statements.\n"
        "- The correct answer must be fully supported by the context.\n\n"
    )

    no_context = (
        "\nNO CONTEXT PROVIDED — USE GENERAL KNOWLEDGE:\n"
        f"- Generate {question_count} high-quality questions about '{topic}' from your training knowledge.\n"
        "- Questions must test real understanding — definitions, causes, comparisons, applications.\n\n"
    )

    distractor_rules = (
        "DISTRACTOR QUALITY RULES (critical for educational value):\n"
        "- Wrong options must be PLAUSIBLE to a student who hasn't studied well.\n"
        "- Use these distractor strategies (vary them):\n"
        "  1. COMMON MISCONCEPTION — a belief many students wrongly hold.\n"
        "  2. PARTIALLY TRUE — mix a correct fact with an incorrect one.\n"
        "  3. CONCEPT SWAP — replace a key term with a related-but-wrong term.\n"
        "  4. CAUSE/EFFECT REVERSAL — flip the direction of a relationship.\n"
        "  5. OVER-GENERALISATION — make a specific fact sound universally true.\n"
        "  6. PLAUSIBLE NEIGHBOUR — use a fact from a closely related concept.\n"
        "- NEVER write distractors that:\n"
        "  * Are sentence fragments or partial copies of the context text\n"
        "  * Only negate the correct answer ('X does NOT...')\n"
        "  * Are obviously false ('The Sun is made of ice')\n"
        "  * Are meta-labels ('This is incorrect', 'Option 1')\n"
        "  * Change only a single word or add 'not' to the correct answer\n"
        "- Every option must be a complete, grammatically correct statement.\n"
        "- All 4 options must be similar in length and style.\n\n"
    )

    question_rules = (
        "QUESTION QUALITY RULES:\n"
        "- Each question must have a SPECIFIC, meaningful stem targeting:\n"
        "  a fact, definition, process step, contrast, or causal relationship.\n"
        "- BANNED question stems (never use these patterns):\n"
        "  * 'Which statement is most closely about...'\n"
        "  * 'Which line from the text...'\n"
        "  * 'According to the lesson, which statement matches...'\n"
        "  * 'Which choice aligns best with...'\n"
        "- GOOD question stems look like:\n"
        "  * 'Where in a plant cell does photosynthesis take place?'\n"
        "  * 'What is the primary function of chlorophyll?'\n"
        "  * 'Which gas is released as a byproduct of photosynthesis?'\n"
        "  * 'What would happen if a plant were placed in complete darkness?'\n"
        f"- Return EXACTLY {question_count} questions.\n"
        "- No repeated questions. No repeated correct answers across questions.\n"
        "- Vary question types: factual recall, conceptual understanding, application, cause-effect, comparison.\n\n"
        f"DIVERSITY: Assign each of the {question_count} questions a UNIQUE angle:\n"
        "  1=definition/what-is, 2=process/how, 3=location/where, 4=cause/why,\n"
        "  5=effect/consequence, 6=comparison/contrast, 7=application/example,\n"
        "  8=exception/limitation, 9=sequence/order, 10=key-figure/component\n"
        "  Label each question stem with its angle in brackets e.g. [definition] What is...\n"
        "  NEVER assign the same angle to two questions.\n\n"
    )

    output_format = (
        "OUTPUT FORMAT — Return valid JSON only. No markdown, no code fences, no explanation.\n"
        "Required keys: topic, output_language_used, questions\n"
        "Each question must have:\n"
        "  id, question, options (array of 4 complete sentences),\n"
        "  correct_option_index (0-3),\n"
        "  correct_explanation (why this answer is right),\n"
        "  wrong_explanation (what mistake leads students to pick wrong answers),\n"
        "  option_explanations (array of 4 — one reason per option),\n"
        "  distractor_strategy (array of 3 — strategy name for each wrong option)\n"
    )

    base = (
        "You are an expert teacher and competitive exam question setter.\n"
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty}\n"
        f"Question count: {question_count}\n"
        f"{_lang_rule(output_language)}\n\n"
        + (grounded if ctx_excerpt else no_context)
        + distractor_rules
        + question_rules
        + output_format
        + (f"\nContext material:\n{ctx_excerpt}\n" if ctx_excerpt else "")
    )
    return base


# ---------------------------------------------------------------------------
# LLM-powered distractor generation  (KEY NEW FUNCTION)
# ---------------------------------------------------------------------------

async def _llm_generate_distractors(
    *,
    question: str,
    correct_answer: str,
    context_excerpt: str,
    topic: str,
    provider_name: str,
    lang: OutputLanguage,
) -> list[str]:
    """
    Ask the LLM to generate 3 high-quality, educationally realistic distractors
    for a given question + correct answer.  Returns a list of exactly 3 strings.
    """
    provider = get_llm_provider(vision=False, provider=provider_name)
    lang_rule = _lang_rule(lang)

    system = (
        "You are an expert MCQ distractor writer for competitive exams. "
        "Return ONLY a JSON array of exactly 3 strings. No markdown, no explanation."
    )
    user = (
        f"{lang_rule}\n\n"
        f"Topic: {topic}\n"
        f"Context:\n{context_excerpt[:8000]}\n\n"
        f"Question: {question}\n"
        f"Correct answer: {correct_answer}\n\n"
        "Write 3 wrong answer options (distractors) that:\n"
        "1. Sound plausible to a student who hasn't studied well\n"
        "2. Are clearly wrong to someone who has read the context\n"
        "3. Use varied strategies: common misconception, concept swap, partial truth, cause-effect reversal\n"
        "4. Are complete claims — NOT just 'Option 1' or negations of the correct answer\n"
        "5. Are similar in length and style to the correct answer\n\n"
        'Return ONLY a JSON array: ["distractor 1", "distractor 2", "distractor 3"]'
    )

    messages: list[Message] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        raw = await provider.complete_chat(messages, max_tokens=600, temperature=0.85)
        raw = raw.strip()
        # Strip markdown fences if any
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list) and len(parsed) >= 3:
            return [str(d).strip() for d in parsed[:3]]
    except Exception:
        pass

    # Soft fallback: return empty so caller handles it
    return []


# ---------------------------------------------------------------------------
# Context sentence helpers
# ---------------------------------------------------------------------------

def _words(s: str) -> set[str]:
    return set(re.findall(r"[\w]{3,}", s.lower()))


def _sentences_from_context(text: str, *, min_len: int = 15) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = " ".join(p.split())
        if len(s) < min_len:
            continue
        key = s.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(s[:300])
    return out


def _option_grounded(option: str, context: str) -> bool:
    o = option.strip()
    if len(o) < 10:
        return False
    ol = o.lower()
    ctx = context.lower()
    if len(o) >= 18 and ol in ctx:
        return True
    for win in (40, 32, 24):
        for i in range(0, max(1, len(o) - win + 1), 6):
            chunk = ol[i : i + win]
            if len(chunk) >= 18 and chunk in ctx:
                return True
    ow = _words(o)
    if len(ow) < 4:
        return False
    best = 0
    for sent in _sentences_from_context(context, min_len=12):
        inter = len(ow & _words(sent))
        if inter > best:
            best = inter
    return best >= max(3, int(0.22 * len(ow)))


def _option_soft_overlap(option: str, context: str) -> bool:
    ow = _words(option)
    cw = _words(context)
    if len(ow) < 3:
        return False
    inter = len(ow & cw)
    return inter >= max(3, int(0.2 * len(ow)))


def _question_overlaps_context(question: str, context: str, *, min_shared: int = 3) -> bool:
    qwl = _words(question)
    cwl = _words(context)
    if len(qwl & cwl) >= min_shared:
        return True
    qn = " ".join(question.lower().split())[:200]
    return len(qn) >= 24 and qn in context.lower()


# ---------------------------------------------------------------------------
# Lightweight mechanical distractor helpers  (last-resort only)
# ---------------------------------------------------------------------------

_SAFE_SWAPS: list[tuple[str, str]] = [
    ("into", "from"), ("from", "into"),
    ("all", "no"), ("no", "all"),
    ("before", "after"), ("after", "before"),
    ("above", "below"), ("below", "above"),
    ("increases", "decreases"), ("decreases", "increases"),
    ("produces", "absorbs"), ("absorbs", "produces"),
    ("releases", "stores"), ("stores", "releases"),
    ("converts", "breaks down"),
    ("causes", "prevents"), ("prevents", "causes"),
    ("starts", "stops"), ("stops", "starts"),
    ("gains", "loses"), ("loses", "gains"),
    ("rises", "falls"), ("falls", "rises"),
    ("more", "less"), ("less", "more"),
    ("always", "never"), ("never", "always"),
    ("directly", "indirectly"),
]


def _replace_first(text: str, old: str, new: str) -> str:
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return text
    replacement = new[0].upper() + new[1:] if match.group(0)[0].isupper() else new
    return text[: match.start()] + replacement + text[match.end():]


def _tweak_number(text: str) -> str | None:
    m = re.search(r"\b(19|20)\d{2}\b", text)
    if m:
        yr = int(m.group(0))
        return text[:m.start()] + str(yr + 10 if yr < 2010 else yr - 10) + text[m.end():]
    m = re.search(r"\b(\d+(\.\d+)?)\s*%", text)
    if m:
        val = float(m.group(1))
        new_val = round(val + 15 if val < 50 else val - 15, 1)
        return re.sub(re.escape(m.group(0)), f"{new_val}%", text, count=1)
    m = re.search(r"\b([2-9]\d+|\d{2,})\b", text)
    if m:
        val = int(m.group(0))
        return text[:m.start()] + str(val * 2 if val < 50 else val - round(val * 0.4)) + text[m.end():]
    return None


def _apply_safe_swap(text: str) -> str | None:
    for original, replacement in _SAFE_SWAPS:
        if re.search(r"\b" + re.escape(original) + r"\b", text, re.IGNORECASE):
            return _replace_first(text, original, replacement)
    return None


def _mechanical_distractors(correct: str) -> list[str]:
    """
    LAST-RESORT only: purely mechanical manipulation.
    Caller should prefer _llm_generate_distractors.
    """
    s = correct.strip().rstrip(".")
    wrongs: list[str] = []
    used: set[str] = {s.lower()}

    def _add(candidate: str | None) -> bool:
        if not candidate:
            return False
        candidate = candidate.strip()
        if candidate.lower() in used:
            return False
        wrongs.append(candidate)
        used.add(candidate.lower())
        return True

    _add(_tweak_number(s))
    _add(_apply_safe_swap(s))
    # Negation: simple "X is not correct" as very last resort
    if len(wrongs) < 3:
        neg = f"It is not the case that: {s[:120]}"
        _add(neg)
    # Pad if still short
    fallbacks = [
        _apply_safe_swap(s),
        _tweak_number(s),
    ]
    for fb in fallbacks:
        if len(wrongs) >= 3:
            break
        _add(fb)

    # Absolute pad
    i = 1
    while len(wrongs) < 3:
        wrongs.append(f"{s[:80]} (variant {i})")
        i += 1

    return wrongs[:3]


# ---------------------------------------------------------------------------
# LLM-powered fallback question generation  (KEY NEW FUNCTION)
# ---------------------------------------------------------------------------

async def _llm_fallback_question(
    *,
    topic: str,
    idx: int,
    context_text: str,
    provider_name: str,
    lang: OutputLanguage,
    avoid_questions: list[str],
) -> QuizQuestion | None:
    """
    Generate a single high-quality MCQ using the LLM when the main batch fails.
    """
    provider = get_llm_provider(vision=False, provider=provider_name)
    lang_rule = _lang_rule(lang)
    avoid = ""
    if avoid_questions:
        avoid = "\nDo NOT generate questions similar to:\n- " + "\n- ".join(avoid_questions[:10])

    system = (
        "You are an expert teacher and exam-paper setter. "
        "Return ONLY valid JSON — no markdown, no explanation."
    )
    user = (
        f"{lang_rule}\n"
        f"Topic: {topic}\n"
        f"Context:\n{context_text[:8000]}\n\n"
        f"Generate exactly 1 MCQ question (index {idx + 1}) with:\n"
        "- A specific, targeted question stem (not generic)\n"
        "- 4 options: 1 correct + 3 realistic distractors using varied strategies "
        "(misconception, concept swap, partial truth, cause-effect reversal)\n"
        "- All options must be complete claims, plausible to a weak student\n"
        + avoid
        + "\nReturn JSON: {\"question\": str, \"options\": [str,str,str,str], "
        "\"correct_option_index\": int, \"correct_explanation\": str, "
        "\"wrong_explanation\": str, \"option_explanations\": [str,str,str,str]}"
    )

    messages: list[Message] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    try:
        raw = await provider.complete_chat(messages, max_tokens=800, temperature=0.9)
        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        n = idx + 1
        return QuizQuestion(
            id=f"q{n}",
            question=data.get("question", f"[{n}] Question about {topic}"),
            options=data.get("options", []),
            correct_option_index=int(data.get("correct_option_index", 0)),
            correct_explanation=data.get("correct_explanation", ""),
            wrong_explanation=data.get("wrong_explanation", ""),
            option_explanations=data.get("option_explanations", [""] * 4),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------

_BOILERPLATE_SUBSTR = (
    "partly incorrect statement mixing",
    "unrelated statement that does not explain",
    "contradictory statement about",
    "conceptually correct statement about",
    "this statement does not correctly describe",
    "this interpretation of",
    "this explanation conflicts",
    "this option does not fully match",
)

_META_OPTION_PATTERNS = [
    r"^option\s*\d+\s*$",
    r"^(partly|partially)\s+incorrect",
    r"^(unrelated|contradictory|conceptually correct)\s+statement",
    r"^this statement (does not|is not|contradicts)",
    r"^this (interpretation|explanation|option)",
    r"\bis not correct\.$",
]


def _is_boilerplate_option(opt: str) -> bool:
    ol = opt.lower().strip()
    if any(b in ol for b in _BOILERPLATE_SUBSTR):
        return True
    return any(re.search(p, ol, re.I) for p in _META_OPTION_PATTERNS)


def _looks_like_boilerplate_options(options: list[str]) -> bool:
    return any(_is_boilerplate_option(o) for o in options)


def _question_needs_fallback(q: QuizQuestion, context_text: str | None) -> bool:
    opts = [o.strip() for o in (q.options or []) if o and o.strip()]
    ctx = (context_text or "").strip()
    if len(opts) < 4:
        return True
    if _looks_like_boilerplate_options(opts):
        return True
    if len({o.lower() for o in opts}) < 4:
        return True
    if any(re.match(r"^option\s*\d+\s*$", o, re.I) for o in opts):
        return True
    if not ctx:
        return False
    hard = sum(1 for o in opts if _option_grounded(o, ctx))
    soft = sum(1 for o in opts if _option_soft_overlap(o, ctx))
    q_ok = _question_overlaps_context(q.question, ctx, min_shared=2)
    if hard >= 1:
        return False
    if soft >= 3:
        return False
    if soft >= 2 and q_ok:
        return False
    if not q_ok:
        return True
    return False


def _count_bad_distractors(q: QuizQuestion) -> int:
    """Count how many wrong options are boilerplate/mechanical."""
    count = 0
    for i, opt in enumerate(q.options or []):
        if i == q.correct_option_index:
            continue
        if _is_boilerplate_option(opt):
            count += 1
        # Detect pure negation patterns
        elif re.search(r"\b(is not|does not|cannot|will not|never)\b", opt.lower()):
            # Not always bad, but flag if the rest of the option is very close to correct
            correct = (q.options or [""])[q.correct_option_index]
            correct_words = _words(correct)
            opt_words = _words(opt)
            if correct_words and len(correct_words & opt_words) / len(correct_words) > 0.7:
                count += 1
    return count


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json_obj(raw: str) -> dict | None:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        chunk = raw[start : end + 1]
        try:
            obj = json.loads(chunk)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Normalize / repair questions
# ---------------------------------------------------------------------------

async def _normalize_questions(
    parsed: QuizGenerateResponse,
    topic: str,
    question_count: int,
    context_text: str | None,
    llm_provider: str,
    output_language: OutputLanguage,
) -> QuizGenerateResponse:
    qs: list[QuizQuestion] = []
    seen_q: set[str] = set()
    ctx = (context_text or "").strip()

    for i, q in enumerate(parsed.questions):
        # --- Clean & dedupe options ---
        raw_options = [o.strip() for o in (q.options or []) if o and o.strip()]
        deduped: list[str] = []
        seen_opt: set[str] = set()
        for opt in raw_options:
            k = opt.lower()
            if k not in seen_opt:
                seen_opt.add(k)
                deduped.append(opt)
        options = deduped

        # --- Fix boilerplate options using LLM ---
        bad_indices = [
            j for j, o in enumerate(options)
            if j != q.correct_option_index and _is_boilerplate_option(o)
        ]
        if bad_indices:
            correct_text = options[q.correct_option_index] if 0 <= q.correct_option_index < len(options) else ""
            new_distractors = await _llm_generate_distractors(
                question=q.question,
                correct_answer=correct_text,
                context_excerpt=ctx,
                topic=topic,
                provider_name=llm_provider,
                lang=output_language,
            )
            if not new_distractors:
                new_distractors = _mechanical_distractors(correct_text)

            di = 0
            for bad_j in bad_indices:
                if di < len(new_distractors):
                    candidate = new_distractors[di]
                    if candidate.lower() not in seen_opt:
                        options[bad_j] = candidate
                        seen_opt.add(candidate.lower())
                        di += 1

        # --- Fill missing options ---
        if len(options) < 4:
            correct_text = options[q.correct_option_index] if 0 <= q.correct_option_index < len(options) else ""
            new_distractors = await _llm_generate_distractors(
                question=q.question,
                correct_answer=correct_text,
                context_excerpt=ctx,
                topic=topic,
                provider_name=llm_provider,
                lang=output_language,
            ) if correct_text else []
            if not new_distractors:
                new_distractors = _mechanical_distractors(correct_text) if correct_text else []
            for d in new_distractors:
                if len(options) >= 4:
                    break
                if d.lower() not in seen_opt:
                    options.append(d)
                    seen_opt.add(d.lower())

        # --- Question dedupe ---
        q_key = " ".join(_words(q.question))
        if not q_key or q_key in seen_q:
            continue
        seen_q.add(q_key)

        # --- Correct answer dedupe (prevents same answer repeating across questions) ---
        correct_text = options[q.correct_option_index] if 0 <= q.correct_option_index < len(options) else ""
        correct_key = " ".join(_words(correct_text))
        if correct_key and correct_key in seen_q:
            continue  # skip question whose correct answer already appeared
        if correct_key:
            seen_q.add(correct_key)

        # --- Validate correct index ---
        idx = q.correct_option_index
        if idx < 0 or idx >= len(options):
            idx = 0

        # --- Option explanations ---
        oex = (q.option_explanations or [])[:4]
        while len(oex) < 4:
            oex.append(q.wrong_explanation or "")

        built = q.model_copy(
            update={
                "id": f"q{i + 1}",
                "options": options[:4],
                "correct_option_index": idx,
                "option_explanations": oex,
            }
        )
        qs.append(built)

    # --- Fill remaining with LLM-generated fallback questions ---
    while len(qs) < question_count:
        idx = len(qs)
        avoid = [q.question for q in qs]
        llm_q = await _llm_fallback_question(
            topic=topic,
            idx=idx,
            context_text=ctx,
            provider_name=llm_provider,
            lang=output_language,
            avoid_questions=avoid,
        )
        if llm_q and llm_q.question.lower().strip() not in seen_q:
            seen_q.add(llm_q.question.lower().strip())
            qs.append(llm_q)
        else:
            # Absolute last resort: static placeholder (shouldn't normally happen)
            qs.append(QuizQuestion(
                id=f"q{idx + 1}",
                question=f"[{idx + 1}] Based on the lesson, which statement about '{topic}' is correct?",
                options=[
                    f"The concept of {topic} is central to understanding this lesson.",
                    f"{topic} is unrelated to the main idea of the passage.",
                    f"The passage never mentions {topic} in any context.",
                    f"{topic} only applies in situations not covered by this lesson.",
                ],
                correct_option_index=0,
                correct_explanation=f"The lesson focuses on {topic} as a key concept.",
                wrong_explanation="The other options misrepresent the lesson content.",
                option_explanations=[
                    "Supported by the overall lesson.", "Contradicts the lesson.",
                    "Factually wrong.", "Too narrow a claim.",
                ],
            ))

    return parsed.model_copy(update={"questions": qs[:question_count]})


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_quiz(
    *,
    topic: str,
    context_text: str | None,
    output_language: OutputLanguage,
    question_count: int,
    difficulty: str,
    llm_provider: str,
) -> QuizGenerateResponse:
    provider = get_llm_provider(vision=False, provider=llm_provider)
    collected: list[QuizQuestion] = []
    seen: set[str] = set()
    ctx = (context_text or "").strip()
    temp = 0.9 if ctx else 1.0
    max_tok = 9000 if ctx else 5000

    for attempt in range(3):
        remaining = question_count - len(collected)
        if remaining <= 0:
            break

        avoid = ""
        if collected:
            prev = [q.question for q in collected]
            avoid = "\nAlready generated questions (do NOT repeat or rephrase):\n- " + "\n- ".join(prev[:20])

        messages: list[Message] = [
            {
                "role": "system",
                "content": (
                    "You output strict JSON only — no markdown, no preamble.\n\n"
                    "DISTRACTOR RULES (non-negotiable):\n"
                    "- Wrong options must use named strategies: misconception, concept_swap, partial_truth, "
                    "cause_effect_reversal, over_generalisation, plausible_neighbour.\n"
                    "- A wrong option that only negates the correct answer is FORBIDDEN.\n"
                    "- Each wrong option must be a complete, meaningful claim that a student might believe.\n"
                    "- All 4 options must be similar in length and grammatical structure.\n"
                    "QUESTION DIVERSITY RULES (non-negotiable):\n"
                    "- Each question must cover a DIFFERENT sub-topic or aspect — causes, events, figures, "
                    "consequences, ideology, dates, comparisons, definitions — never repeat the same angle.\n"
                    "- NEVER generate two questions with the same correct answer.\n"
                    "- NEVER use 'what was a significant outcome' or similar generic stems more than once.\n"
                    "- Stems must be concrete and specific — no generic 'which statement is about X' questions.\n"
                ),
            },
            {
                "role": "user",
                "content": _prompt(
                    topic=topic,
                    difficulty=difficulty,
                    question_count=remaining,
                    output_language=output_language,
                    context_text=context_text,
                )
                + avoid
                + f"\nAttempt: {attempt + 1}",
            },
        ]

        raw = await provider.complete_chat(messages, max_tokens=max_tok, temperature=temp)
        data = _extract_json_obj(raw) or {}
        try:
            parsed_try = QuizGenerateResponse.model_validate(
                {
                    "topic": data.get("topic", topic),
                    "output_language_used": data.get("output_language_used", output_language),
                    "questions": data.get("questions", []),
                }
            )
        except ValidationError:
            parsed_try = QuizGenerateResponse(
                topic=topic,
                output_language_used=output_language,
                questions=[],
            )

        normalized_try = await _normalize_questions(
            parsed_try,
            topic=topic,
            question_count=max(len(parsed_try.questions), 1),
            context_text=context_text,
            llm_provider=llm_provider,
            output_language=output_language,
        )

        for q in normalized_try.questions:
            key = q.question.lower().strip()
            if key and key not in seen:
                seen.add(key)
                collected.append(q)
                if len(collected) >= question_count:
                    break

    parsed = QuizGenerateResponse(
        topic=topic,
        output_language_used=output_language,
        questions=collected,
    )
    parsed = parsed.model_copy(update={"output_language_used": output_language, "topic": topic})
    return await _normalize_questions(
        parsed,
        topic,
        question_count,
        context_text,
        llm_provider=llm_provider,
        output_language=output_language,
    )