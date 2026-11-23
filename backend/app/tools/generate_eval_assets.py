"""Deterministic generator for the scaled synthetic corpus and golden rows.

Item 6 needs enough documents and questions for intervals to mean something, plus
the hardness that makes retrieval interesting: near-duplicate distractors,
conflicting document versions, and cross-team ownership chains. Everything here
is generated from a fixed seed and committed, so the corpus and the golden chunk
ids are reproducible without network access or a live database.

Run from the repository root:

    uv run --directory backend python -m app.tools.generate_eval_assets

The command rewrites ``corpus/synthetic/`` and
``evals/golden/generated_questions.jsonl``. It never touches the hand-authored
documents under ``corpus/``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.core.acl import ACLScope
from app.ingestion.chunking import chunk_parsed_document
from app.ingestion.corpus import iter_corpus_files
from app.ingestion.parse import parse_markdown

REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = REPO_ROOT / "corpus"
SYNTHETIC_DIR = CORPUS_DIR / "synthetic"
GOLDEN_PATH = REPO_ROOT / "evals" / "golden" / "generated_questions.jsonl"
MANIFEST_PATH = SYNTHETIC_DIR / "manifest.json"

GENERATOR = "app.tools.generate_eval_assets"
SEED = 20260412

# Phase C row additions from the preregistered Phase A power table (STATUS §0.8).
# The hand-authored set already contributes 3 test `fact` rows and 2 test
# `multi_hop` rows, so these generated counts lift the totals to n_needed.
PHASE_C_FACT_TEST_ROWS = 45
PHASE_C_FACT_CLUSTERS = 8
PHASE_C_MULTI_HOP_TEST_ROWS = 201
PHASE_C_MULTI_HOP_CLUSTERS = 19


@dataclass(frozen=True)
class Team:
    slug: str
    name: str
    lead: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class Service:
    name: str
    slug: str
    team: str
    p99_ms: int
    error_budget_pct: float
    dependency: str
    owner: str
    tier: int
    runbook: str
    version: str
    deployed: str


TEAMS: tuple[Team, ...] = (
    Team(
        "data-platform",
        "Data Platform",
        "Alice Chen",
        ("Alice Chen", "Priya Nair", "Tomas Vidal"),
    ),
    Team(
        "payments",
        "Payments",
        "Elena Rostova",
        ("Elena Rostova", "Marcus Webb", "Sofia Lind"),
    ),
    Team(
        "core-banking",
        "Core Banking",
        "Dave Miller",
        ("Dave Miller", "Nadia Okafor", "Kenji Sato"),
    ),
    Team(
        "sre",
        "Site Reliability Engineering",
        "Bob Kumar",
        ("Bob Kumar", "Grace Liu", "Omar Haddad"),
    ),
    Team(
        "security",
        "Security",
        "Maya Singh",
        ("Maya Singh", "Liam Foster", "Anika Rao"),
    ),
    Team(
        "ml-platform",
        "ML Platform",
        "Noah Kim",
        ("Noah Kim", "Iris Novak", "Pablo Reyes"),
    ),
    Team(
        "customer-support",
        "Customer Support",
        "Zoe Bennett",
        ("Zoe Bennett", "Hugo Alves", "Mei Tan"),
    ),
    Team(
        "treasury",
        "Treasury",
        "Ravi Shah",
        ("Ravi Shah", "Clara Moreau", "Jonas Berg"),
    ),
    Team(
        "risk",
        "Risk",
        "Amara Diallo",
        ("Amara Diallo", "Felix Braun", "Sana Iqbal"),
    ),
    Team(
        "compliance",
        "Compliance",
        "Helena Voss",
        ("Helena Voss", "Diego Marin", "Ruth Cohen"),
    ),
)

SERVICE_NAMES: dict[str, tuple[str, ...]] = {
    "data-platform": (
        "EventStream",
        "OutboxWorker",
        "SchemaRegistry",
        "IngestionPipeline",
        "Reconciler",
        "EmbeddingService",
    ),
    "payments": (
        "PaymentGateway",
        "FraudScorer",
        "SettlementEngine",
        "CardVault",
        "RefundService",
        "TokenizationAPI",
    ),
    "core-banking": (
        "LedgerCore",
        "AccountService",
        "InterestEngine",
        "StatementGenerator",
        "FxRateService",
        "ReconciliationJob",
    ),
    "sre": (
        "AlertRouter",
        "IncidentBot",
        "CapacityPlanner",
        "SloEvaluator",
        "OnCallScheduler",
        "ChaosRunner",
    ),
    "security": (
        "AccessBroker",
        "SecretRotator",
        "AuditLogger",
        "ThreatScanner",
        "PolicyEngine",
        "KeyManager",
    ),
    "ml-platform": (
        "FeatureStore",
        "ModelRegistry",
        "TrainingOrchestrator",
        "InferenceGateway",
        "DriftMonitor",
        "VectorIndexer",
    ),
    "customer-support": (
        "TicketRouter",
        "KnowledgeBase",
        "SentimentAnalyzer",
        "EscalationEngine",
        "ChatGateway",
        "MacroService",
    ),
    "treasury": (
        "CashForecast",
        "LiquidityMonitor",
        "FxHedging",
        "PaymentRail",
        "BalanceAggregator",
        "SweepEngine",
    ),
    "risk": (
        "CreditScorer",
        "ExposureCalculator",
        "LimitEngine",
        "StressTester",
        "AlertCorrelator",
        "ModelValidator",
    ),
    "compliance": (
        "RetentionManager",
        "ConsentRegistry",
        "AuditExporter",
        "RegulatoryReporter",
        "SanctionsScreener",
        "EvidenceVault",
    ),
}

# Deliberately absent from the corpus. Unanswerable rows use these names so a
# lexical near-match cannot accidentally make the question answerable.
ABSENT_NAMES: tuple[str, ...] = (
    "QuantumLedger",
    "HyperCache",
    "OrbitQueue",
    "NebulaVault",
    "PhotonIndex",
    "TachyonBus",
    "AuroraScheduler",
    "ZephyrGateway",
    "HelixRegistry",
    "PulsarRouter",
    "VertexScanner",
    "CascadeEngine",
    "OnyxMonitor",
    "LumenStore",
    "CobaltBroker",
    "MosaicPlanner",
    "QuasarEvaluator",
    "TundraPipeline",
    "EmberLedger",
    "SolsticeService",
    "GraniteQueue",
    "BeaconAPI",
    "HarborDB",
    "CometWorker",
    "SummitCache",
    "FalconIndex",
    "WillowGateway",
    "CedarEngine",
    "MapleStore",
    "AspenRouter",
)

# Phase C template families. Each cluster id is one family, so a cluster
# bootstrap resamples phrasings together instead of treating near-duplicates as
# independent rows.
PHASE_C_FACT_PROBES: tuple[tuple[str, str, str], ...] = (
    ("gen_fact_p99_direct", "What p99 latency target is documented for {name}?", "p99"),
    ("gen_fact_sla_restatement", "State the p99 SLA for {name}.", "p99"),
    ("gen_fact_error_budget", "What is the documented error budget for {name}?", "budget"),
    ("gen_fact_monthly_budget", "What monthly error budget applies to {name}?", "budget"),
    ("gen_fact_sla_pair", "Give the p99 target and error budget for {name}.", "both"),
    (
        "gen_fact_latency_target",
        "According to its SLA, what latency target does {name} use?",
        "p99",
    ),
    ("gen_fact_budget_lookup", "Find the error budget listed for {name}.", "budget"),
    ("gen_fact_p99_lookup", "Find the p99 latency figure for {name}.", "p99"),
)

PHASE_C_MULTI_HOP_TEMPLATES: tuple[str, ...] = (
    "Which team owns {dependency}, the service that {service} depends on?",
    "Which team is responsible for {dependency}, an upstream dependency of {service}?",
    "Who owns the upstream service {dependency} used by {service}?",
    "What team maintains the dependency {dependency} of {service}?",
    "Which team's scope includes {dependency}, which {service} relies on?",
    "Find the owning team for {dependency} in {service}'s dependency chain.",
    "When {service} calls {dependency}, which team owns that service?",
    "Who is accountable for {dependency}, upstream of {service}?",
    "Which team should be paged for {dependency}, the dependency of {service}?",
    "What team owns the service {service} depends on for upstream data?",
    "Identify the owner of {dependency} as used by {service}.",
    "Which team is listed as the owner of {dependency} in {service}'s upstream path?",
    "For the {service} dependency chain, which team owns {dependency}?",
    "Which engineering team owns {dependency}, the upstream service of {service}?",
    "Who owns the service on which {service} depends?",
    "Which team's directory covers {dependency}, a dependency of {service}?",
    "What is the owning team of {dependency} for {service}?",
    "Trace {service}'s dependency to {dependency}: which team owns it?",
    "Which team has operational ownership of {dependency} for {service}?",
)


def _slug(name: str) -> str:
    return name.lower()


def _build_services() -> tuple[Service, ...]:
    flat: list[Service] = []
    for team_index, team in enumerate(TEAMS):
        for local_index, name in enumerate(SERVICE_NAMES[team.slug]):
            flat.append(
                Service(
                    name=name,
                    slug=_slug(name),
                    team=team.slug,
                    p99_ms=20 + ((team_index * 13 + local_index * 7) % 120),
                    error_budget_pct=round(0.1 + ((team_index + local_index) % 5) * 0.1, 1),
                    dependency="",
                    owner=team.members[local_index % len(team.members)],
                    tier=1 if local_index % 3 == 0 else 2,
                    runbook=f"RB-{team_index + 1:02d}{local_index + 1:02d}",
                    version="v2" if local_index % 5 == 0 else "v1",
                    deployed=f"2026-{(local_index % 6) + 1:02d}-{(team_index + 3):02d}",
                )
            )
    # Cross-team chain: each service depends on a service seven positions later,
    # which always lands in a different team because teams are six services wide.
    with_dependencies: list[Service] = []
    for index, service in enumerate(flat):
        target = flat[(index + 7) % len(flat)]
        with_dependencies.append(
            Service(
                name=service.name,
                slug=service.slug,
                team=service.team,
                p99_ms=service.p99_ms,
                error_budget_pct=service.error_budget_pct,
                dependency=target.name,
                owner=service.owner,
                tier=service.tier,
                runbook=service.runbook,
                version=service.version,
                deployed=service.deployed,
            )
        )
    return tuple(with_dependencies)


SERVICES: tuple[Service, ...] = _build_services()
SERVICES_BY_NAME: dict[str, Service] = {service.name: service for service in SERVICES}
TEAMS_BY_SLUG: dict[str, Team] = {team.slug: team for team in TEAMS}


def _frontmatter(doc_id: str, title: str, acl_scope: str, valid_from: str) -> str:
    return (
        "---\n"
        f"title: {title}\n"
        f"doc_id: {doc_id}\n"
        f"acl_scope: {acl_scope}\n"
        f"valid_from: {valid_from}\n"
        "source_tier: 1\n"
        "---\n\n"
    )


def _team_doc(team: Team) -> str:
    services = [s for s in SERVICES if s.team == team.slug]
    lines = [
        _frontmatter(
            f"doc_team_{team.slug}",
            f"{team.name} Team Directory",
            team.slug,
            "2026-01-05T00:00:00Z",
        ),
        f"# {team.name} Team Directory\n\n",
        f"The {team.name} team operates {len(services)} production services for the GraphRAG lab.\n\n",
        "## Team Overview\n",
        f"The {team.name} team is led by {team.lead}. ",
        f"Its members are {', '.join(team.members)}.\n\n",
        "## Service Ownership\n",
    ]
    for service in services:
        lines.append(f"- {service.name} is owned by the {team.name} team.\n")
    lines.extend(
        [
            "\n## Escalation\n",
            f"Escalate to {team.lead} through #team-{team.slug} for any {team.name} incident.\n",
        ]
    )
    return "".join(lines)


def _service_doc(service: Service) -> str:
    team = TEAMS_BY_SLUG[service.team]
    return "".join(
        [
            _frontmatter(
                f"doc_service_{service.slug}",
                f"{service.name} Service Specification",
                service.team,
                "2026-02-01T00:00:00Z",
            ),
            f"# {service.name} Service Specification\n\n",
            f"{service.name} is a Tier {service.tier} production service in the GraphRAG lab.\n\n",
            "## Overview\n",
            f"{service.name} is owned by the {team.name} team. ",
            f"The service owner is {service.owner}.\n\n",
            "## SLA\n",
            f"{service.name} targets a p99 latency of {service.p99_ms}ms and an error budget of ",
            f"{service.error_budget_pct}% per 30 days.\n\n",
            "## Dependencies\n",
            f"{service.name} depends on {service.dependency} for its upstream data path.\n\n",
            "## Runbook\n",
            f"Runbook {service.runbook} covers {service.name}.\n\n",
            "## Change Log\n",
            f"Version {service.version} of {service.name} was deployed on {service.deployed}.\n",
        ]
    )


def _runbook_doc(service: Service) -> str:
    team = TEAMS_BY_SLUG[service.team]
    return "".join(
        [
            _frontmatter(
                f"doc_runbook_{service.slug}",
                f"Runbook {service.runbook} for {service.name}",
                service.team,
                "2026-02-10T00:00:00Z",
            ),
            f"# Runbook {service.runbook} for {service.name}\n\n",
            f"This runbook is the operational procedure for {service.name}.\n\n",
            "## Purpose\n",
            f"Runbook {service.runbook} is the primary operational procedure for {service.name}.\n\n",
            "## Escalation\n",
            f"If {service.name} breaches its p99 target of {service.p99_ms}ms, page {service.owner} ",
            f"and the {team.name} team.\n\n",
            "## Verification\n",
            f"Verify {service.dependency} is healthy before declaring {service.name} recovered.\n",
        ]
    )


def _sla_version_docs(service: Service) -> tuple[str, str, str]:
    team = TEAMS_BY_SLUG[service.team]
    old_p99 = service.p99_ms + 15
    old_budget = round(service.error_budget_pct + 0.2, 1)
    mirror_p99 = old_p99 + 1

    v1 = "".join(
        [
            _frontmatter(
                f"doc_sla_{service.slug}_v1",
                f"{service.name} SLA v1",
                service.team,
                "2026-01-01T00:00:00Z",
            ).replace("source_tier: 1\n", "source_tier: 1\nvalid_to: 2026-03-01T00:00:00Z\n"),
            f"# {service.name} SLA v1\n\n",
            f"This agreement governed {service.name} before the March 2026 revision.\n\n",
            "## Scope\n",
            f"This agreement covers {service.name} and the {team.name} team.\n\n",
            "## Latency Target\n",
            f"Under v1, {service.name} targets a p99 latency of {old_p99}ms.\n\n",
            "## Error Budget\n",
            f"Under v1, the monthly error budget is {old_budget}%.\n",
        ]
    )

    v2 = "".join(
        [
            _frontmatter(
                f"doc_sla_{service.slug}_v2",
                f"{service.name} SLA v2",
                service.team,
                "2026-03-01T00:00:00Z",
            ),
            f"# {service.name} SLA v2\n\n",
            f"This agreement supersedes v1 for {service.name} from March 2026 onward.\n\n",
            "## Scope\n",
            f"This agreement covers {service.name} and the {team.name} team.\n\n",
            "## Latency Target\n",
            f"Under v2, {service.name} targets a p99 latency of {service.p99_ms}ms.\n\n",
            "## Error Budget\n",
            f"Under v2, the monthly error budget is {service.error_budget_pct}%.\n",
        ]
    )

    mirror = "".join(
        [
            _frontmatter(
                f"doc_sla_{service.slug}_v1_mirror",
                f"{service.name} SLA v1 (audit mirror)",
                service.team,
                "2026-01-01T00:00:00Z",
            ).replace("source_tier: 1\n", "source_tier: 3\nvalid_to: 2026-03-01T00:00:00Z\n"),
            f"# {service.name} SLA v1 (audit mirror)\n\n",
            "This mirror is retained for audit only and is superseded by v2.\n\n",
            "## Scope\n",
            f"This agreement covers {service.name} and the {team.name} team.\n\n",
            "## Latency Target\n",
            f"Under v1, {service.name} targets a p99 latency of {mirror_p99}ms.\n\n",
            "## Error Budget\n",
            f"Under v1, the monthly error budget is {old_budget}%.\n",
        ]
    )
    return v1, v2, mirror


def _incident_doc(service: Service, index: int) -> str:
    team = TEAMS_BY_SLUG[service.team]
    incident_id = f"INC-2026-{index + 10:02d}"
    duration = 18 + (index * 11) % 90
    cause = "connection-pool exhaustion" if index % 2 == 0 else "stale configuration rollout"
    return "".join(
        [
            _frontmatter(
                f"doc_incident_{service.slug}",
                f"{incident_id} Postmortem for {service.name}",
                service.team,
                "2026-04-12T00:00:00Z",
            ),
            f"# {incident_id} Postmortem for {service.name}\n\n",
            f"{incident_id} is the postmortem for a production incident affecting {service.name}.\n\n",
            "## Summary\n",
            f"{incident_id} affected {service.name} for {duration} minutes.\n\n",
            "## Root Cause\n",
            f"The root cause was {cause} in {service.dependency}.\n\n",
            "## Remediation\n",
            f"The {team.name} team restored {service.name} by rolling back {service.dependency}.\n",
        ]
    )


def _scope_for(raw_scope: str | None) -> ACLScope:
    if raw_scope and raw_scope.lower() != "public":
        return ACLScope.restricted(
            allowed_roles=frozenset([raw_scope]),
            allowed_groups=frozenset([raw_scope]),
        )
    return ACLScope.public()


def _chunk_ids_by_heading(content: str, source_path: str) -> dict[str, str]:
    parsed = parse_markdown(content, source_path=source_path)
    chunks = chunk_parsed_document(
        parsed,
        source_path,
        _scope_for(parsed.metadata.get("acl_scope")),
    )
    return {str(chunk.metadata.get("heading", "")): chunk.chunk_id for chunk in chunks}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_corpus() -> list[tuple[str, str]]:
    """Return ``(doc_id, content)`` for every generated document without writing."""
    documents: list[tuple[str, str]] = []

    for team in TEAMS:
        documents.append((f"doc_team_{team.slug}", _team_doc(team)))

    for service in SERVICES:
        documents.append((f"doc_service_{service.slug}", _service_doc(service)))
        documents.append((f"doc_runbook_{service.slug}", _runbook_doc(service)))

    for index_number, service in enumerate(SERVICES):
        if index_number % 6 == 0:
            v1, v2, mirror = _sla_version_docs(service)
            documents.append((f"doc_sla_{service.slug}_v1", v1))
            documents.append((f"doc_sla_{service.slug}_v2", v2))
            documents.append((f"doc_sla_{service.slug}_v1_mirror", mirror))

    for index_number, service in enumerate(SERVICES):
        if index_number % 6 == 3:
            documents.append(
                (f"doc_incident_{service.slug}", _incident_doc(service, index_number // 6))
            )

    return documents


def generate_corpus() -> dict[str, dict[str, str]]:
    """Write the generated corpus and return ``doc_id -> heading -> chunk_id``."""
    if SYNTHETIC_DIR.exists():
        for path in sorted(SYNTHETIC_DIR.glob("*.md")):
            path.unlink()

    index: dict[str, dict[str, str]] = {}
    for doc_id, content in build_corpus():
        source_path = f"corpus/synthetic/{doc_id}.md"
        _write(SYNTHETIC_DIR / f"{doc_id}.md", content)
        index[doc_id] = _chunk_ids_by_heading(content, source_path)

    return index


def _row(
    row_id: str,
    category: str,
    cluster_id: str,
    split: str,
    query: str,
    expected_answer: str | None,
    expected_doc_ids: list[str],
    expected_chunk_ids: list[str],
    expected_entities: list[str],
    optimal_strategy: str,
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": row_id,
        "category": category,
        "cluster_id": cluster_id,
        "split": split,
        "query": query,
        "expected_answer": expected_answer,
        "expected_doc_ids": expected_doc_ids,
        "expected_chunk_ids": expected_chunk_ids,
        "expected_entities": expected_entities,
        "expected_path": None,
        "optimal_strategy": optimal_strategy,
    }
    payload.update(extra)
    return payload


def _splits(count: int, test_count: int) -> list[str]:
    return ["test"] * test_count + ["dev"] * (count - test_count)


def _fact_rows(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    versioned = [service for service in SERVICES if SERVICES.index(service) % 6 == 0]
    standard = [service for service in SERVICES if service not in versioned]

    fact_services = standard[:20] + versioned[:10]
    splits = _splits(len(fact_services), 20)

    for position, (service, split) in enumerate(zip(fact_services, splits, strict=True)):
        if service in versioned:
            doc_id = f"doc_sla_{service.slug}_v2"
            heading = "Latency Target"
            answer = f"Under v2, {service.name} targets a p99 latency of {service.p99_ms}ms."
            query = f"Under the current v2 agreement, what p99 latency does {service.name} target?"
        else:
            doc_id = f"doc_service_{service.slug}"
            heading = "SLA"
            answer = (
                f"{service.name} targets a p99 latency of {service.p99_ms}ms and an error "
                f"budget of {service.error_budget_pct}% per 30 days."
            )
            query = f"What is the p99 latency SLA for {service.name}?"
        rows.append(
            _row(
                f"gen_fact_{position + 1:03d}",
                "fact",
                "gen_fact_sla_v2" if service in versioned else "gen_fact_sla",
                split,
                query,
                answer,
                [doc_id],
                [index[doc_id][heading]],
                [service.name, f"{service.p99_ms}ms"],
                "vector",
            )
        )
    return rows


def _multi_hop_rows(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    candidates = [
        service
        for service in SERVICES
        if TEAMS_BY_SLUG[service.team].slug
        != TEAMS_BY_SLUG[SERVICES_BY_NAME[service.dependency].team].slug
    ][:30]
    splits = _splits(len(candidates), 20)

    for position, (service, split) in enumerate(zip(candidates, splits, strict=True)):
        dependency = SERVICES_BY_NAME[service.dependency]
        team = TEAMS_BY_SLUG[dependency.team]
        rows.append(
            _row(
                f"gen_multi_hop_{position + 1:03d}",
                "multi_hop",
                "gen_multihop_dependency_owner",
                split,
                f"Which team owns {dependency.name}, the service that {service.name} depends on?",
                f"{team.name} owns {dependency.name}.",
                [f"doc_service_{service.slug}", f"doc_service_{dependency.slug}"],
                [
                    index[f"doc_service_{service.slug}"]["Dependencies"],
                    index[f"doc_service_{dependency.slug}"]["Overview"],
                ],
                [dependency.name, team.name],
                "graph",
            )
        )
    return rows


def _global_rows(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    splits = _splits(len(TEAMS) * 3, 20)
    position = 0
    for team in TEAMS:
        services = [service for service in SERVICES if service.team == team.slug]
        names = ", ".join(service.name for service in services)
        questions = [
            (
                f"Which services does the {team.name} team own?",
                f"The {team.name} team owns {names}.",
                "Service Ownership",
                [team.name] + [service.name for service in services],
            ),
            (
                f"Who leads the {team.name} team?",
                f"{team.lead} leads the {team.name} team.",
                "Team Overview",
                [team.lead, team.name],
            ),
            (
                f"How many production services does the {team.name} team own?",
                f"The {team.name} team owns {len(services)} production services.",
                "Team Overview",
                [team.name],
            ),
        ]
        cluster_ids = ("gen_global_ownership", "gen_global_lead", "gen_global_count")
        for question_index, (query, answer, heading, entities) in enumerate(questions):
            rows.append(
                _row(
                    f"gen_global_{position + 1:03d}",
                    "global",
                    cluster_ids[question_index],
                    splits[position],
                    query,
                    answer,
                    [f"doc_team_{team.slug}"],
                    [index[f"doc_team_{team.slug}"][heading]],
                    entities,
                    "hybrid",
                )
            )
            position += 1
    return rows


def _unanswerable_rows() -> list[dict[str, object]]:
    splits = _splits(len(ABSENT_NAMES), 20)
    templates = (
        "What is the p99 latency SLA for {name}?",
        "Which team owns {name}?",
        "Which runbook covers {name}?",
    )
    cluster_ids = (
        "gen_unanswerable_sla",
        "gen_unanswerable_owner",
        "gen_unanswerable_runbook",
    )
    return [
        _row(
            f"gen_unanswerable_{position + 1:03d}",
            "unanswerable",
            cluster_ids[position % len(cluster_ids)],
            split,
            templates[position % len(templates)].format(name=name),
            None,
            [],
            [],
            [],
            "abstain",
        )
        for position, (name, split) in enumerate(zip(ABSENT_NAMES, splits, strict=True))
    ]


def _paraphrase_rows(
    index: dict[str, dict[str, str]],
    fact_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    test_parents = [row for row in fact_rows if row["split"] == "test"]
    dev_parents = [row for row in fact_rows if row["split"] == "dev"]
    parents = test_parents + dev_parents
    splits = _splits(len(parents), 20)
    templates = (
        "Tell me the p99 SLA for {name}.",
        "What latency target applies to {name}?",
        "State the error budget and p99 target for {name}.",
    )
    cluster_ids = (
        "gen_paraphrase_p99",
        "gen_paraphrase_latency",
        "gen_paraphrase_error_budget",
    )

    for position, (parent, split) in enumerate(zip(parents, splits, strict=True)):
        entities = cast(list[str], parent["expected_entities"])
        service_name = entities[0]
        service = SERVICES_BY_NAME[service_name]
        rows.append(
            _row(
                f"gen_paraphrase_{position + 1:03d}",
                "paraphrase",
                cluster_ids[position % len(cluster_ids)],
                split,
                templates[position % len(templates)].format(name=service.name),
                cast(str | None, parent["expected_answer"]),
                list(cast(list[str], parent["expected_doc_ids"])),
                list(cast(list[str], parent["expected_chunk_ids"])),
                [service.name, f"{service.p99_ms}ms"],
                "cache",
                depends_on=[cast(str, parent["id"])],
            )
        )
    return rows


def _multi_turn_rows(
    index: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    splits = _splits(len(SERVICES), 20)
    for position, (service, split) in enumerate(zip(SERVICES, splits, strict=True)):
        parent_query = f"What is the p99 latency SLA for {service.name}?"
        parent_answer = (
            f"{service.name} targets a p99 latency of {service.p99_ms}ms and an error "
            f"budget of {service.error_budget_pct}% per 30 days."
        )
        rows.append(
            _row(
                f"gen_multi_turn_{position + 1:03d}",
                "multi_turn",
                "gen_multi_turn_p99",
                split,
                "What is its p99 latency SLA?",
                parent_answer,
                [f"doc_service_{service.slug}"],
                [index[f"doc_service_{service.slug}"]["SLA"]],
                [service.name],
                "vector",
                thread_turns=[
                    {"role": "user", "content": parent_query},
                    {"role": "assistant", "content": parent_answer},
                ],
                expected_rewritten_query=(f"What is {service.name}'s p99 latency SLA?"),
            )
        )
    return rows


def _phase_c_fact_rows(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    """Powered `fact` rows added after the frozen Phase A baseline."""
    rows: list[dict[str, object]] = []
    versioned = [service for service in SERVICES if SERVICES.index(service) % 6 == 0]
    standard = [service for service in SERVICES if service not in versioned]
    assert len(PHASE_C_FACT_PROBES) == PHASE_C_FACT_CLUSTERS

    for position in range(PHASE_C_FACT_TEST_ROWS):
        service = standard[position % len(standard)]
        cluster_id, template, answer_kind = PHASE_C_FACT_PROBES[position % len(PHASE_C_FACT_PROBES)]
        p99 = f"{service.p99_ms}ms"
        budget = f"{service.error_budget_pct}%"
        if answer_kind == "budget":
            answer = f"{service.name} has an error budget of {budget} per 30 days."
        elif answer_kind == "both":
            answer = (
                f"{service.name} targets a p99 latency of {p99} and an error budget of "
                f"{budget} per 30 days."
            )
        else:
            answer = f"{service.name} targets a p99 latency of {p99}."
        rows.append(
            _row(
                f"gen_fact_phase_c_{position + 1:03d}",
                "fact",
                cluster_id,
                "test",
                template.format(name=service.name),
                answer,
                [f"doc_service_{service.slug}"],
                [index[f"doc_service_{service.slug}"]["SLA"]],
                [service.name, p99],
                "vector",
            )
        )
    return rows


def _phase_c_multi_hop_rows(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    """Powered `multi_hop` rows added after the frozen Phase A baseline."""
    rows: list[dict[str, object]] = []
    candidates = [
        service
        for service in SERVICES
        if TEAMS_BY_SLUG[service.team].slug
        != TEAMS_BY_SLUG[SERVICES_BY_NAME[service.dependency].team].slug
    ]
    assert len(PHASE_C_MULTI_HOP_TEMPLATES) == PHASE_C_MULTI_HOP_CLUSTERS

    for position in range(PHASE_C_MULTI_HOP_TEST_ROWS):
        service = candidates[position % len(candidates)]
        dependency = SERVICES_BY_NAME[service.dependency]
        team = TEAMS_BY_SLUG[dependency.team]
        template_index = position % len(PHASE_C_MULTI_HOP_TEMPLATES)
        template = PHASE_C_MULTI_HOP_TEMPLATES[template_index]
        rows.append(
            _row(
                f"gen_multi_hop_phase_c_{position + 1:03d}",
                "multi_hop",
                f"gen_multihop_upstream_owner_{template_index + 1:02d}",
                "test",
                template.format(
                    service=service.name,
                    dependency=dependency.name,
                    team=team.name,
                ),
                f"{team.name} owns {dependency.name}.",
                [f"doc_service_{service.slug}", f"doc_service_{dependency.slug}"],
                [
                    index[f"doc_service_{service.slug}"]["Dependencies"],
                    index[f"doc_service_{dependency.slug}"]["Overview"],
                ],
                [dependency.name, team.name],
                "graph",
            )
        )
    return rows


def build_golden(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    """Return the generated golden rows without writing them."""
    fact_rows = _fact_rows(index)
    return (
        fact_rows
        + _multi_hop_rows(index)
        + _global_rows(index)
        + _unanswerable_rows()
        + _paraphrase_rows(index, fact_rows)
        + _multi_turn_rows(index)
        + _phase_c_fact_rows(index)
        + _phase_c_multi_hop_rows(index)
    )


def generate_golden(index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    rows = build_golden(index)
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def _count_corpus() -> tuple[int, int]:
    documents = 0
    chunks = 0
    for path in iter_corpus_files(CORPUS_DIR):
        documents += 1
        parsed = parse_markdown(path.read_text(encoding="utf-8"), source_path=path.as_posix())
        chunks += len(
            chunk_parsed_document(
                parsed,
                path.as_posix(),
                _scope_for(parsed.metadata.get("acl_scope")),
            )
        )
    return documents, chunks


def _check_assets() -> int:
    """Regenerate in memory and compare against the committed assets.

    Counting documents and chunks is not enough: chunk ids include a hash of the
    chunk text, so a hand edit can keep every count identical while leaving the
    golden ids stale. This check rebuilds the corpus and golden rows from the
    generator, then compares the committed bytes and ids.
    """
    if not SYNTHETIC_DIR.exists() or not MANIFEST_PATH.exists() or not GOLDEN_PATH.exists():
        raise SystemExit("generated assets are missing; run without --check first")

    mismatches: list[str] = []
    expected_documents = build_corpus()
    expected_names = {f"{doc_id}.md" for doc_id, _ in expected_documents}
    committed_paths = {path.name: path for path in SYNTHETIC_DIR.glob("*.md")}

    for name in sorted(expected_names - committed_paths.keys()):
        mismatches.append(f"missing generated document {name}")
    for name in sorted(committed_paths.keys() - expected_names):
        mismatches.append(f"unexpected generated document {name}")

    index: dict[str, dict[str, str]] = {}
    for doc_id, content in expected_documents:
        source_path = f"corpus/synthetic/{doc_id}.md"
        path = SYNTHETIC_DIR / f"{doc_id}.md"
        if path.exists() and path.read_text(encoding="utf-8") != content:
            mismatches.append(f"generated document {path.name} differs from generator output")
        index[doc_id] = _chunk_ids_by_heading(content, source_path)

    expected_rows = build_golden(index)
    for number, row in enumerate(expected_rows, start=1):
        if not row.get("cluster_id"):
            mismatches.append(f"generated golden row {number} has no cluster_id")
    expected_lines = [json.dumps(row, ensure_ascii=False) for row in expected_rows]
    committed_lines = [
        line for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len(committed_lines) != len(expected_lines):
        mismatches.append(f"golden rows {len(committed_lines)} != {len(expected_lines)}")
    for number, (expected_line, committed_line) in enumerate(
        zip(expected_lines, committed_lines, strict=False), start=1
    ):
        if expected_line != committed_line:
            mismatches.append(f"golden row {number} differs from generator output")

    documents, chunks = _count_corpus()
    expected_manifest = {
        "generator": GENERATOR,
        "seed": SEED,
        "generated_documents": len(expected_documents),
        "generated_chunks": sum(len(headings) for headings in index.values()),
        "total_documents": documents,
        "total_chunks": chunks,
        "golden_rows": len(expected_rows),
    }
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            mismatches.append(f"manifest {key} {manifest.get(key)!r} != {value!r}")

    print(f"corpus documents: {documents}")
    print(f"corpus chunks:    {chunks}")
    print(f"golden rows:      {len(expected_rows)}")
    if mismatches:
        for mismatch in mismatches:
            print(f"MISMATCH: {mismatch}")
        return 1
    print("generated assets match the committed corpus and golden rows.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and compare against committed assets without writing.",
    )
    args = parser.parse_args(argv)

    if args.check:
        return _check_assets()

    index = generate_corpus()
    rows = generate_golden(index)
    documents, chunks = _count_corpus()
    manifest = {
        "generator": GENERATOR,
        "seed": SEED,
        "generated_documents": len(index),
        "generated_chunks": sum(len(headings) for headings in index.values()),
        "total_documents": documents,
        "total_chunks": chunks,
        "golden_rows": len(rows),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(index)} generated documents to {SYNTHETIC_DIR}")
    print(f"Wrote {len(rows)} golden rows to {GOLDEN_PATH}")
    print(f"Corpus totals: {documents} documents / {chunks} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
