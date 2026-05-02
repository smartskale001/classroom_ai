# ClassroomAI

> *Imagine handing the computer a single page of a textbook—and getting back a clear explanation, a quiz that actually matches your chapter, slides you can teach from tomorrow, flashcards, narration, and even a short clip. That’s not a wish list for next year’s edtech roadmap; it’s what this repo is built to do.*

Every minute a teacher spends retyping the same ideas into five different tools is a minute not spent with students. **ClassroomAI** closes that gap: it turns raw teaching material—pasted chapter text or screenshots of pages—into a **full lesson package**—explanations, checks for understanding, visuals, audio, and optional short video—so one source drives everything. Run it with **OpenAI** (cloud APIs) or **open-source** tools (**Ollama** for text, optional **SD WebUI** for some images).

---

## What the application can do

### Learn (core)

- Accept **chapter text**, a **PDF** (page-by-page text, **tables** via pdfplumber, optional **Tesseract OCR** for scans and text in images), or **multiple screenshot images** of textbook pages.
- Produce a structured **explanation** in your chosen language (English, Hindi, or Roman Hindi).
- Add a **Mermaid diagram** when a diagram helps (e.g. processes, sequences).
- Suggest **visual briefs** and a **video lesson prompt** you can refine elsewhere in the app.
- Optionally generate an **AI illustration** or a **Pexels stock photo** (search-based stock, not AI-generated pixels) tied to the first visual brief.

### Quiz

- Build **multiple-choice questions** grounded in your lesson (chapter text plus generated explanation when available).
- Adjust **difficulty** and **question count** and regenerate as needed.

### Slides

- Generate a **slide outline** and a downloadable **PowerPoint (.pptx)** with a **dark, presentation-style theme** (hero title slide, full-bleed backgrounds, readable typography).
- **Images:** without an API key, each slide gets a **generated gradient background**; with **`PEXELS_API_KEY`**, slides use **darkened landscape stock photos** behind text (credits in speaker notes).

### Flashcards

- Create **flashcards** from the same lesson context for quick review.

### Infographic

- Produce a **single infographic-style image** from a layout prompt (OpenAI or local SD pipeline, depending on stack).

### Listen (audio)

- Turn lesson content into **spoken audio** (e.g. OpenAI TTS or Edge TTS, depending on configuration).

### Video (short clips)

- **Local animation**: lightweight **MP4** animations rendered on the server (no cloud video API).
- **OpenAI Sora**: generative clips when your account supports the Videos API.
- **Pexels stock video**: **search** the Pexels catalog by keywords and download a real stock clip (not generated; license terms apply).
- **Lesson overview** (Notebook LM–style explainer): turn long **source text** into a **narrated multi-segment MP4** — LLM script, TTS, on-screen titles, optional Pexels backgrounds — stitched with FFmpeg (not Google’s proprietary cinematic pipeline).

---

## Why it’s useful

| Audience | Benefit |
|----------|---------|
| **Teachers & tutors** | Faster prep: one upload or paste drives explanation, quiz, slides, flashcards, and narration—consistent with the same source material. |
| **Students** | Clear explanations, practice questions, and review formats (cards, audio) aligned to *their* chapter, not generic web summaries. |
| **Self-learners** | Same pipeline for independent study from notes or book photos. |
| **Teams on a budget** | The **open-source stack** (Ollama + local tools) reduces reliance on paid APIs for core text and some visuals. |

The app is designed so **downstream outputs** (quiz, slides, etc.) can reuse the **same grounded context** as the Learn step, which keeps quizzes and decks tied to what you actually provided.

---

## Quick start

1. **Python API** (from repo root):

   ```bash
   python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env   # then edit .env with keys and provider settings
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Web UI** (optional):

   ```bash
   cd frontend && npm install && npm run dev
   ```

   The Vite dev server proxies API calls to the backend; see `frontend` config for the proxy target.

3. **API reference**: open `http://127.0.0.1:8000/docs` when the server is running.

Secrets belong in **`.env`** (gitignored), not in the repository. For a deeper walkthrough of flows and endpoints, see `FLOW_DOCUMENTATION.html` in this repo.

---

## Repository layout (short)

- `app/` — FastAPI backend (`/api/v1/...`), services (explanation, quiz, slides, video, audio, etc.).
- `frontend/` — React + Vite UI for the full lesson workflow.

---

*ClassroomAI — one chapter in; a whole lesson out.*
