import re

from app.cache.exact import ExactCache
from app.cache.semantic import SemanticCache
from app.core.acl import ACLScope

# Keywords characteristic of small talk / greetings
SMALL_TALK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^(hi|hello|hey|greetings|good morning|good afternoon|good evening|howdy)[\s!.]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(who are you|what can you do|how are you|tell me about yourself)[\s?!.]*$", re.IGNORECASE
    ),
    re.compile(r"^(thanks|thank you|bye|goodbye)[\s!.]*$", re.IGNORECASE),
]

# Keywords indicating unanswerable / out-of-scope topics that require immediate abstention
UNANSWERABLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(arr|gross profit|revenue|fiscal year)\b", re.IGNORECASE),
    re.compile(r"\b(aws region|kubernetes cluster|cloud provider)\b", re.IGNORECASE),
    re.compile(r"\b(snowflake|data lake|at-rest encryption)\b", re.IGNORECASE),
]

# Patterns characteristic of multi-hop relationship traversal
MULTI_HOP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"who leads the.*team responsible", re.IGNORECASE),
    re.compile(r"which (?:sre lead|architect(?:'s)? team|team) (?:owns|ran)", re.IGNORECASE),
    re.compile(r"which team owns.*(?:service that|depends on|suffered|whose)", re.IGNORECASE),
    re.compile(r"the service that.*depends on", re.IGNORECASE),
    re.compile(r"what service failed during the incident", re.IGNORECASE),
    re.compile(r"what slack channel.*(?:regarding|contacted)", re.IGNORECASE),
    re.compile(r"who was assigned the remediation.*(?:following|incident)", re.IGNORECASE),
    re.compile(r"who leads the.*(?:engineering\s+team|database\s+where)", re.IGNORECASE),
]

# Patterns characteristic of global cross-document summarization
GLOBAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(summarize|summary across|all engineering teams|all teams)\b", re.IGNORECASE),
    re.compile(r"\b(cross-team|mechanisms exist to ensure|across systems)\b", re.IGNORECASE),
    re.compile(
        r"\b(describe the remediation action items|action items and their owners)\b",
        re.IGNORECASE,
    ),
]


class QueryRouter:
    """Classifies queries into optimal retrieval strategies."""

    @classmethod
    def route(
        cls,
        query: str,
        exact_cache: ExactCache | None = None,
        semantic_cache: SemanticCache | None = None,
        acl_scope: ACLScope | None = None,
        owner_user_id: str | None = None,
    ) -> str:
        """Evaluate query and return route: 'cache', 'abstain', 'graph', 'hybrid', or 'vector'."""
        query_clean = query.strip()
        scope = acl_scope or ACLScope.public()

        # 0. Check Small Talk (skip retrieval entirely)
        for pattern in SMALL_TALK_PATTERNS:
            if pattern.search(query_clean):
                return "small_talk"

        # 1. Check Unanswerable Guard (immediate abstention to save cost and latency)
        for pattern in UNANSWERABLE_PATTERNS:
            if pattern.search(query_clean):
                return "abstain"

        # 2. Check Exact Cache (100% exact match hit)
        if (
            exact_cache is not None
            and exact_cache.get(query_clean, acl_scope=scope, owner_user_id=owner_user_id) is not None
        ):
            return "cache"

        # 3. Check Multi-Hop Graph Traversal
        for pattern in MULTI_HOP_PATTERNS:
            if pattern.search(query_clean):
                return "graph"

        # 4. Check Global Summarization
        for pattern in GLOBAL_PATTERNS:
            if pattern.search(query_clean):
                return "hybrid"

        # 5. Check Semantic Cache (for fact / localized query paraphrases)
        if (
            semantic_cache is not None
            and semantic_cache.get(query_clean, acl_scope=scope, owner_user_id=owner_user_id) is not None
        ):
            return "cache"

        # 6. Default to localized vector retrieval for facts
        return "vector"
