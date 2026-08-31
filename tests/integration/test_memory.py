
import pytest

from app.agent.history import HistoryManager
from app.agent.registry import StrategyRegistry


@pytest.mark.asyncio
async def test_history_manager_sanitization() -> None:
    history = HistoryManager("test_task", "test_session")

    details = {
        "user": "test",
        "password": "supersecretpassword",
        "nested": {
            "password": "super_secret_password"
        }
    }
    sanitized = history._sanitize_details(details)
    assert sanitized is not None
    assert sanitized["user"] == "test"
    assert sanitized["password"] == "***"

@pytest.mark.asyncio
async def test_history_manager_logging() -> None:
    history = HistoryManager("test_task_2", "test_session_2")

    await history.log_event("START_TASK", {"goal": "test goal"})
    await history.log_event("LOGIN", {"password": "secret"})

    events = await history.get_recent_events(limit=10)
    assert len(events) >= 2
    # Ensure they are sorted desc
    assert events[0]["event_type"] == "LOGIN"
    assert events[0]["details"]["password"] == "***"

    assert events[1]["event_type"] == "START_TASK"
    assert events[1]["details"]["goal"] == "test goal"

@pytest.mark.asyncio
async def test_semantic_memory() -> None:
    history = HistoryManager("test_task_3", "test_session_3")

    await history.set_memory("login_url", "https://example.com/login")
    val = await history.get_memory("login_url")
    assert val == "https://example.com/login"

    # Overwrite
    await history.set_memory("login_url", "https://example.com/signin")
    val = await history.get_memory("login_url")
    assert val == "https://example.com/signin"

@pytest.mark.asyncio
async def test_strategy_registry() -> None:
    registry = StrategyRegistry()

    # Add strategy
    strat = await registry.add_strategy(
        url="https://example.com/products",
        objective="Find products",
        action_type="extract",
        selector=".product-card"
    )

    assert strat.domain == "example.com"
    assert strat.selector == ".product-card"

    # Record success
    await registry.record_success(strat.id)

    strats = await registry.get_best_strategies(
        url="https://example.com/products",
        objective="Find products",
        action_type="extract"
    )

    assert len(strats) == 1
    assert strats[0].success_count == 1
    assert strats[0].confidence == 1.0

    # Record failure
    await registry.record_failure(strat.id)

    strats2 = await registry.get_best_strategies(
        url="https://example.com/products",
        objective="Find products",
        action_type="extract"
    )

    assert strats2[0].failure_count == 1
    assert strats2[0].confidence == 0.5  # 1 success / 2 total = 0.5
