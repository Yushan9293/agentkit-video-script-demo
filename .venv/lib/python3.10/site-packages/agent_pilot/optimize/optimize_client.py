import requests
import traceback
import logging
from typing import Optional

from agent_pilot.http_client import get_http_client
from agent_pilot.optimize.models import (
    OptimizeServiceStartOptimizeResult,
    OptimizeServiceProgressResult,
    OptimizeReport,
)
# OptimizeServiceProgressResult is added to the import

logger = logging.getLogger(__name__)


def optimize_service_start(
    task_id: str,
    version: str,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> OptimizeServiceStartOptimizeResult:
    """
    Starts an optimization job for a given task and version.
    Makes an HTTP POST request to the specified or default API.

    Parameters:
        task_id (str): Unique identifier for the task.
        version (str): Version of the task/prompt to optimize.
        api_key (str, optional): API key for authentication. Defaults to config's API key.
        api_url (str, optional): API base URL. Defaults to config's API URL.

    Returns:
        OptimizeServiceStartOptimizeResult: Result containing TaskId, Version, and OptimizeJobId.

    Raises:
        RuntimeError: If starting the optimization job fails.
    """
    try:
        action = "OptimizeServiceStartOptimize"  # Action for starting optimization

        body = {
            "TaskId": task_id,
            "Version": version,
        }

        response_data, response_status_code = get_http_client().post(
            action=action,
            data=body,
            api_key=api_key,
            api_url=api_url,
            base_path="/agent-pilot-optimize",
            workspace_id=workspace_id,
        )

        if response_status_code == 401:
            raise RuntimeError("Invalid or unauthorized API credentials")

        if response_status_code != 200:
            raise RuntimeError(f"Error fetching template: {response_status_code} - {response_data}")

        logger.debug(f"[{action}] got response json: {response_data}")

        result_data = response_data.get("Result", None)
        if result_data is None:
            raise RuntimeError("Optimization job start result not found in response, or response format is unexpected.")

        # Validate and parse the result data into OptimizeServiceStartOptimizeResult
        optimize_result = OptimizeServiceStartOptimizeResult(**result_data)
        return optimize_result

    except requests.exceptions.RequestException as e:
        traceback.print_exc()
        raise RuntimeError(f"Network error while starting optimization job: {str(e)}") from e
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Error starting optimization job: {str(e)}") from e


def optimize_service_get_progress(
    optimize_job_id: str,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> OptimizeServiceProgressResult:
    """
    Gets the optimization progress for a given optimization job ID.
    Makes an HTTP GET request to the specified or default API.

    Parameters:
        optimize_job_id (str): Unique identifier for the optimization job.
        api_key (str, optional): API key for authentication. Defaults to config's API key.
        api_url (str, optional): API base URL. Defaults to config's API URL.

    Returns:
        OptimizeServiceProgressResult: Result containing JobInfo and Progress.

    Raises:
        RuntimeError: If fetching the optimization progress fails.
    """
    try:
        action = "OptimizeServiceGetOptimizeProgress"  # Action for getting progress

        body = {"OptimizeJobId": optimize_job_id}

        response_data, response_status_code = get_http_client().post(
            action=action, data=body, api_key=api_key, api_url=api_url, workspace_id=workspace_id
        )

        if response_status_code == 401:
            raise RuntimeError("Invalid or unauthorized API credentials")

        if response_status_code != 200:
            raise RuntimeError(f"Error fetching template: {response_status_code} - {response_data}")

        logger.debug(f"[{action}] got response json: {response_data}")

        result_data = response_data.get("Result", None)
        if result_data is None:
            raise RuntimeError("Optimization progress result not found in response, or response format is unexpected.")

        # Validate and parse the result data into OptimizeServiceProgressResult
        progress_result = OptimizeServiceProgressResult(**result_data)
        return progress_result

    except requests.exceptions.RequestException as e:
        traceback.print_exc()
        raise RuntimeError(f"Network error while fetching optimization progress: {str(e)}") from e
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Error fetching optimization progress: {str(e)}") from e


def optimize_service_get_report(
    task_id: str,
    base_version: str,
    ref_version: str,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> OptimizeReport:  # noqa: E501
    try:
        action = "OptimizeServiceGetReport"

        body = {
            "TaskId": task_id,
            "BaseVersion": base_version,
            "RefVersion": ref_version,
        }

        response_data, response_status_code = get_http_client().post(
            action=action, data=body, api_key=api_key, api_url=api_url, workspace_id=workspace_id
        )

        if response_status_code == 401:
            raise RuntimeError("Invalid or unauthorized API credentials")

        if response_status_code != 200:
            raise RuntimeError(f"Error fetching template: {response_status_code} - {response_data}")

        logger.debug(f"[{action}] got response json: {response_data}")

        return OptimizeReport(base=response_data["Result"]["base"], opt=response_data["Result"]["ref"])

    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Error getting optimization report: {str(e)}") from e
