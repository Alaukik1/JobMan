<div align="center">

<img src="https://img.icons8.com/fluency/96/target.png" width="80" alt="JobMan logo"/>

# JobMan

**Autonomous AI-powered job hunting — from resume to ranked leads, fully local.**

![Python](https://img.shields.io/badge/Python-3.10+-4584b6?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local%20AI-7c3aed?style=flat-square)
![PyWebView](https://img.shields.io/badge/PyWebView-Desktop-0ea5e9?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)
![Open Source](https://img.shields.io/badge/Open%20Source-%E2%9D%A4-ef4444?style=flat-square)

*No subscriptions. No cloud. Your resume stays on your machine.*

</div>

---

## What is JobMan?

**JobMan** is a fully local, AI-powered job search agent. It reads your resume, autonomously hunts for relevant job postings across the web, semantically vets each one against your profile, and generates personalized application drafts — all running on your own hardware via [Ollama](https://ollama.com).

> Built for job seekers who want intelligent automation without surrendering their data to third-party services.

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🧠 Smart Initialization
Audits your RAM & GPU, recommends the optimal local model (`phi3` or `llama3`), and handles one-click installation of the Ollama engine.

</td>
<td width="50%" valign="top">

### 🕷️ Autonomous Lead Hunting
AI generates targeted search vectors from your resume, crawls Google, and deep-links into career pages automatically.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔬 Neural Vetting
Semantic comparison yields a **0–100% match score** and a written AI rationale for every discovered lead.

</td>
<td width="50%" valign="top">

### 🚫 Intelligence Bouncer
Real-time domain filter silently rejects low-signal sites (Reddit, Behance, etc.) before they consume AI processing time.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 📊 Results Gallery
Search, filter, and export your full lead history directly to Excel — a persistent dashboard across sessions.

</td>
<td width="50%" valign="top">

### ✍️ AI Application Drafting
One click generates a personalized cover letter or application draft for any vetted lead in your gallery.

</td>
</tr>
</table>

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

<table>
<tr>
<td>🐍 <b>Python</b> 3.10+</td>
<td>🪟 <b>Windows</b> (Linux/macOS experimental)</td>
</tr>
<tr>
<td>💾 <b>8 GB RAM</b> min (16 GB for llama3)</td>
<td>🤖 <b>Ollama</b> — auto-installed on first run</td>
</tr>
</table>

---

## 🚀 Getting Started

```bash
git clone https://github.com/Alaukik1/JobMan
cd JobMan
pip install -r requirements.txt
python app.py
```

On first launch, the **Smart Setup wizard** will audit your hardware, recommend a model, and offer to install Ollama automatically.

> 💡 **Tip:** To build a standalone `.exe`, run `pyinstaller app.spec`. The `resolve_path()` utility in `api.py` ensures all assets are found correctly inside the compiled binary.

---

## 🔄 How It Works

| Step | What happens |
|------|-------------|
| 1️⃣ Hardware audit | `audit_hardware()` scans RAM & GPU to select `phi3` (light) or `llama3` (full) |
| 2️⃣ Resume ingestion | Your resume is loaded into a local memory profile via `GET /api/resume` |
| 3️⃣ Query generation | The AI synthesizes targeted search vectors from your experience and skills |
| 4️⃣ Web crawling | `run_pipeline()` scopes Google results and deep-crawls into career pages |
| 5️⃣ Bouncer filter | Low-signal domains are rejected in real time before consuming AI resources |
| 6️⃣ Semantic vetting | `ask_local_ai_to_match()` scores each job page against your resume (0–100%) |
| 7️⃣ Gallery storage | Results are written to Excel and surfaced in the lead dashboard |
| 8️⃣ Draft generation | Click any lead to generate a tailored cover letter via `draftWithAI()` |

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

```bash
# Suggested branch naming
git checkout -b feat/your-feature-name
git checkout -b fix/your-bug-description
```

---

## 📄 License

MIT — see [`LICENSE`](./LICENSE) for details.

---

<div align="center">

Built with ❤️ using Python · FastAPI · PyWebView · Ollama

*Open Source Forever*

</div>
