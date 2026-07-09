<div align="center">
  <img src="https://raw.githubusercontent.com/Selimjerbi66/Cyber-Ataraxia-ValeriA/refs/heads/main/ValeriA/CA_logo.png" width="180" alt="ValeriA Logo"/>
  <h1>Cyber Ataraxia — ValeriA</h1>

  <p>
    A self-hosted, privacy-first alternative to Open WebUI<br/>
    Part of the <a href="https://github.com/Selimjerbi66/CyberAtaraxia-Suite">CyberAtaraxia Suite</a> — developed by <strong>Selim JERBI</strong>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Version-0.1-orange?style=for-the-badge" />
    <img src="https://img.shields.io/badge/Status-Prototype-orange?style=for-the-badge" />
    <img src="https://img.shields.io/badge/Language-French%20-blue?style=for-the-badge" />
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
    <img src="https://img.shields.io/badge/Runs%20on-Ollama-black?style=for-the-badge" />
    <img src="https://img.shields.io/badge/Search-SearXNG-3050ff?style=for-the-badge" />
  </p>
</div>

---

## 📋 What is ValeriA?

**ValeriA** is a free, open-source, self-hosted chat interface for local LLMs served through **Ollama** — built as a lightweight, privacy-first alternative to **Open WebUI**.

It gives locally-hosted models (such as **Gemma** and **Llama**) real-time web access without ever sending your prompts or data to a third-party cloud service. Every request, every search, and every model response stays on your own machine.

> ⚠️ **This is currently a prototype.** ValeriA is functional but under active development — expect rough edges, incomplete features, and breaking changes between versions. It is not yet recommended for production or mission-critical use.

---

## 🧠 How it works

ValeriA follows a simple, transparent pipeline — no black box, no hidden cloud calls:

```
Your question
     │
     ▼
 SearXNG  ──────────▶  web result links
     │
     ▼
 Fetch & scrape the linked pages (with snippet fallback)
     │
     ▼
 Question + retrieved pages  ──────────▶  Ollama (Gemma / Llama / any local model)
     │
     ▼
 Streamed answer, displayed live in the chat
```

Everything after the initial SearXNG query — scraping, prompting, inference — happens locally, on the machine hosting ValeriA.

---

## ✨ Features

- 💬 **Multiple isolated chats** — create, rename, pin, and delete conversations independently
- 🌐 **Live web search** via SearXNG (or any compatible search engine, configurable)
- 📄 **Full page scraping** with automatic snippet fallback if a page fails to load
- 🔀 **Model selection per chat** — pick any model available in your Ollama instance
- ⚡ **Streaming responses** — answers appear token by token, like ChatGPT/Claude
- 📝 **Full Markdown rendering** with syntax-highlighted code blocks
- 🔁 **Regenerate** a response with one click
- 👍👎 **Feedback** on individual messages
- 🔍 **Search across chat history**
- 📤 **Export conversations** to Markdown
- 🎙️ **Voice input** (browser-based, no external API)
- 🔐 **Password-protected access**, with a CLI recovery procedure if you lose it
- 💾 **SQLite persistence** — conversations and settings survive container restarts
- 🐳 **Single Docker container** — deploys next to Ollama and SearXNG with no extra infrastructure

---

## 📁 Repository Structure

```
Cyber-Ataraxia-ValeriA/
└── ValeriA/
    ├── frontend/       ← Web interface (HTML/CSS/JS)
    ├── backend/        ← FastAPI application (API, scraping, Ollama/SearXNG bridge, SQLite)
    └── Dockerfile      ← Builds the ValeriA container image
```

---

## 🚀 Getting Started

### Prerequisites

