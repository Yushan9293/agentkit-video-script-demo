from typing import Any, Dict, Tuple
import jsonpickle  # type: ignore

from pydantic.v1 import BaseModel as BaseModelV1
from pydantic import BaseModel as BaseModelV2


def default_input_parser(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    def serialize(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
        if not args and not kwargs:
            return None

        if len(args) == 1 and not kwargs:
            return args[0]

        input = list(args)
        if kwargs:
            input.append(kwargs)

        return input

    return {"input": serialize(args, kwargs)}


def method_input_parser(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    def serialize(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
        args = args[1:]

        if not args and not kwargs:
            return None

        if len(args) == 1 and not kwargs:
            return args[0]

        input_list = list(args)
        if kwargs:
            input_list.append(kwargs)

        return input_list

    return {"input": serialize(args, kwargs)}


def default_output_parser(output: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    return {"output": getattr(output, "content", output), "tokensUsage": None}


class PydanticHandler(jsonpickle.handlers.BaseHandler):
    def flatten(self, obj: Any, data: Any) -> Any:
        """Convert Pydantic model to a JSON-friendly dict using model_dump_json()"""
        if isinstance(obj, BaseModelV1):
            return jsonpickle.loads(obj.json(), safe=True)
        elif isinstance(obj, BaseModelV2):
            return jsonpickle.loads(obj.model_dump_json(), safe=True)
        else:
            return jsonpickle.loads(obj.model_dump_json(), safe=True)


PARAMS_TO_CAPTURE = [
    "frequency_penalty",
    "function_call",
    "functions",
    "logit_bias",
    "logprobs",
    "max_tokens",
    "max_completion_tokens",
    "n",
    "presence_penalty",
    "response_format",
    "seed",
    "stop",
    "stream",
    "audio",
    "modalities",
    "temperature",
    "tool_choice",
    "tools",
    "tool_calls",
    "top_p",
    "top_k",
    "top_logprobs",
    "prediction",
    "service_tier",
    "parallel_tool_calls",
    # Additional params
    "extra_headers",
    "extra_query",
    "extra_body",
    "timeout",
]


def filter_params(params: Dict[str, Any]) -> Dict[str, Any]:
    filtered_params = {key: value for key, value in params.items() if key in PARAMS_TO_CAPTURE}
    return filtered_params
