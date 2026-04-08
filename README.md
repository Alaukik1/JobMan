# 🎯 JobMan

> Autonomous AI-powered job hunting — from resume to ranked leads, fully local.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-green) ![Ollama](https://img.shields.io/badge/Ollama-local%20AI-purple) ![License](https://img.shields.io/badge/license-MIT-orange)

**No subscriptions. No cloud. Your resume stays on your machine.**

---

## What is this?

**JobMan** is a fully local, AI-powered job search agent. It reads your resume, autonomously hunts for relevant job postings across the web, semantically vets each one against your profile, and generates personalized application drafts — all running on your own hardware via [Ollama](https://ollama.com).

Built for job seekers who want intelligent automation without surrendering their data to third-party services.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **Smart Initialization** | Audits your RAM & GPU, recommends the optimal local model (`phi3` or `llama3`), and installs Ollama in one click. |
| 🕷️ **Autonomous Lead Hunting** | AI generates targeted search vectors from your resume, crawls Google, and deep-links into career pages automatically. |
| 🔬 **Neural Vetting** | Semantic comparison yields a **0–100% match score** and a written AI rationale for every discovered lead. |
| 🚫 **Intelligence Bouncer** | Real-time domain filter silently rejects low-signal sites (Reddit, Behance, etc.) before wasting AI cycles. |
| 📊 **Results Gallery** | Search, filter, and export your full lead history to Excel — a persistent dashboard across sessions. |
| ✍️ **AI Application Drafting** | One click generates a personalized cover letter or application draft for any vetted lead in your gallery. |

---

## 🏗️ Architecture

| Module | Role | Key Functions |
|---|---|---|
| `app.py` | Desktop shell — bootstraps PyWebView and FastAPI on port 8000 | `run_server()`, multiprocessing freeze support |
| `api.py` | REST communication hub — serves frontend, bridges backend | `resolve_path()`, `GET /api/models`, `POST /api/start` |
| `backend.py` | AI engine — orchestrates the full search and vetting pipeline | `run_pipeline()`, `ask_local_ai_to_match()`, `call_local_ai()` |
| `setup_manager.py` | Smart onboarding — hardware audit and Ollama installation | `audit_hardware()`, `recommend_model()`, `install_ollama_windows()` |
| `templates/index.html` | Frontend — polling UI, live bouncer log, gallery rendering | `checkSmartSetup()`, `renderResultsTable()`, `draftWithAI()` |

---

## ⚙️ Prerequisites

- **Python** 3.10 or higher
- **Windows** (primary target; Linux/macOS experimental)
- **8 GB RAM** minimum (16 GB recommended for `llama3`)
- **Ollama** — auto-installed on first run

---

## 🚀 Getting Started

```bash
git clone https://github.com/your-username/autoapply-ai
cd autoapply-ai
pip install -r requirements.txt
python app.py
```

On first launch, the **Smart Setup wizard** will audit your hardware, recommend a model, and offer to install Ollama automatically.

> **Tip:** To build a standalone `.exe`, run `pyinstaller app.spec`. The `resolve_path()` utility in `api.py` ensures all assets are found correctly inside the compiled binary.

---

## 🔄 How It Works

1. **Hardware audit** — `audit_hardware()` scans RAM and GPU to select `phi3` (light) or `llama3` (full).
2. **Resume ingestion** — your resume is loaded into a local memory profile via `GET /api/resume`.
3. **Query generation** — the AI synthesizes targeted search vectors from your experience and skills.
4. **Web crawling** — `run_pipeline()` scopes
