from app.schemas.market import PrecomputeHintRequest
from app.services.precompute import PrecomputeTaskPlanner


def test_current_page_tasks_score_higher_than_related_tasks() -> None:
    planner = PrecomputeTaskPlanner()
    tasks = planner.build_tasks(
        PrecomputeHintRequest(
            current_page="market-analysis",
            instrument_id="btc-usdt-perp",
            timeframe="1h",
            view_window="default",
            priority=5,
            visible=True,
        )
    )

    current = next(task for task in tasks if task.task_type == "analysis")
    related = next(task for task in tasks if task.task_type == "structure")

    assert current.score > related.score
    assert current.page_type == "analysis"


def test_selected_candidates_limit_related_precompute_tasks() -> None:
    planner = PrecomputeTaskPlanner()
    tasks = planner.build_tasks(
        PrecomputeHintRequest(
            current_page="alert-center",
            instrument_id="btc-usdt-perp",
            timeframe="1h",
            candidates=["microstructure"],
        )
    )

    task_types = {task.task_type for task in tasks}
    assert "alerts" in task_types
    assert "microstructure" in task_types
    assert "structure" not in task_types
