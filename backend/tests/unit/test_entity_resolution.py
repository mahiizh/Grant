import pytest
from app.ingestion.entity_resolution import EntityResolver


@pytest.mark.asyncio
async def test_entity_resolution_30_pair_benchmark() -> None:
    """Benchmark entity resolution precision and recall across 30 hand-labeled pairs."""
    resolver = EntityResolver()

    # 15 Positive Pairs
    positives = [
        ("Postgres", "Database", "PostgreSQL", "Database"),
        ("PostgreSQL", "Database", "PostgreSQL 16", "Database"),
        ("Postgres", "Database", "PostgreSQL 16", "Database"),
        ("Redis", "Cache", "redis-server", "Cache"),
        ("K8s", "Infrastructure", "Kubernetes", "Infrastructure"),
        ("PaymentGateway", "Service", "Payment-Gateway", "Service"),
        ("PaymentGateway", "Service", "payment-gw", "Service"),
        ("CoreBanking", "Service", "CoreBanking v2", "Service"),
        ("Alice Chen", "Person", "Alice Chen", "Person"),
        ("Bob Kumar", "Person", "Bob Kumar", "Person"),
        ("Elena Rostova", "Person", "Elena Rostova", "Person"),
        ("Dave Miller", "Person", "Dave Miller", "Person"),
        ("Qdrant", "Database", "Qdrant Vector DB", "Database"),
        ("Neo4j", "Database", "Neo4j Graph Database", "Database"),
        ("Redis Sentinel", "Infrastructure", "Redis Sentinel Cluster", "Infrastructure"),
    ]

    # 15 Negative Pairs
    negatives = [
        ("PostgreSQL", "Database", "Neo4j", "Database"),
        ("Redis", "Cache", "Qdrant", "Database"),
        ("Alice Chen", "Person", "Bob Kumar", "Person"),
        ("Elena Rostova", "Person", "Dave Miller", "Person"),
        ("PaymentGateway", "Service", "CoreBanking", "Service"),
        ("Kubernetes", "Infrastructure", "PostgreSQL", "Database"),
        ("SRE Team", "Organization", "Data Platform Team", "Organization"),
        ("Payments Team", "Organization", "Core Banking Team", "Organization"),
        ("Exchange Rate Service", "Service", "PaymentGateway", "Service"),
        ("Redis", "Cache", "PostgreSQL", "Database"),
        ("Qdrant", "Database", "Neo4j", "Database"),
        ("Board Audit", "Document", "SLA Agreement", "Document"),
        ("Alice Chen", "Person", "Elena Rostova", "Person"),
        ("PaymentGateway", "Service", "Redis", "Cache"),
        ("Docker", "Infrastructure", "PostgreSQL", "Database"),
    ]

    true_positives = 0
    false_negatives = 0
    for name_a, type_a, name_b, type_b in positives:
        is_same = await resolver.are_same_entity(name_a, type_a, name_b, type_b)
        if is_same:
            true_positives += 1
        else:
            false_negatives += 1

    true_negatives = 0
    false_positives = 0
    for name_a, type_a, name_b, type_b in negatives:
        is_same = await resolver.are_same_entity(name_a, type_a, name_b, type_b)
        if not is_same:
            true_negatives += 1
        else:
            false_positives += 1

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0

    print(f"\nEntity Resolution Benchmark Results:")
    print(f"True Positives: {true_positives}/15")
    print(f"True Negatives: {true_negatives}/15")
    print(f"Precision: {precision:.2%}, Recall: {recall:.2%}")

    # Assert 100% precision and high recall
    assert precision >= 0.90, f"Precision was {precision:.2%}"
    assert recall >= 0.90, f"Recall was {recall:.2%}"

    # Explicit check for "Postgres", "PostgreSQL", and "PostgreSQL 16"
    assert await resolver.are_same_entity("Postgres", "Database", "PostgreSQL", "Database")
    assert await resolver.are_same_entity("PostgreSQL", "Database", "PostgreSQL 16", "Database")
    assert await resolver.are_same_entity("Postgres", "Database", "PostgreSQL 16", "Database")