- A Linux/Windows/macOS machine (ideally with an NVIDIA GPU for reasonable inference speed)
- [Docker](https://docs.docker.com/engine/install/) installed and running
- [Ollama](https://ollama.com/) installed
- A running [SearXNG](https://docs.searxng.org/) instance (also deployable via Docker)

### 1. Install Ollama and pull your models

```bash
curl -fsSL https://ollama.com/install.sh | sh

ollama pull gemma3:4b
ollama pull llama3.1:8b
```

### 2. Deploy SearXNG

```bash
docker run -d \
  --name searxng \
  --network host \
  -v searxng-data:/etc/searxng \
  --restart unless-stopped \
  searxng/searxng
```

> Make sure `json` is enabled under `search.formats` in your SearXNG `settings.yml`, otherwise ValeriA won't be able to parse its results.

### 3. Clone the ValeriA repository

```bash
git clone https://github.com/Selimjerbi66/Cyber-Ataraxia-ValeriA.git
cd Cyber-Ataraxia-ValeriA/ValeriA
```

### 4. Build and run ValeriA

```bash
docker build -t valeria .

docker run -d \
  --name valeria \
  --network host \
  -v valeria_data:/data \
  --restart unless-stopped \
  valeria
```

### 5. Open it in your browser

```
http://<your-machine-ip>:8090
```

On first launch, ValeriA will ask you to create a password before giving you access to the chat.

---

## ⚙️ Configuration

All of the following are configurable directly from the ValeriA settings panel — no need to touch the container or restart it:

| Setting | Description |
|---|---|
| Ollama URL | Address of your Ollama instance (default: `http://localhost:11434`) |
| Default model | Which local model to use for new chats |
| Search engine URL | Your SearXNG (or other) search endpoint |
| Number of sources | How many web results to fetch per query (default: 10) |
| Scraping mode | Full page scraping, snippets only, or hybrid with fallback |

---

## 🔁 Updating ValeriA

Your data (conversations, password, settings) lives in the `valeria_data` Docker volume and survives updates:

```bash
cd Cyber-Ataraxia-ValeriA
git pull

cd ValeriA
docker stop valeria
docker rm valeria
docker build -t valeria .
docker run -d --name valeria --network host -v valeria_data:/data --restart unless-stopped valeria
```

---

## 🔑 Forgot your password?

Run the recovery script directly inside the running container:

```bash
docker exec -it valeria python reset_password.py
```

---

## 🛠️ Tech Stack

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![FastAPI](https://img.shields.io/badge/fastapi-109989?style=for-the-badge&logo=FASTAPI&logoColor=white)
![SQLite](https://img.shields.io/badge/sqlite-%2307405e.svg?style=for-the-badge&logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![JavaScript](https://img.shields.io/badge/javascript-%23323330.svg?style=for-the-badge&logo=javascript&logoColor=%23F7DF1E)

Fonts: **Inter** · **JetBrains Mono**

---

## ⚖️ Disclaimer

ValeriA is an **independent, non-commercial, open-source project**, currently in **prototype stage**. It is provided as-is, with no warranty or guarantee of stability.

ValeriA is not affiliated with, endorsed by, or sponsored by Ollama, SearXNG, Google (Gemma), or Meta (Llama). All trademarks belong to their respective owners.

---

## 👤 Author

**Selim JERBI** — AI Engineer

<p>
  <a href="https://linkedin.com/in/selim-jerbi-b355a0202">
    <img src="https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" />
  </a>
  &nbsp;
  <a href="mailto:Selimjerbi66@gmail.com">
    <img src="https://img.shields.io/badge/Gmail-Contact-D14836?style=for-the-badge&logo=gmail&logoColor=white" />
  </a>
  &nbsp;
  <a href="https://github.com/Selimjerbi66/CyberAtaraxia-Suite">
    <img src="https://img.shields.io/badge/CyberAtaraxia%20Suite-View%20all%20tools-1a56db?style=for-the-badge&logo=github&logoColor=white" />
  </a>
</p>

---

## 📜 License

This project is part of the **CyberAtaraxia Suite** by Selim JERBI. License to be defined — stay tuned.

---

<div align="center">
  <sub>Cyber Ataraxia — ValeriA · Part of the CyberAtaraxia Suite · Open Source · Built by Selim JERBI</sub>
</div>
