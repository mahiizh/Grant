"""Rerun the Grant latency baseline against a live isolated-store API.

The script waits for the background ingestion job to reach ``completed`` and
reports that ingest time separately from the upload response time.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

BASE = os.getenv("BASELINE_API", "http://127.0.0.1:8000/api/v1")
HEADERS = {"X-Dev-User": "alice"}
OUT = Path(os.getenv("BASELINE_OUT", r"C:\Users\mahil\AppData\Local\Temp\opencode"))

DOC_QUERIES = [
    "Which security controls are covered by the baseline document?",
    "How does the risk register record threats and residual risk?",
    "What happens during incident response and post-incident review?",
]
WEB_QUERIES = [
    "What is the current population of Tokyo?",
    "What is the capital of Mongolia?",
    "What is the tallest mountain in Africa?",
]
# Distinct from WEB_QUERIES so an exact-cache hit cannot hide web write-back or
# chunk selection. A per-run suffix prevents a previous probe's cache entry from
# short-circuiting the forced-web stage breakdown.
FORCED_WEB_QUERY_BASES = [
    "Who won the 2026 FIFA World Cup final and what was the score?",
    "What is the current population of Ulaanbaatar in 2026?",
    "What is the atomic number of tungsten?",
]

CONTENT = "\n\n".join(
    [
        "# ISO/IEC 27001 baseline document",
        "Information security management systems require documented controls, leadership commitment, risk assessment, and continual improvement.",
        "The audit team reviews access control, incident response, backups, encryption, vendor management, and employee awareness training.",
        "Management defines an information security policy and reviews it annually to preserve confidentiality, integrity, and availability.",
        "An internal audit verifies that remediation actions are tracked and that control owners provide evidence of operation.",
        "The risk register records threats, likelihood, impact, treatment decisions, residual risk, and approval by the risk owner.",
        "Incident response procedures define detection, triage, containment, eradication, recovery, and post-incident review.",
        "Access control requires unique user IDs, least privilege, periodic access review, and prompt revocation after role changes.",
        "Backup procedures require scheduled backups, restoration testing, secure storage, and documented recovery time objectives.",
        "Supplier agreements include confidentiality obligations, security requirements, service levels, and audit rights.",
        "The baseline doc is used only to measure ingest and retrieval latency during runtime refactoring.",
    ]
    * 4
)


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return round(ordered[idx], 3)


def summarize(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    return {
        "n": len(values),
        "p50": round(statistics.median(values), 3),
        "p95": p95(values),
        "max": round(max(values), 3),
    }


async def timed_health(client: httpx.AsyncClient) -> tuple[float, int]:
    started = time.perf_counter()
    try:
        response = await client.get(f"{BASE}/health/live", timeout=60.0)
        return (time.perf_counter() - started) * 1000.0, response.status_code
    except Exception:
        return (time.perf_counter() - started) * 1000.0, 0


async def upload_and_wait(
    client: httpx.AsyncClient, content: str, name: str
) -> dict[str, Any]:
    health: list[float] = []
    stop = False

    async def poll_health() -> None:
        while not stop:
            ms, _ = await timed_health(client)
            health.append(ms)
            await asyncio.sleep(0.05)

    poller = asyncio.create_task(poll_health())
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{BASE}/documents",
            headers=HEADERS,
            files={"file": (name, content.encode("utf-8"), "text/markdown")},
            timeout=180.0,
        )
        response_ms = (time.perf_counter() - started) * 1000.0
        payload = response.json()
        document_id = str(payload.get("document_id") or "")
        job_id = str(payload.get("job_id") or "")
        status = response.status_code

        status_payload: dict[str, Any] = {}
        ingest_wait_ms: float | None = None
        if document_id and response.status_code in (200, 202):
            status_started = time.perf_counter()
            deadline = status_started + 180.0
            while time.perf_counter() < deadline:
                status_response = await client.get(
                    f"{BASE}/documents/{document_id}/status",
                    headers=HEADERS,
                    timeout=30.0,
                )
                if status_response.status_code == 200:
                    status_payload = status_response.json()
                    job_status = str(status_payload.get("status") or "")
                    if job_status in ("completed", "failed"):
                        ingest_wait_ms = round(
                            (time.perf_counter() - status_started) * 1000.0, 2
                        )
                        break
                await asyncio.sleep(0.1)
    except Exception as exc:
        response_ms = (time.perf_counter() - started) * 1000.0
        payload = {"error": str(exc)}
        document_id = ""
        job_id = ""
        status = 0
        status_payload = {}
        ingest_wait_ms = None
    finally:
        stop = True
        await poller

    return {
        "response_ms": round(response_ms, 3),
        "status": status,
        "body": payload,
        "document_id": document_id,
        "job_id": job_id,
        "job_status": status_payload.get("status"),
        "server_ingest_ms": status_payload.get("ingest_ms"),
        "ingest_wait_ms": ingest_wait_ms,
        "health_during_ingest": summarize(health),
    }


async def ask(
    client: httpx.AsyncClient,
    query: str,
    policy: str,
    timeout: float = 120.0,
    force_web: bool = False,
) -> tuple[float, int, dict[str, Any]]:
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{BASE}/query",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"query": query, "answer_policy": policy, "force_web": force_web},
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - started) * 1000.0
        payload = response.json()
        return elapsed, response.status_code, {
            "query": query,
            "status": response.status_code,
            "is_cached": payload.get("is_cached"),
            "source_kind": payload.get("source_kind"),
            "strategy_used": payload.get("strategy_used"),
            "is_abstention": payload.get("is_abstention"),
            "error": payload.get("detail"),
            "stage_timings_ms": payload.get("stage_timings_ms", {}),
            "evidence_scores": [
                {
                    "chunk_id": item.get("chunk_id"),
                    "score": item.get("score"),
                    "method": item.get("retrieval_method"),
                }
                for item in (payload.get("evidence") or [])[:5]
            ],
            "web_source_count": len(payload.get("web_sources") or []),
        }
    except Exception as exc:
        return (time.perf_counter() - started) * 1000.0, 0, {
            "query": query,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def main() -> None:
    async with httpx.AsyncClient() as client:
        idle = []
        for _ in range(10):
            ms, _ = await timed_health(client)
            idle.append(ms)
            await asyncio.sleep(0.05)

        # A unique file name/content avoids the unchanged-document fast path.
        unique_name = f"baseline_worker_{int(time.time())}.md"
        upload_result = await upload_and_wait(client, CONTENT, unique_name)

        cache_query = "What controls does the ISO 27001 baseline document require?"
        await ask(client, cache_query, "grounded_only")
        cache_samples: list[float] = []
        cache_meta: list[dict[str, Any]] = []
        for _ in range(5):
            ms, status, meta = await ask(client, cache_query, "grounded_only")
            cache_samples.append(ms)
            cache_meta.append({"status": status, **meta})

        docs_samples: list[float] = []
        docs_meta: list[dict[str, Any]] = []
        for query in DOC_QUERIES:
            ms, status, meta = await ask(client, query, "grounded_only")
            docs_samples.append(ms)
            docs_meta.append({"status": status, **meta})

        web_samples: list[float] = []
        web_meta: list[dict[str, Any]] = []
        for query in WEB_QUERIES:
            ms, status, meta = await ask(client, query, "grounded_plus_web")
            web_samples.append(ms)
            web_meta.append({"status": status, **meta})

        forced_web_meta: list[dict[str, Any]] = []
        run_suffix = f"live web check {int(time.time())}"
        for base_query in FORCED_WEB_QUERY_BASES:
            query = f"{base_query} ({run_suffix})"
            ms, status, meta = await ask(
                client, query, "grounded_plus_web", force_web=True
            )
            forced_web_meta.append(
                {
                    "latency_ms": round(ms, 3),
                    "status": status,
                    "stage_timings_ms": meta.get("stage_timings_ms", {}),
                    **meta,
                }
            )

        result = {
            "idle_health_ms": summarize(idle),
            "upload": upload_result,
            "ask_cache_hit": {**summarize(cache_samples), "samples": cache_meta},
            "ask_docs": {**summarize(docs_samples), "samples": docs_meta},
            "ask_web": {**summarize(web_samples), "samples": web_meta},
            "ask_web_forced": {"samples": forced_web_meta},
        }
        OUT.mkdir(parents=True, exist_ok=True)
        target = OUT / "baseline_after_worker.json"
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
