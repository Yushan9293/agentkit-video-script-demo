import logging
import traceback
from typing import Optional, Dict, List, Any, Callable, TypeVar, Awaitable, AsyncIterator, cast, Union
import uuid
from .parsers import default_input_parser, default_output_parser  # type: ignore
from agent_pilot.volcengine_utils import VolcengineUtils
import jsonpickle  # type: ignore
from datetime import datetime, timezone
from agent_pilot.config import get_config
from agent_pilot.context import get_parent_run_id, tags_ctx, RunManager, queue, Run
from agent_pilot.utils import create_uuid_from_string, clean_nones
from agent_pilot.models import TrackingEvent
from agent_pilot.parsers import filter_params
from importlib.metadata import PackageNotFoundError
from agent_pilot.openai_utils import OpenAIUtils
import packaging.version
from pydantic.v1 import BaseModel as BaseModelV1
from pydantic import BaseModel as BaseModelV2
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
run_manager = RunManager()

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_SAMPLE_RATE = 1.0


def generate_run_id() -> str:
    return str(uuid.uuid4())


def track_event(
    run_type: str,
    event_name: str,
    run_id: str,
    task_id: str,
    version: str,
    workspace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    model_name: Optional[str] = None,
    input_messages: Optional[List[Dict[str, Any]]] = None,
    output_message: Optional[Dict[str, Any]] = None,
    prompt_template: Optional[List[Dict[str, Any]]] = None,
    variables: Optional[Dict[str, str]] = None,
    reference: Optional[Union[str, Dict[str, Any]]] = None,
    error: Optional[Dict[str, Any]] = None,
    token_usage: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    timestamp: Optional[str] = None,
    feedback: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    runtime: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    callback_queue: Any = None,
) -> None:
    try:
        config = get_config()
        api_key = api_key or config.api_key
        api_url = api_url or config.api_url

        # Ensure parent_run_id is correctly typed
        parent_id = get_parent_run_id(parent_run_id or "", run_type, api_key or "", run_id)
        # We need to generate a UUID that is unique by run_id / api_key pair
        # in case of multiple concurrent callback handler use
        run_id = str(create_uuid_from_string(str(run_id) + str(api_key)))

        if config.verbose:
            logger.info(
                f"Tracking event: {event_name} for run_id: {run_id} \n"
                f"task_id: {task_id} \n"
                f"version: {version} \n"
                f"session_id: {session_id} \n"
                f"parent_run_id: {parent_id} \n"
                f"model_name: {model_name} \n"
                f"input_messages: {input_messages} \n"
                f"output_message: {output_message} \n"
                f"prompt_template: {prompt_template} \n"
                f"variables: {variables} \n"
                f"reference: {reference} \n"
                f"error: {error} \n"
                f"token_usage: {token_usage} \n"
                f"tags: {tags} \n"
                f"feedback: {feedback} \n"
            )
        if isinstance(reference, str):
            reference = {"role": "assistant", "content": reference}

        # 移除 TrackingEvent 不支持的参数
        current_tags = tags or tags_ctx.get()
        event = TrackingEvent(
            run_type=run_type,
            event_name=event_name,
            run_id=run_id,
            task_id=task_id,
            prompt_version=version,
            workspace_id=workspace_id,
            session_id=session_id,
            parent_run_id=parent_id,
            model_name=model_name,
            input_messages=input_messages,
            output_message=output_message,
            prompt_template=prompt_template,
            variables=variables,
            feedback=feedback,  # type: ignore
            reference=reference,
            error=error,
            token_usage=token_usage,
            tags=current_tags,
            params=params,
            properties={"runtime": runtime or "pilot-probing-py"},
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        )

        if api_key:
            event.api_key = api_key
        if api_url:
            event.api_url = api_url

        if callback_queue is not None:
            callback_queue.append(event)
        else:
            queue.append(event)

        if config.verbose:
            try:
                serialized_event = jsonpickle.encode(clean_nones(event), unpicklable=False, indent=4)
                logger.info(f"\nAdd event: {serialized_event}\n")
            except Exception as e:
                logger.warning(f"Could not serialize event: {event}\n {e}")

    except Exception as e:
        logger.exception(f"Error in `track_event`: {str(e)}")


