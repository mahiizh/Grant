from collections.abc import AsyncGenerator
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes import query as query_route
from app.db.models import Base
from app.db.postgres import get_db_session
from app.evaluation.runner import EvaluationRunner
from app.main import app


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_session

    app.dependency_overrides[get_db_session] = override_get_db

    repo_root = Path(__file__).resolve().parents[3]
    corpus_dir = repo_root / "corpus"
    orchestrator = await EvaluationRunner.setup_corpus_and_orchestrator(
        session=test_session,
        corpus_dir=corpus_dir,
    )
    query_route.set_orchestrator(orchestrator)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"X-Dev-User": "admin"}) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_threads_crud_and_messages(client: AsyncClient) -> None:
    # 1. Create thread
    res = await client.post("/api/v1/threads", json={"title": "Investigation INC-04", "acl_scope": "sre"})
    assert res.status_code == 201
    thread_data = res.json()
    thread_id = thread_data["thread_id"]
    assert thread_data["title"] == "Investigation INC-04"
    assert thread_data["acl_scope"] == "sre"
    assert thread_data["messages"] == []

    # 2. List threads
    res = await client.get("/api/v1/threads")
    assert res.status_code == 200
    threads_list = res.json()
    assert any(t["thread_id"] == thread_id for t in threads_list)

    # 3. Patch thread (rename)
    res = await client.patch(f"/api/v1/threads/{thread_id}", json={"title": "Renamed Investigation"})
    assert res.status_code == 200
    assert res.json()["title"] == "Renamed Investigation"

    # 4. Post message Turn 1
    res = await client.post(
        f"/api/v1/threads/{thread_id}/messages",
        json={"content": "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?"},
    )
    assert res.status_code == 200
    turn1 = res.json()
    assert turn1["role"] == "assistant"
    assert turn1["trace_id"] is not None
    assert len(turn1["citations"]) > 0
    assert any(s["id"] == "condense" for s in turn1["pipeline_stages"])
    asst_msg_id_1 = turn1["message_id"]

    # 5. Post message Turn 2 (with pronouns)
    res = await client.post(
        f"/api/v1/threads/{thread_id}/messages",
        json={"content": "How did they fix it?"},
    )
    assert res.status_code == 200
    turn2 = res.json()
    assert "they" not in turn2["rewritten_query"].lower()
    assert "outbox" in turn2["rewritten_query"].lower()
    assert turn2["trace_id"] != turn1["trace_id"]
    asst_msg_id_2 = turn2["message_id"]

    # 6. Feedback 👍/👎
    res = await client.post(
        f"/api/v1/threads/{thread_id}/messages/{asst_msg_id_2}/feedback",
        json={"feedback": "up", "note": "Resolved pronouns cleanly"},
    )
    assert res.status_code == 200
    assert res.json()["feedback"] == "up"
    assert res.json()["feedback_note"] == "Resolved pronouns cleanly"

    # 7. Add to golden dataset
    res = await client.post(
        f"/api/v1/threads/{thread_id}/messages/{asst_msg_id_2}/golden",
        json={"category": "multi_turn"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "added"
    assert "eval_candidate_" in res.json()["golden_id"]

    # 8. Regenerate message
    res = await client.post(f"/api/v1/threads/{thread_id}/messages/{asst_msg_id_2}/regenerate")
    assert res.status_code == 200
    regen = res.json()
    assert len(regen["generations"]) == 1  # 1 prior archived generation
    assert regen["generations"][0]["content"] == turn2["content"]

    # 9. Get thread details
    res = await client.get(f"/api/v1/threads/{thread_id}")
    assert res.status_code == 200
    detail = res.json()
    assert len(detail["messages"]) >= 4  # 2 user msgs + 2 assistant msgs

    # 10. Delete thread
    res = await client.delete(f"/api/v1/threads/{thread_id}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True

    # Confirm 404 after delete
    res = await client.get(f"/api/v1/threads/{thread_id}")
    assert res.status_code == 404
