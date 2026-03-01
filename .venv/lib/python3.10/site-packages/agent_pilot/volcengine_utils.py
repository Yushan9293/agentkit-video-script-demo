import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)
MONITORED_KEYS = [
    "frequency_penalty",
    "functions",
    "logit_bias",
    "max_tokens",
    "n",
    "presence_penalty",
    "stop",
    "stream",
    "temperature",
    "tool_choice",
    "tools",
    "top_p",
    "top_k",
]


class VolcengineUtils:
    @staticmethod
    def parse_role(role: str) -> str:
        if role == "assistant":
            return "ai"
        return role

    @staticmethod
    def get_property(object: Any, property: str) -> Any:
        if isinstance(object, dict):
            return None if not object.get(property) else object.get(property)
        return getattr(object, property, None)

    @staticmethod
    def parse_message(message: Any) -> Dict[str, Any]:
        return {
            "role": VolcengineUtils.get_property(message, "role"),
            "content": VolcengineUtils.get_property(message, "content"),
            "reasoning_content": VolcengineUtils.get_property(message, "reasoning_content"),
            "tool_calls": VolcengineUtils.get_property(message, "tool_calls"),
            "tool_call_id": VolcengineUtils.get_property(message, "tool_call_id"),
        }

    @staticmethod
    def parse_input(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        messages = [VolcengineUtils.parse_message(message) for message in kwargs["messages"]]
        model_name = kwargs.get("model", None)
        extra = {key: kwargs[key] for key in MONITORED_KEYS if key in kwargs}

        return {"model_name": model_name, "input": messages, "extra": extra}

    @staticmethod
    def parse_output(output: Any, stream: bool = False) -> Dict[str, Any]:
        try:
            return {
                "output": VolcengineUtils.parse_message(output.choices[0].message),
                "tokensUsage": {
                    "completion": output.usage.completion_tokens,
                    "prompt": output.usage.prompt_tokens,
                },
            }
        except Exception as e:
            logging.info(f"[Pilot Probing] Error parsing output: {str(e)}")
            return {
                "output": {},
                "tokensUsage": {
                    "completion": 0,
                    "prompt": 0,
                },
            }