def default_stream_handler(fn: Callable[..., Any], run_id: str, name: str, type: str, *args: Any, **kwargs: Any) -> Any:
    try:
        stream = fn(*args, **kwargs)

        choices: List[Dict[str, Any]] = []
        tokens = 0

        for chunk in stream:
            tokens += 1
            if not chunk.choices:
                # Azure
                continue

            choice = chunk.choices[0]
            index = choice.index

            content = choice.delta.content
            role = choice.delta.role
            function_call = choice.delta.function_call
            tool_calls = choice.delta.tool_calls

            if len(choices) <= index:
                choices.append({
                    "message": {
                        "role": role,
                        "content": content or "",
                        "function_call": {},
                        "tool_calls": [],
                    }
                })

            if content:
                choices[index]["message"]["content"] += content

            if role:
                choices[index]["message"]["role"] = role

            if hasattr(function_call, "name"):
                choices[index]["message"]["function_call"]["name"] = function_call.name

            if hasattr(function_call, "arguments"):
                choices[index]["message"]["function_call"].setdefault("arguments", "")
                choices[index]["message"]["function_call"]["arguments"] += function_call.arguments

            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    existing_call_index = next(
                        (
                            index
                            for (index, tc) in enumerate(choices[index]["message"]["tool_calls"])
                            if tc.index == tool_call.index
                        ),
                        -1,
                    )

                if existing_call_index == -1:
                    choices[index]["message"]["tool_calls"].append(tool_call)

                else:
                    existing_call = choices[index]["message"]["tool_calls"][existing_call_index]
                    if hasattr(tool_call, "function") and hasattr(tool_call.function, "arguments"):
                        existing_call.function.arguments += tool_call.function.arguments

            yield chunk
    finally:
        stream.close()

    output = OpenAIUtils.parse_message(choices[0]["message"])
    track_event(
        type,
        "end",
        run_id,
        task_id="",  # Placeholder task_id
        version="",  # Placeholder version
        model_name=name,
        output_message=output,
        token_usage={"completion": tokens, "prompt": None},
    )
    return


def wrap(
    fn: Callable[..., T],
    run_type: Optional[str] = None,
    run_id: Optional[str] = None,
    model_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    input_parser: Callable[..., Dict[str, Any]] = default_input_parser,
    output_parser: Callable[[Any, bool], Optional[Dict[str, Any]]] = default_output_parser,
    api_key: Optional[str] = None,
    stream: bool = False,
    stream_handler: Callable[..., T] = default_stream_handler,
    sample_rate: Optional[float] = None,
) -> Callable[..., T]:
    def sync_wrapper(*args: Any, **kwargs: Any) -> T:
        output: Optional[T] = None

        if sample_rate is not None:
            if random.random() > sample_rate:
                kwargs.pop("parent", None)
                kwargs.pop("task_id", None)
                kwargs.pop("version", None)
                kwargs.pop("tags", None)
                kwargs.pop("prompt_template", None)
                kwargs.pop("variables", None)
                output = fn(*args, **kwargs)
                output.run = None  # type: ignore
                return output
        nonlocal stream
        stream = stream or kwargs.get("stream", False)  # type: ignore

        parent_run_id = kwargs.pop("parent", run_manager.current_run_id)
        task_id = kwargs.pop("task_id", None)
        version = kwargs.pop("version", None)

        run = run_manager.start_run(run_id, task_id, version, parent_run_id)
        if run is None:
            # Create a fallback run with default values if start_run fails
            run = Run(run_id or "", parent_run_id, task_id, version)

        try:
            prompt_template = kwargs.pop("prompt_template", None)
            variables = kwargs.pop("variables", None)

            try:
                params = filter_params(kwargs)

                parsed_input = input_parser(*args, **kwargs)

                track_event(
                    run_type or "",
                    "start",
                    run_id=run.id,
                    task_id=str(run.task_id or ""),
                    version=str(run.version or ""),
                    parent_run_id=parent_run_id,
                    input_messages=parsed_input["input"],
                    model_name=model_name or parsed_input["model_name"],
                    params=params,
                    prompt_template=prompt_template,
                    variables=variables,
                    tags=kwargs.pop("tags", None) or tags or tags_ctx.get(),
                    api_key=api_key,
                )
            except Exception as e:
                logging.exception(e)

            if stream:
                return stream_handler(
                    fn,
                    run.id,
                    str(run.task_id or ""),
                    str(run.version or ""),
                    model_name or parsed_input["model_name"],
                    run_type or "",
                    *args,
                    **kwargs,
                )

            try:
                output = fn(*args, **kwargs)

                if isinstance(output, (BaseModelV1, BaseModelV2)):
                    output.run = run  # type: ignore

            except Exception as e:
                track_event(
                    run_type or "",
                    "error",
                    run.id,
                    task_id=str(run.task_id or ""),
                    version=str(run.version or ""),
                    error={"message": str(e), "stack": traceback.format_exc()},
                    api_key=api_key,
                )

                # rethrow error
                raise e

            try:
                parsed_output = output_parser(output, stream)

                if parsed_output is not None:
                    track_event(
                        run_type or "",
                        "end",
                        run.id,
                        task_id=str(run.task_id or ""),
                        version=str(run.version or ""),
                        prompt_template=prompt_template,
                        variables=variables,
                        model_name=model_name or parsed_input["model_name"],
                        output_message=parsed_output["output"],
                        token_usage=parsed_output["tokensUsage"],
                        api_key=api_key,
                    )
                return output
            except Exception as e:
                logger.exception(f"Error in output parsing: {e}")
                return output

        finally:
            run_manager.end_run(run.id)

        return output

    return sync_wrapper


