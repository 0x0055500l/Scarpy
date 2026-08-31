import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.future import select

from app.db.models import ExecutionEvent, Task
from app.db.session import get_db_session
from app.schemas.api import (
    TaskCreateRequest,
    TaskEventResponse,
    TaskResponse,
    TaskResultResponse,
)
from app.services.worker import WorkerService

router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.post("", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(request: TaskCreateRequest) -> TaskResponse:
    task_id = str(uuid.uuid4())

    async with get_db_session() as session:
        new_task = Task(
            id=task_id,
            url=str(request.url),
            goal=request.objective,
            schema_definition=request.schema_definition,
            options=request.options,
            status="QUEUED"
        )
        session.add(new_task)
        await session.commit()
        await session.refresh(new_task)

        response = TaskResponse(
            id=new_task.id,
            url=new_task.url,
            goal=new_task.goal,
            status=new_task.status,
            created_at=new_task.created_at,
            error=new_task.error,
            options=new_task.options
        )

    # Enqueue background execution
    WorkerService.enqueue_task(task_id)

    return response

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    async with get_db_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskResponse(
            id=task.id,
            url=task.url,
            goal=task.goal,
            status=task.status,
            created_at=task.created_at,
            error=task.error,
            options=task.options
        )

@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: str) -> TaskResponse:
    async with get_db_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status in ["COMPLETED", "FAILED", "CANCELLED"]:
            raise HTTPException(status_code=400, detail=f"Cannot cancel task in {task.status} state")

        task.status = "CANCELLED"
        await session.commit()
        await session.refresh(task)

        return TaskResponse(
            id=task.id,
            url=task.url,
            goal=task.goal,
            status=task.status,
            created_at=task.created_at,
            error=task.error
        )

@router.get("/{task_id}/events", response_model=List[TaskEventResponse])
async def get_task_events(task_id: str) -> List[TaskEventResponse]:
    async with get_db_session() as session:
        # Verify task exists
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        stmt = select(ExecutionEvent).where(
            ExecutionEvent.task_id == task_id
        ).order_by(ExecutionEvent.timestamp.asc())

        result = await session.execute(stmt)
        events = result.scalars().all()

        return [
            TaskEventResponse(
                event_type=e.event_type,
                timestamp=e.timestamp,
                details=e.details
            ) for e in events
        ]

@router.get("/{task_id}/results", response_model=TaskResultResponse)
async def get_task_results(task_id: str) -> TaskResultResponse:
    async with get_db_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskResultResponse(
            id=task.id,
            status=task.status,
            result=task.result,
            error=task.error
        )
