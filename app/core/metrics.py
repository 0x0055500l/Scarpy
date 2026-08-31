import time
from typing import Any, Dict, Set


class MetricsCollector:
    """Collects execution metrics for reliability testing and observability."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.success_count = 0
        self.failure_count = 0
        self.recovery_count = 0
        self.llm_calls = 0
        self.llm_failures = 0
        self.browser_errors = 0
        self.pages_visited: Set[str] = set()
        self.actions_executed = 0
        self.start_time = 0.0
        self.end_time = 0.0

    def start_timer(self) -> None:
        self.start_time = time.time()

    def stop_timer(self) -> None:
        self.end_time = time.time()

    def record_llm_call(self, success: bool = True) -> None:
        self.llm_calls += 1
        if not success:
            self.llm_failures += 1

    def record_browser_error(self) -> None:
        self.browser_errors += 1

    def record_page_visit(self, url: str) -> None:
        self.pages_visited.add(url)

    def record_action(self) -> None:
        self.actions_executed += 1

    def record_recovery(self) -> None:
        self.recovery_count += 1

    def record_task_result(self, success: bool) -> None:
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

    def get_metrics(self) -> Dict[str, Any]:
        total_tasks = self.success_count + self.failure_count
        success_rate = (self.success_count / total_tasks * 100) if total_tasks > 0 else 0.0
        failure_rate = (self.failure_count / total_tasks * 100) if total_tasks > 0 else 0.0

        execution_time = self.end_time - self.start_time if self.end_time > 0 else (time.time() - self.start_time)

        return {
            "success_rate": f"{success_rate:.1f}%",
            "failure_rate": f"{failure_rate:.1f}%",
            "recovery_count": self.recovery_count,
            "average_execution_time": f"{execution_time:.2f}s",
            "llm_calls": self.llm_calls,
            "llm_failures": self.llm_failures,
            "browser_errors": self.browser_errors,
            "pages_visited": len(self.pages_visited),
            "actions_executed": self.actions_executed
        }

# Global instance for the process
metrics = MetricsCollector()
