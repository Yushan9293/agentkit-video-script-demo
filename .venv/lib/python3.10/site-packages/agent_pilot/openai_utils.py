import json
import logging
from typing import Dict, Any, Optional, TypeVar

logger = logging.getLogger(__name__)
MONITORED_KEYS = [
    "frequency_penalty",
    "functions",
    "logit_bias",
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
    "logprobs",
    "prediction",
    "service_tier",
    "parallel_tool_calls",
]

T = TypeVar("T")


class OpenAIUtils:
    @staticmethod
    def parse_role(role: str) -> str:
        if role == "assistant":
            return "ai"
        else:
            return role

    @staticmethod
    def get_property(object: Any, property: str) -> Any:
        if isinstance(object, dict):
            return None if not object.get(property) else object.get(property)
        else:
            return getattr(object, property, None)

    @staticmethod
    def parse_message(message: Any) -> Dict[str, Any]:
        audio = OpenAIUtils.get_property(message, "audio")
        if audio is not None:
            audio = json.loads(audio.model_dump_json(indent=2, exclude_unset=True))

        # Get refusal value directly without using get_property to preserve False values
        refusal = None
        if isinstance(message, dict):
            refusal = message.get("refusal")
        else:
            refusal = getattr(message, "refusal", None)

        parsed_message = {
            "role": OpenAIUtils.get_property(message, "role"),
            "content": OpenAIUtils.get_property(message, "content"),
            "refusal": refusal,
            "audio": audio,
            "tool_calls": OpenAIUtils.get_property(message, "tool_calls"),
            "tool_call_id": OpenAIUtils.get_property(message, "tool_call_id"),
        }
        return parsed_message

    @staticmethod
    def parse_input(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        messages = [OpenAIUtils.parse_message(message) for message in kwargs["messages"]]
        model_name = kwargs.get("model", None) or kwargs.get("engine", None) or kwargs.get("deployment_id", None)
        extra = {key: kwargs[key] for key in MONITORED_KEYS if key in kwargs}

        return {"model_name": model_name, "input": messages, "extra": extra}

    @staticmethod
    def parse_output(output: Any, stream: bool = False) -> Optional[Dict[str, Any]]:
        try:
            return {
                "output": OpenAIUtils.parse_message(output.choices[0].message),
                "tokensUsage": {
                    "completion": output.usage.completion_tokens,
                    "prompt": output.usage.prompt_tokens,
                },
            }
        except (IndexError, TypeError) as e:
            logging.info("[Pilot Probing] Error parsing output: %s", e)
            return None
        except AttributeError as e:
            logging.info("[Pilot Probing] Error parsing output: %s", e)
            return None
        except Exception as e:
            logging.info("[Pilot Probing] Error parsing output: %s", e)
            return None
