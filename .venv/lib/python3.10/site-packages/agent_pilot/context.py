from contextvars import ContextVar
from agent_pilot.event_queue import EventQueue
from agent_pilot.utils import create_uuid_from_string
from typing import List, Dict, Optional, Any, Union
import logging
from uuid import uuid4, UUID

RunID = Union[str, UUID]

parent_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("parent_ctx", default=None)
tags_ctx: ContextVar[Optional[List[str]]] = ContextVar("tag_ctx", default=None)
event_queue_ctx: ContextVar[EventQueue] = ContextVar("event_queue_ctx")
event_queue_ctx.set(EventQueue())
queue = event_queue_ctx.get()


def get_parent_run_id(parent_run_id: str, run_type: str, app_key: str, run_id: str) -> Optional[str]:
    if parent_run_id == "None":
        parent_run_id = None  # type: ignore

    parent_ctx_value = parent_ctx.get()
    parent_from_ctx = parent_ctx_value.get("message_id") if parent_ctx_value is not None else None
    if not parent_run_id and parent_from_ctx and run_type != "thread":
        return str(create_uuid_from_string(str(parent_from_ctx) + str(app_key)))

    if parent_run_id:
        return str(create_uuid_from_string(str(parent_run_id) + str(app_key)))

    if parent_run_id is not None:
        return str(create_uuid_from_string(str(parent_run_id) + str(app_key)))

    return None


class TagsContextManager:
    def __init__(self, tags: List[str]) -> None:
        tags_ctx.set(tags)

    def __enter__(self) -> None:
        pass

    def __exit__(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        tags_ctx.set(None)


def tags(tags: List[str]) -> TagsContextManager:
    return TagsContextManager(tags)


class ParentContextManager:
    def __init__(self, message_id: str) -> None:
        parent_ctx.set({"message_id": message_id, "retrieved": False})

    def __enter__(self) -> None:
        pass

    def __exit__(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        parent_ctx.set(None)


def parent(id: str) -> ParentContextManager:
    return ParentContextManager(id)


class Run:
    def __init__(
        self,
        run_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        task_id: Optional[str] = None,
        version: Optional[str] = None,
    ) -> None:
        self.id: str = run_id or str(uuid4())
        self.parent_run_id: Optional[str] = parent_run_id
        self.children: List[Run] = []
        self.task_id: Optional[str] = task_id
        self.version: Optional[str] = version


class RunManager:
    def __init__(self) -> None:
        self.runs: Dict[str, Run] = {}
        self._current_run: Optional[Run] = None
        self._run_stack: List[Run] = []

    @property
    def current_run(self) -> Optional[Run]:
        """Get the currently active run."""
        return self._current_run

    @property
    def current_run_id(self) -> Optional[str]:
        """Safely get the ID of the current run, or None if there is no current run."""
        return self._current_run.id if self._current_run else None

    def start_run(
        self,
        run_id: Optional[RunID] = None,
        task_id: Optional[str] = None,
        version: Optional[str] = None,
        parent_run_id: Optional[RunID] = None,
    ) -> Optional[Run]:
        if parent_run_id is None and self._current_run is not None:
            parent_run_id = self._current_run.id

        if run_id is not None and run_id == parent_run_id:
            logging.error("A run cannot be its own parent.")
            return None

        run_id_str: Optional[str] = str(run_id) if run_id is not None else None
        parent_run_id_str: Optional[str] = str(parent_run_id) if parent_run_id is not None else None

        if not self._run_exists(parent_run_id_str):
            # in Langchain CallbackHandler, sometimes it pass a parent_run_id for run that do not exist.
            # Those runs should be ignored by Lunary
            parent_run_id_str = None

        run = Run(run_id_str, parent_run_id_str, task_id, version)
        self.runs[run.id] = run

        if parent_run_id_str:
            parent_run = self.runs.get(parent_run_id_str)
            if parent_run:
                parent_run.children.append(run)

        if self._current_run:
            self._run_stack.append(self._current_run)
        self._current_run = run

        return run

    def end_run(self, run_id: RunID) -> str:
        run_id_str = str(run_id)

        run = self.runs.get(run_id_str)
        if run:
            if self._current_run and self._current_run.id == run_id_str:
                self._current_run = self._run_stack.pop() if self._run_stack else None
            self._delete_run(run)

        return run_id_str

    def _run_exists(self, run_id: Optional[str]) -> bool:
        if run_id is None:
            return False
        return run_id in self.runs

    def _delete_run(self, run: Run) -> None:
        for child in run.children:
            self._delete_run(child)

        if run.parent_run_id:
            parent_run = self.runs.get(run.parent_run_id)
            if parent_run:
                parent_run.children.remove(run)

        if run.id in [r.id for r in self._run_stack]:
            self._run_stack = [r for r in self._run_stack if r.id != run.id]

        if self.runs.get(run.id):
            del self.runs[run.id]
