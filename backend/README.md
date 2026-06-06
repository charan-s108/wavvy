---
title: Wavvy
emoji: 🎙️
colorFrom: yellow
colorTo: purple
sdk: docker
pinned: false
app_port: 7860
---

# Wavvy Backend

Real-time voice AI CCaaS platform — FastAPI + LiveKit Agents worker.

Two processes run inside this Space via supervisord:
- **API** — FastAPI on port 7860 (REST + WebSockets)
- **Worker** — LiveKit Agents worker (voice pipeline per call)

See the [main repository](https://github.com/charansrinivas108/wavvy) for full documentation.
