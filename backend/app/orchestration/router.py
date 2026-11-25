import re

from app.cache.exact import ExactCache
from app.cache.keys import prompt_version_lookup_chain
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

# Keywords indicating unanswerable / out-of-scope topics that require immediate
# abstention in grounded_only mode. grounded_plus_web never abstains on these;
# it may answer from web evidence or model knowledge instead.
UNANSWERABLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(arr|gross profit|revenue|fiscal year)\b", re.IGNORECASE),
    re.compile(r"\b(aws region|kubernetes cluster|cloud provider)\b", re.IGNORECASE),
    re.compile(r"\b(snowflake|data lake|at-rest encryption)\b", re.IGNORECASE),
]

# The only queries grounded_plus_web refuses outright.
UNSAFE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(self[- ]?harm|suicide|kill myself)\b", re.IGNORECASE),
    re.compile(r"\b(how to|instructions? for)\b.*\b(bomb|explosive|weapon|firearm)\b", re.IGNORECASE),
    re.compile(r"\b(make|build|synthesize)\b.*\b(meth|fentanyl|nerve agent)\b", re.IGNORECASE),
    re.compile(r"\b(ddos|ransomware|malware)\b.*\b(how to|instructions?|deploy)\b", re.IGNORECASE),
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
        answer_policy: str = "grounded_only",
        prompt_version: str = "v1",
    ) -> str:
        """Evaluate query and return route: 'cache', 'abstain', 'graph', 'hybrid', or 'vector'."""
        query_clean = query.strip()
        scope = acl_scope or ACLScope.public()

        # 0. Check Small Talk (skip retrieval entirely)
        for pattern in SMALL_TALK_PATTERNS:
            if pattern.search(query_clean):
                return "small_talk"

        # 1a. Unsafe requests abstain under either policy.
        for pattern in UNSAFE_PATTERNS:
            if pattern.search(query_clean):
                return "abstain"

        # 1b. Domain-limit abstention applies only to grounded_only. In
        # grounded_plus_web the query may continue to web grounding or an
        # explicitly unverified model answer.
        if answer_policy == "grounded_only":
            for pattern in UNANSWERABLE_PATTERNS:
                if pattern.search(query_clean):
                    return "abstain"

        # 2. Check Exact Cache (100% exact match hit). Legacy v1 entries were
        # grounded-only answers, so they remain readable under that policy.
        for probe_version in prompt_version_lookup_chain(prompt_version):
            if exact_cache is not None and exact_cache.get(
                query_clean,
                acl_scope=scope,
                owner_user_id=owner_user_id,
                prompt_version=probe_version,
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
        for probe_version in prompt_version_lookup_chain(prompt_version):
            if semantic_cache is not None and semantic_cache.get(
                query_clean,
                acl_scope=scope,
                owner_user_id=owner_user_id,
                prompt_version=probe_version,
            ):
                return "cache"

        # 6. Default to localized vector retrieval for facts
        return "vector"
