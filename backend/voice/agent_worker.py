"""
LiveKit Agents worker — entry point for the Wavvy voice agent.

Usage:
    python -m voice.agent_worker dev     # local dev (auto-reloads)
    python -m voice.agent_worker start   # production

WorkerOptions registers this process with LiveKit Cloud. When a room is
created (POST /api/livekit/start-call), LiveKit auto-dispatches a job here.
Each job runs in an isolated subprocess via prewarm pool.

Production tuning:
  load_threshold=0.80  — stop accepting jobs at 80% process capacity
  job_memory_limit_mb=512 — kill runaway subprocesses at 512 MB RSS
  drain_timeout=300    — 5 min graceful shutdown (covers avg call length)
  num_idle_processes=2 — keep 2 warm subprocesses to eliminate cold start
"""
import os
# Disable OpenTelemetry OTLP export before any LiveKit/OTel import.
# LiveKit Agents auto-detects LiveKit Cloud URLs and tries to POST traces/metrics
# to the OTLP endpoint. When the endpoint is rate-limiting or unreachable, the
# BatchSpanProcessor worker thread blocks for up to 90s (30s × 3 providers),
# which exceeds the LiveKit admin's ping/pong deadline and drops the call.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import logging

from livekit.agents import WorkerOptions, cli

from config import settings
from voice.agent_session import entrypoint, prewarm

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            # LiveKit credentials — passed explicitly so pydantic-settings .env is used
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            # Production resource limits
            job_memory_limit_mb=512,      # OOM-kill runaway subprocesses
            load_threshold=0.80,          # reject new jobs before overload
            drain_timeout=300,            # 5 min grace on SIGTERM
            num_idle_processes=2,         # warm pool: first-call latency ~0
        )
    )
