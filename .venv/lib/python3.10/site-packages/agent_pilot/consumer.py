from collections import defaultdict
import time
import atexit
import logging
from threading import Thread
from typing import Optional, Any, Dict, List, Tuple
from .config import get_config
from .models import TrackingEvent
from .http_client import get_http_client

logger = logging.getLogger(__name__)


DEFAULT_FLUSH_INTERVAL = 0.5


class Consumer:
    def __init__(self, event_queue: Any, api_key: Optional[str] = None) -> None:
        self.running = True
        self.event_queue = event_queue
        self.api_key = api_key
        self.http_client = get_http_client()

        self._thread = Thread(target=self.run, daemon=True)
        atexit.register(self._final_flush)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def run(self) -> None:
        while self.running:
            self.send_batch()
            time.sleep(DEFAULT_FLUSH_INTERVAL)

        self.send_batch()

    def _group_batch_by_api_key_url(
        self, batch: list[TrackingEvent], default_api_key: Optional[str] = None, default_api_url: Optional[str] = None
    ) -> Dict[Tuple[str, str], List[TrackingEvent]]:
        api_key_url_map: Dict = defaultdict(list)
        for event in batch:
            api_key = event.api_key or default_api_key
            api_url = event.api_url or default_api_url

            if not api_key:
                logger.error(
                    f"API key not found. Please provide an API key. event {event.run_id} will not be sent: {event}"
                )
                continue

            key = (api_key, api_url)
            api_key_url_map[key].append(event)
        return api_key_url_map

    def _send_event_batch(
        self,
        batch: list[TrackingEvent],
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        verbose: bool = False,
        config_workspace_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict], int]:
        task_id = batch[0].task_id
        workspace_id = batch[0].workspace_id or config_workspace_id
        data = {
            "TaskId": task_id,
            "workspace_id": workspace_id,
            "TrackingEvents": [
                event.model_dump(  # api_key and api_url are excluded
                    exclude_none=True,
                    exclude_unset=True,
                    exclude_defaults=True,
                )
                for event in batch
            ],
        }

        if verbose:
            logger.info(f"Sending data: {data}")

        action = "TrackingEvent"
        response_data, response_status_code = self.http_client.post(
            action=action,
            data=data,
            api_key=api_key,
            api_url=api_url,
            workspace_id=workspace_id,
        )
        return response_data, response_status_code

    def send_batch(self) -> None:
        config = get_config()
        batch: list[TrackingEvent] = self.event_queue.get_batch()

        verbose = config.verbose
        api_url = config.api_url
        workspace_id = config.workspace_id

        if len(batch) > 0:
            api_key = self.api_key or config.api_key

            if verbose:
                logger.info(f"Sending {len(batch)} events.")
                for event in batch:
                    event_data = event.model_dump(  # api_key and api_url are excluded
                        exclude_none=True,
                        exclude_unset=True,
                        exclude_defaults=True,
                    )
                    logger.info(f"event {event.run_id}: {event_data}")

            try:
                if verbose:
                    logger.info(f"Sending events to {api_url}")

                grouped_batches = self._group_batch_by_api_key_url(batch, api_key, api_url)
                for (_api_key, _api_url), mini_batch in grouped_batches.items():
                    response_data, response_status_code = self._send_event_batch(
                        batch=mini_batch,
                        api_key=_api_key,
                        api_url=_api_url,
                        verbose=verbose,
                        config_workspace_id=workspace_id,
                    )

                    if verbose:
                        logger.info(
                            f"Events sent. response_data: {response_data}, response_status_code: {response_status_code}"
                        )
            except Exception as e:
                if verbose:
                    logger.exception(f"Error sending events: {e}", exc_info=True)
                else:
                    logger.error("Error sending events", exc_info=True)

                self.event_queue.append(batch)

    def _final_flush(self) -> None:
        if hasattr(self, "running"):
            self.running = False
        else:
            return
        try:
            if self.event_queue.len() > 0:
                self.send_batch()
        except Exception as e:
            logger.error(f"Error in final flush: {e}", exc_info=True)

    def stop(self) -> None:
        self.running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
