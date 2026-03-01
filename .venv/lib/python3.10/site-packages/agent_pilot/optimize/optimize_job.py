import traceback
import logging
from typing import Optional, Any  # Added Any

from pydantic import BaseModel

from agent_pilot.config import get_config
from .optimize_client import optimize_service_start, optimize_service_get_progress, optimize_service_get_report
from agent_pilot.optimize.models import (
    OptimizeJobInfo,
    OptimizeState,
    OptimizeReport,
)

logger = logging.getLogger(__name__)


class OptimizeJob(BaseModel):
    # Pydantic fields
    task_id: str
    base_version: str
    job_id: str
    api_key: Optional[str] = None
    api_url: Optional[str] = None
    local_debug: Optional[bool] = None
    optimized_version: Optional[str] = None
    workspace_id: Optional[str] = None

    _loaded_api_config = get_config()

    def __init__(self, **data: Any) -> None:
        """
        Custom __init__ to allow Pydantic's normal initialization and then
        set default api_key and api_url from config if not provided.
        """
        super().__init__(**data)
        if self.api_key is None:
            if self._loaded_api_config and hasattr(self._loaded_api_config, "api_key"):
                self.api_key = self._loaded_api_config.api_key
            else:
                logger.warning(f"API key not provided for job {self.job_id} and not found in config.")

        if self.api_url is None:
            if self._loaded_api_config and hasattr(self._loaded_api_config, "api_url"):
                self.api_url = self._loaded_api_config.api_url
            else:
                logger.warning(f"API URL not provided for job {self.job_id} and not found in config.")

        if self.local_debug is None:
            if self._loaded_api_config and hasattr(self._loaded_api_config, "local_debug"):
                self.local_debug = self._loaded_api_config.local_debug
            else:
                logger.warning(f"Local debug flag not provided for job {self.job_id} and not found in config.")

        if self.workspace_id is None:
            if self._loaded_api_config and hasattr(self._loaded_api_config, "workspace_id"):
                self.workspace_id = self._loaded_api_config.workspace_id
            else:
                logger.warning(f"Workspace ID not provided for job {self.job_id} and not found in config.")

    @classmethod
    def create_optimize_job(
        cls,
        task_id: str,
        base_version: str,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> "OptimizeJob":
        """
        Starts an optimization job for a given task and version.
        Returns an OptimizeJob instance.
        """

        effective_api_key = api_key
        if effective_api_key is None and cls._loaded_api_config and hasattr(cls._loaded_api_config, "api_key"):
            effective_api_key = cls._loaded_api_config.api_key

        effective_api_url = api_url
        if effective_api_url is None and cls._loaded_api_config and hasattr(cls._loaded_api_config, "api_url"):
            effective_api_url = cls._loaded_api_config.api_url

        effective_workspace_id = workspace_id
        if (
            effective_workspace_id is None
            and cls._loaded_api_config
            and hasattr(cls._loaded_api_config, "workspace_id")
        ):
            effective_workspace_id = cls._loaded_api_config.workspace_id

        try:
            logger.info(f"Starting optimization for task_id: {task_id}, version: {base_version}")
            optimize_result = optimize_service_start(
                task_id=task_id,
                version=base_version,
                api_key=effective_api_key,
                api_url=effective_api_url,
                workspace_id=effective_workspace_id,
            )
            logger.info(f"Optimization started successfully. OptimizeJobId: {optimize_result.OptimizeJobId}")

            return cls(
                task_id=task_id,
                base_version=base_version,
                job_id=optimize_result.OptimizeJobId,
                api_key=api_key,
                api_url=api_url,
            )
        except Exception as e:
            exception_info = traceback.format_exc()
            logger.error(f"Starting optimization failed: {exception_info}")
            raise RuntimeError(f"Starting optimization failed: {exception_info}") from e

    def get_job_info(self) -> OptimizeJobInfo:
        """
        Gets the optimization progress for this optimization job.
        Uses job_id, api_key, and api_url from the instance.
        """
        try:
            logger.info(f"Getting optimization progress for OptimizeJobId: {self.job_id}")
            if (not self.local_debug and self.api_key is None) or self.api_url is None:
                raise RuntimeError(f"API key or API URL is not set for job {self.job_id}")

            progress_result = optimize_service_get_progress(
                optimize_job_id=self.job_id,
                api_key=self.api_key,
                api_url=self.api_url,
                workspace_id=self.workspace_id,
            )
            logger.info(f"Successfully fetched optimization progress for OptimizeJobId: {self.job_id}")
            job_info = OptimizeJobInfo(
                job_id=self.job_id,
                state=OptimizeState(progress_result.JobInfo.State),
                progress=progress_result.Progress,
                optimized_version=progress_result.JobInfo.OptimizedVersion,
            )
            return job_info
        except Exception as e:
            exception_info = traceback.format_exc()
            logger.error(f"Fetching optimization progress failed for job {self.job_id}: {exception_info}")
            raise RuntimeError(f"Fetching optimization progress failed for job {self.job_id}: {exception_info}") from e

    def get_report(self, ref_version: Optional[str] = None) -> OptimizeReport:
        """
        Gets the optimization report for this job, comparing its base_version
        against a ref_version. Uses task_id, base_version, api_key, and api_url from the instance.
        """
        try:
            logger.info(
                f"Getting optimization report for task_id={self.task_id}, "
                f"base_version={self.base_version}, ref_version={ref_version}"
            )
            if (not self.local_debug and self.api_key is None) is None or self.api_url is None:
                raise RuntimeError(f"API key or API URL is not set for job {self.job_id}")
            if ref_version is None and self.optimized_version is not None:
                ref_version = self.optimized_version
                logger.info(f"ref version not provided, using the optimized version: {ref_version}")
            elif ref_version is None and self.optimized_version is None:
                job_info = self.get_job_info()
                ref_version = job_info.optimized_version
                self.optimized_version = ref_version
                logger.info(f"ref version not provided, using the optimized version: {ref_version}")
            else:
                pass

            if ref_version is None:
                raise RuntimeError(f"ref_version is not set for job {self.job_id}")

            report = optimize_service_get_report(
                task_id=self.task_id,
                base_version=self.base_version,
                ref_version=ref_version,
                api_key=self.api_key,
                api_url=self.api_url,
                workspace_id=self.workspace_id,
            )
            logger.info(
                f"Successfully got optimization report for task_id={self.task_id}, "
                f"base_version={self.base_version}, ref_version={ref_version}."
            )
            return report
        except Exception as e:
            exception_info = traceback.format_exc()
            logger.error(f"Fetching optimization report failed for job {self.job_id}: {exception_info}")
            raise RuntimeError(f"Fetching optimization report failed for job {self.job_id}: {exception_info}") from e


def create(
    task_id: str,
    base_version: str,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> OptimizeJob:
    """
    Starts an optimization job for a given task and version.

    Parameters:
        task_id (str): Unique identifier for the task.
        version (str): Version of the task/prompt to optimize.
        api_key (Optional[str]): API key for authentication. Defaults to config's API key.
        api_url (Optional[str]): API base URL. Defaults to config's API URL.
        workspace_id (Optional[str]): Workspace ID for authentication. Defaults to config's workspace ID.

    Returns:
        OptimizeJob: OptimizeJob instance with the started job details.

    """
    optimize_job = OptimizeJob.create_optimize_job(task_id, base_version, api_key, api_url, workspace_id)
    return optimize_job


def resume(
    task_id: str,
    base_version: str,
    job_id: str,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> OptimizeJob:
    """
    Resumes an optimization job for a given task and version.
    Parameters:
        task_id (str): Unique identifier for the task.
        version (str): Version of the task/prompt to optimize.
        api_key (Optional[str]): API key for authentication. Defaults to config's API key.
        api_url (Optional[str]): API base URL. Defaults to config's API URL.
        workspace_id (Optional[str]): Workspace ID for authentication. Defaults to config's workspace ID.
    Returns:
        OptimizeJob: OptimizeJob instance with the started job details.
    """
    optimize_job = OptimizeJob(
        task_id=task_id,
        base_version=base_version,
        job_id=job_id,
        api_key=api_key,
        api_url=api_url,
        workspace_id=workspace_id,
    )
    return optimize_job
