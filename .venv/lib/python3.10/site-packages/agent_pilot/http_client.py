import threading
import requests
from typing import Optional, Tuple
import uuid
from agent_pilot.config import get_config
import logging

logger = logging.getLogger(__name__)

http_client = None
_lock = threading.Lock()


class HttpClient:
    def __init__(self) -> None:
        config = get_config()
        self.api_url = config.api_url
        self.api_key = config.api_key
        self.version = "2024-01-01"
        self.local_debug = config.local_debug
        self.ssl_verify = config.ssl_verify
        self.verbose = config.verbose
        self.workspace_id = config.workspace_id
        # Timeout configuration: (connect_timeout, read_timeout)
        self.timeout = (10, 30)  # 10s to connect, 30s to read

    def post(
        self,
        action: str,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        stream: Optional[bool] = False,
        base_path: Optional[str] = None,
        version: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Tuple[dict, int]:
        request_id = str(uuid.uuid4())
        if data is not None:
            data["RequestId"] = request_id
        else:
            data = {"RequestId": request_id}

        if base_path is None:
            base_path = "/agent-pilot"

        api_key = api_key or self.api_key
        api_url = api_url or self.api_url
        verbose = self.verbose
        version = self.version if version is None else version
        workspace_id = self.workspace_id if workspace_id is None else workspace_id

        if data.get("workspace_id") is None:
            data["workspace_id"] = workspace_id

        # Determine if this is a local debug request based on the actual URL being used
        is_local_debug = api_url.startswith("http://localhost") if api_url else self.local_debug

        # Check for API key first, before attempting any network connections
        if not api_key:
            raise RuntimeError("No authentication api_key provided")

        logger.info(f"[post] request_id: {request_id}, api_url: {api_url}, action: {action}")
        if verbose:
            logger.info(f"[post] data: {data}")

        if headers is None:
            headers = {}

        if not is_local_debug:
            headers.update({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
        else:
            headers.update({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })

        url = None
        if version and action:
            url = api_url + base_path + f"?Version={version}&Action={action}"
        elif version:
            url = api_url + base_path + f"?Version={version}"
        elif action:
            url = api_url + base_path + f"?Action={action}"
        else:
            url = api_url + base_path

        response = requests.post(url=url, json=data, headers=headers, verify=self.ssl_verify, stream=stream)

        if response.status_code == 401:
            raise RuntimeError(
                f"Invalid or unauthorized API credentials: request_id: {request_id}, response: {response.text}"
            )
        if not response.ok:
            raise RuntimeError(
                f"Error calling {url}: request_id: {request_id}, response: {response.status_code} - {response.text}"
            )
        if stream:
            return response, response.status_code  # type: ignore
        else:
            return response.json(), response.status_code


def get_http_client() -> HttpClient:
    global http_client
    if http_client is None:
        with _lock:
            if http_client is None:
                http_client = HttpClient()
    return http_client
