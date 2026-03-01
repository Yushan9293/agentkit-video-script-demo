import threading
from typing import List, Union, TypeVar, Any
from agent_pilot.consumer import Consumer

T = TypeVar("T")


class EventQueue:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.events: List[Any] = []
        self.consumer = Consumer(self)
        self.consumer.start()

    def append(self, event: Union[List[T], T]) -> None:
        with self.lock:
            if isinstance(event, list):
                self.events.extend(event)
            else:
                self.events.append(event)

    def get_batch(self) -> List[Any]:
        if self.lock.acquire(False):  # non-blocking
            try:
                events = self.events
                self.events = []
                return events
            finally:
                self.lock.release()
        else:
            return []

    def flush(self) -> None:
        """Flush all pending events immediately by calling consumer's send_batch."""
        if hasattr(self.consumer, "send_batch"):
            self.consumer.send_batch()

    def len(self) -> int:
        return len(self.events)