async def async_stream_handler(
    fn: Callable[..., AsyncIterator[Any]],
    run_id: str,
    task_id: Optional[str],
    version: Optional[str],
    model_name: Optional[str],
    type: Optional[str],
    *args: Any,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    # 修复异步流处理的类型问题
    stream_iterator = fn(*args, **kwargs)

    choices: List[Dict[str, Any]] = []
    tokens = 0

    async for chunk in stream_iterator:
        tokens += 1
        if not chunk.choices:
            # Happens with Azure
            continue

        choice = chunk.choices[0]
        index = choice.index

        content = choice.delta.content
        role = choice.delta.role
        tool_calls = choice.delta.tool_calls

        if len(choices) <= index:
            choices.append({
                "message": {
                    "role": role,
                    "content": content or "",
                    "function_call": {},
                    "tool_calls": [],
                }
            })

        if content:
            choices[index]["message"]["content"] += content

        if role:
            choices[index]["message"]["role"] = role

        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                existing_call_index = next(
                    (
                        index
                        for (index, tc) in enumerate(choices[index]["message"]["tool_calls"])
                        if tc.index == tool_call.index
                    ),
                    -1,
                )

            if existing_call_index == -1:
                choices[index]["message"]["tool_calls"].append(tool_call)

            else:
                existing_call = choices[index]["message"]["tool_calls"][existing_call_index]
                if hasattr(tool_call, "function") and hasattr(tool_call.function, "arguments"):
                    existing_call.function.arguments += tool_call.function.arguments

        yield chunk

    output = OpenAIUtils.parse_message(choices[0]["message"])
    track_event(
        type or "",
        "end",
        run_id,
        task_id=str(task_id or ""),
        version=str(version or ""),
        output_message=output,
        token_usage={"completion": tokens, "prompt": None},
    )


def async_wrap(
    fn: Callable[..., Awaitable[T]],
    type: Optional[str] = None,
    model_name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    input_parser: Callable[..., Dict[str, Any]] = default_input_parser,
    output_parser: Callable[[Any, bool], Optional[Dict[str, Any]]] = default_output_parser,
    app_key: Optional[str] = None,
    stream: bool = False,
    sample_rate: Optional[float] = None,
) -> Callable[..., Awaitable[Any]]:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if sample_rate is not None:
            if random.random() > sample_rate:
                kwargs.pop("parent", None)
                kwargs.pop("task_id", None)
                kwargs.pop("version", None)
                kwargs.pop("tags", None)
                kwargs.pop("prompt_template", None)
                kwargs.pop("variables", None)
                output = await fn(*args, **kwargs)
                output.run = None  # type: ignore
                return output

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            output: Optional[T] = None

            parent_run_id = kwargs.pop("parent", run_manager.current_run_id)
            task_id = kwargs.pop("task_id", None)
            version = kwargs.pop("version", None)
            run = run_manager.start_run(parent_run_id=parent_run_id, task_id=task_id, version=version)
            if run is None:
                # Create a fallback run with default values if start_run fails
                run = Run(None, parent_run_id, task_id, version)

            try:
                try:
                    params = filter_params(kwargs)
                    parsed_input = input_parser(*args, **kwargs)

                    track_event(
                        type or "",
                        "start",
                        run_id=run.id,
                        task_id=str(run.task_id or ""),
                        version=str(run.version or ""),
                        parent_run_id=parent_run_id,
                        input_messages=parsed_input["input"],
                        model_name=model_name or parsed_input["model_name"],
                        params=params,
                        tags=kwargs.pop("tags", None) or tags or tags_ctx.get(),
                        api_key=app_key,
                    )
                except Exception as e:
                    logger.exception(e)

                try:
                    output = await fn(*args, **kwargs)
                    if isinstance(output, (BaseModelV1, BaseModelV2)):
                        output.run = run  # type: ignore

                except Exception as e:
                    track_event(
                        type or "",
                        "error",
                        run.id,
                        task_id=str(run.task_id or ""),
                        version=str(run.version or ""),
                        error={"message": str(e), "stack": traceback.format_exc()},
                        api_key=app_key,
                    )

                    # rethrow error
                    raise e

                try:
                    parsed_output = output_parser(output, kwargs.get("stream", False))

                    if parsed_output is not None:
                        track_event(
                            type or "",
                            "end",
                            run.id,
                            task_id=str(run.task_id or ""),
                            version=str(run.version or ""),
                            model_name=model_name or parsed_input["model_name"],
                            output_message=parsed_output["output"],
                            token_usage=parsed_output["tokensUsage"],
                            api_key=app_key,
                        )
                    return output
                except Exception as e:
                    logger.exception(f"Error in output parsing: {e}")
                    return output

            finally:
                run_manager.end_run(run.id)

        async def async_stream_wrapper(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            parent_run_id = kwargs.pop("parent", run_manager.current_run_id)
            task_id = kwargs.pop("task_id", None)
            version = kwargs.pop("version", None)
            run = run_manager.start_run(parent_run_id=parent_run_id, task_id=task_id, version=version)
            if run is None:
                # Create a fallback run with default values if start_run fails
                run = Run(None, parent_run_id, task_id, version)

            try:
                try:
                    params = filter_params(kwargs)
                    parsed_input = input_parser(*args, **kwargs)

                    track_event(
                        type or "",
                        "start",
                        run_id=run.id,
                        parent_run_id=parent_run_id,
                        task_id=str(run.task_id or ""),
                        version=str(run.version or ""),
                        input_messages=parsed_input["input"],
                        model_name=model_name or parsed_input["model_name"],
                        tags=kwargs.pop("tags", None) or tags or tags_ctx.get(),
                        params=params,
                        api_key=app_key,
                    )
                except Exception as e:
                    logger.exception(e)

                # 修复异步迭代器处理
                fn_callable = cast(Callable[..., AsyncIterator[Any]], fn)
                handler = async_stream_handler(
                    fn_callable,
                    run.id,
                    str(run.task_id or ""),
                    str(run.version or ""),
                    model_name or parsed_input["model_name"],
                    type or "",
                    *args,
                    **kwargs,
                )

                # 直接产生异步迭代器的结果
                async for chunk in handler:
                    yield chunk

            finally:
                run_manager.end_run(run.id)

        nonlocal stream
        stream = stream or kwargs.get("stream", False)  # type: ignore
        if stream:
            return async_stream_wrapper(*args, **kwargs)
        else:
            return await async_wrapper(*args, **kwargs)

    return wrapper


def probing(object: Any, sample_rate: float = DEFAULT_SAMPLE_RATE) -> Any:
    try:
        package_name = object.__class__.__module__.split(".")[0]

        if package_name == "volcenginesdkarkruntime":
            client_name = getattr(type(object), "__name__", None)
            if client_name == "Ark":
                try:
                    object.chat.completions.create = wrap(
                        object.chat.completions.create,
                        "llm",
                        input_parser=VolcengineUtils.parse_input,
                        output_parser=VolcengineUtils.parse_output,
                        sample_rate=sample_rate,
                    )

                except Exception:
                    logging.info(
                        "Please use `agent_pilot.probing(client)` after initializing the Volcengine ArkRuntime client"
                    )
            elif client_name == "AsyncArk":
                try:
                    object.chat.completions.create = async_wrap(
                        object.chat.completions.create,
                        "llm",
                        input_parser=VolcengineUtils.parse_input,
                        output_parser=VolcengineUtils.parse_output,
                        sample_rate=sample_rate,
                    )
                except Exception:
                    logging.info(
                        "Please use `agent_pilot.probing(client)` after "
                        "initializing the Volcengine AsyncArkRuntime client"
                    )
            else:
                logger.warning(f"Unsupported client: {client_name} not in [Ark, AsyncArk]")
            return object

        if package_name == "openai":
            try:
                from importlib.metadata import version

                installed_version = version("openai")
                if packaging.version.parse(installed_version) >= packaging.version.parse("1.0.0"):
                    client_name = getattr(type(object), "__name__", None)
                    if client_name == "openai" or client_name == "OpenAI" or client_name == "AzureOpenAI":
                        try:
                            # 当前不使用 parse_legacy_input 和 parse_legacy_output，直接使用标准的 parse 函数
                            object.chat.completions.create = wrap(
                                object.chat.completions.create,
                                "llm",
                                input_parser=OpenAIUtils.parse_input,
                                output_parser=OpenAIUtils.parse_output,
                                sample_rate=sample_rate,
                            )
                        except Exception:
                            logging.info("Please use `agent_pilot.probing(client)`after initializing the OpenAI client")
                        try:
                            # 对于普通的 completions 接口，也使用标准的 parse 函数
                            object.completions.create = wrap(
                                object.completions.create,
                                "llm",
                                input_parser=OpenAIUtils.parse_input,
                                output_parser=OpenAIUtils.parse_output,
                                sample_rate=sample_rate,
                            )
                        except Exception:
                            logger.warning(
                                "Please use `agent_pilot.probing(client)` after initializing the OpenAI client"
                            )
                        return object
                    if client_name == "AsyncOpenAI" or client_name == "AsyncAzureOpenAI":
                        try:
                            object.chat.completions.create = async_wrap(
                                object.chat.completions.create,
                                "llm",
                                input_parser=OpenAIUtils.parse_input,
                                output_parser=OpenAIUtils.parse_output,
                                sample_rate=sample_rate,
                            )
                        except Exception:
                            logging.info(
                                "Please use `agent_pilot.probing(client)` after initializing the AsyncOpenAI client"
                            )
                        try:
                            # 对于异步的 completions 接口，也使用标准的 parse 函数
                            object.completions.create = async_wrap(
                                object.completions.create,
                                "llm",
                                input_parser=OpenAIUtils.parse_input,
                                output_parser=OpenAIUtils.parse_output,
                                sample_rate=sample_rate,
                            )
                        except Exception:
                            logger.warning(
                                "Please use `agent_pilot.probing(client)` after initializing the AsyncOpenAI client"
                            )
                        return object
                else:
                    logger.warning("Please use `agent_pilot.probing(client)` for OpenAI client version >= 1.0.0")
            except PackageNotFoundError:
                pass
    except (PackageNotFoundError, AttributeError):
        logger.debug("you need to install openai/volcengine-python-sdk[ark] to monitor your LLM calls")
    except Exception as e:
        logger.exception(f"Error in monitor: {e}")

    return object


def track_feedback(
    task_id: str,
    version: str,
    run_id: str,
    feedback: Dict[str, Any],
    workspace_id: Optional[str] = None,
) -> None:
    """
    Track feedback for a given run.

    Args:
        run_id (str): The ID of the run to track feedback for.
        feedback (Dict[str, Any]): The feedback to track.
    """
    track_event(
        run_type="feedback",
        event_name="feedback",
        run_id=run_id,
        task_id=task_id,
        version=version,
        feedback=feedback,
        workspace_id=workspace_id,
    )


def flush() -> None:
    """
    Flush all pending tracking events immediately.

    This function forces the consumer to send all queued events to the server
    immediately, rather than waiting for the normal batch interval.

    This is useful when you want to ensure all events are sent before the
    program exits or at specific points in your application.

    Example:
        import agent_pilot as ap

        # Your tracking code here
        ap.track_event(...)

        # Force immediate flush of all pending events
        ap.flush()
    """
    try:
        queue.flush()
    except Exception as e:
        logger.exception(f"Error in flush: {e}")
