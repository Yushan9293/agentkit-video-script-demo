import logging
from typing import Generator, Optional

from agent_pilot.config import get_config
from agent_pilot.http_client import get_http_client
from agent_pilot.models import TaskType
from agent_pilot.pe.models import GeneratePromptStreamRequest, GeneratePromptStreamResponseChunk
from agent_pilot.pe.utils import parse_event_stream_line
from agent_pilot.pe.models import DEFAULT_GENERATE_MODEL

logger = logging.getLogger(__name__)


def generate_prompt_stream(
    task_description: str,
    temperature: float = 1.0,
    top_p: float = 0.7,
    model_name: Optional[str] = None,
    feedback: Optional[str] = None,
    current_prompt: Optional[str] = None,
    task_type: TaskType = TaskType.DEFAULT,
    request_id: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Generator[GeneratePromptStreamResponseChunk, None, None]:
    """
    Generate a prompt with streaming response.

    Args:
        rule: The prompt engineering rule.
        temperature: Sampling temperature.
        top_p: Top-p sampling parameter.
        model_name: Optional model name to use.
        feedback: Optional feedback for the generation.
        current_prompt: Current prompt to improve upon.
        task_type: Task type for prompt generation.
        request_id: Optional request ID for tracking.
        api_key: Optional API key to override config.
        api_url: Optional API URL to override config.

    Returns:
        Generator yielding prompt chunks.

    Raises:
        RuntimeError: On API error.
    """
    verbose = get_config().verbose

    action = "GeneratePromptStream"

    if not model_name:
        model_name = DEFAULT_GENERATE_MODEL

    # Create request model
    request = GeneratePromptStreamRequest(
        rule=task_description,
        temperature=temperature,
        top_p=top_p,
        model_name=model_name,
        feedback=feedback,
        current_prompt=current_prompt,
        task_type=task_type,
        request_id=request_id,
    )  # type: ignore

    try:
        response_data, status_code = get_http_client().post(
            action=action,
            data=request.model_dump(by_alias=True, exclude_none=True),
            api_key=api_key,
            api_url=api_url,
            stream=True,
            workspace_id=workspace_id,
        )

        if status_code != 200:
            raise RuntimeError(f"Error generating prompt: {status_code} - {response_data}")

        # the event stream is like event line then data line then empty line:
        # event: message
        # data: {"content": "Hello, world!"}
        #
        # event: error
        # data: {"error": "Error message"}
        prompt_chunk = None
        for line in response_data.iter_lines():  # type: ignore
            decoded_line = line.decode("utf-8").strip()
            logger.debug(f"received line: {decoded_line}")
            prompt_chunk = parse_event_stream_line(decoded_line, prompt_chunk)
            if prompt_chunk and (prompt_chunk.data.content or prompt_chunk.data.usage):  # type: ignore
                yield_data = prompt_chunk
                prompt_chunk = None
                yield yield_data
            elif prompt_chunk and (prompt_chunk.event == "message" or prompt_chunk.event == "usage"):  # type: ignore
                continue
            elif prompt_chunk and prompt_chunk.event == "error":
                logger.error(f"Error generating prompt: {prompt_chunk}")
                continue
            else:
                if verbose:
                    logger.info(f"Received unknown type line: {decoded_line}")
                continue

    except Exception as e:
        logger.error(f"Error generating prompt: {str(e)}")
        raise RuntimeError(f"Error generating prompt: {str(e)}") from e
