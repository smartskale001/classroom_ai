# ClassroomAI - Complete Guide

## 🎯 What is ClassroomAI?

ClassroomAI is an **AI-powered educational content generator** that turns textbook chapters, PDFs, or screenshots into complete, ready-to-use lesson packages. Imagine uploading a single page from a textbook and getting back:

- ✅ **Clear explanations** of the topic
- ✅ **Quiz questions** based on the content
- ✅ **Presentation slides** (PowerPoint) you can teach from
- ✅ **Flashcards** for students to review
- ✅ **Audio narration** of the lessons
- ✅ **Illustrations or stock images** to visualize concepts
- ✅ **Infographics** for complex ideas
- ✅ **Short educational videos** (using various methods)
- ✅ **Mermaid diagrams** for processes and sequences

All from a **single source** – the chapter text, PDF, or images you provide.

---

## 💡 Why Would You Use This?

### For Teachers & Educators
- **Save Time**: Instead of spending hours creating materials in different tools, ClassroomAI generates everything at once.
- **Consistency**: Everything comes from the same source, so quizzes match the explanation, slides match the lesson.
- **Multiple Formats**: Students learn differently – some prefer reading, some prefer slides, some need audio or flashcards.
- **Less Typing**: Paste chapter text once, get 8+ different materials.

### For Students
- **Better Explanations**: AI explains the chapter in clear, simple language (can be in English, Hindi, or Roman Hindi).
- **Practice Materials**: Auto-generated quizzes help check understanding immediately.
- **Multiple Learning Styles**: Choose between reading, slides, audio, or flashcards.
- **Consistent Quality**: All materials cover the same content, no conflicting information.

### For Content Creators & Course Designers
- **Scale Quickly**: Build large course libraries faster.
- **Budget-Friendly**: Use free/open-source AI models instead of expensive cloud APIs.
- **Customizable**: Adjust difficulty, language, and format as needed.

---

## 🔧 How It's Made (Technical Overview)

### The Brain: AI Models

ClassroomAI uses **two types of AI**:

1. **Text Generation** (creates explanations, quizzes, etc.)
   - Cloud Option: **OpenAI GPT-4** (powerful but costs money)
   - Local Option: **Ollama** (free, runs on your computer)

2. **Image Generation** (creates illustrations and infographics)
   - Cloud Option: **OpenAI DALL-E** (through your OpenAI account)
   - Local Option: **Stable Diffusion WebUI** (free, runs locally)
   - Stock Option: **Pexels API** (free stock photos)

### The System: Python Backend + React Frontend

```
📱 React Frontend (What you see)
   ↓ (sends chapter text, PDF, or images)
⚙️ FastAPI Python Backend (does the work)
   ├─ Explain Module (generates explanations)
   ├─ Quiz Module (creates questions)
   ├─ Slides Module (builds PowerPoint decks)
   ├─ Flashcards Module (creates study cards)
   ├─ Audio Module (converts text to speech)
   ├─ Video Module (creates short clips)
   ├─ Illustration Module (finds or generates images)
   └─ Infographic Module (creates visual summaries)
   ↓ (sends back results)
📥 Results (download PowerPoint, listen to audio, etc.)
```

### The Flow: What Happens Inside

1. **User uploads** chapter text, PDF, or screenshots.
2. **Backend extracts** text (handles PDFs with tables, OCR for scanned images).
3. **LLM processes** the text and creates an explanation.
4. **Other modules reuse** this explanation to create:
   - Quiz questions
   - Slide outlines
   - Flashcard content
   - Video scripts
5. **Results are generated** and made available for download.

---

## 📊 Core Features Explained

### 1. **Learn (Explanation Module)**
- **Input**: Chapter text, PDF, or images of textbook pages.
- **Output**: Structured explanation in your chosen language.
- **Bonus**: Auto-generates Mermaid diagrams for processes.
- **Best For**: Understanding new topics.

**Example:**
- Input: "Chapter on Photosynthesis"
- Output: Clear explanation + diagram showing how light becomes energy.

### 2. **Quiz Module**
- **Input**: Chapter text + generated explanation.
- **Output**: Multiple-choice questions with correct answers and explanations.
- **Customizable**: Difficulty level, number of questions.
- **Best For**: Checking student understanding.

**Example:**
- Question: "Which part of the plant captures sunlight?"
- Options: A) Roots, B) Leaves, C) Stem, D) Flower
- Answer: B (with explanation).

### 3. **Slides Module**
- **Input**: Lesson explanation.
- **Output**: Ready-to-present PowerPoint deck with:
  - Hero title slide
  - Content slides with dark theme
  - Professional gradients or stock photos
  - Speaker notes with credits
- **Best For**: Teaching a class or presenting.

### 4. **Flashcards Module**
- **Input**: Lesson content.
- **Output**: Question-answer pairs for quick review.
- **Best For**: Self-study and memorization.

### 5. **Audio Module**
- **Input**: Text content.
- **Output**: MP3 file of spoken narration.
- **Voices Available**:
  - OpenAI TTS (if using OpenAI)
  - Edge TTS (free, high quality)
- **Best For**: Audio learners and commuters.

### 6. **Illustration Module**
- **Input**: Visual brief from the lesson.
- **Output**: Image (one of three methods):
  - AI-generated (OpenAI or Stable Diffusion)
  - Stock photo (Pexels)
- **Best For**: Making concepts visual.

### 7. **Infographic Module**
- **Input**: Topic and key points.
- **Output**: Single infographic-style image.
- **Best For**: Summarizing complex topics visually.

### 8. **Video Module** (Three Options)

**A. Local Animation** (Free, server-generated)
- Creates lightweight MP4 animations.
- No external API calls.
- Best for quick lesson summaries.

**B. OpenAI Sora** (Premium, high quality)
- Uses OpenAI's video generation API.
- Creates cinematic educational clips.
- Requires account with video API access.

**C. Pexels Stock Video** (Free)
- Searches Pexels stock video library.
- Downloads real footage by keywords.
- No generation needed, just retrieval.

---

## 🚀 Getting Started (Step-by-Step)

### Prerequisites (What You Need)

**Before installing**, you need:

1. **Python 3.9 or higher** installed on your computer.
2. **Git** (for cloning the repository).
3. **API Keys** (choose at least one):
   - **OpenAI**: Sign up at https://openai.com and create an API key (costs money per usage).
   - OR use **Ollama** (free, local LLM).
4. **Node.js** (for the web interface, optional).
5. **Optional APIs**:
   - Pexels API key for stock photos (free).
   - Stable Diffusion WebUI for local image generation.

---

This README is already comprehensive. Let me know if you want to add or modify any sections!