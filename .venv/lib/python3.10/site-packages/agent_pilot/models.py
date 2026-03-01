import pydantic
from typing import Any, Dict, List, Literal, Optional, Generic, TypeVar, Union
from pydantic import ConfigDict, computed_field, Field
import logging
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TaskType(str, Enum):
    """Task types for prompt engineering."""

    DEFAULT = "DEFAULT"  # single turn task
    MULTIMODAL = "MULTIMODAL"  # visual reasoning single turn task
    DIALOG = "DIALOG"  # multi turn dialog


class Feedback(pydantic.BaseModel):
    """
    Feedback is the feedback that is sent to the tracking service.
    """

    human_score: Optional[float] = None
    human_analysis: Optional[str] = None
    human_confidence: Optional[float] = None
    metric_score: Optional[float] = None
    metric_analysis: Optional[str] = None
    metric_confidence: Optional[float] = None
    thumb: Optional[str] = None
    comment: Optional[str] = None


class Variable(pydantic.BaseModel):
    name: str
    value: str
    type: Literal["text", "image_url"] = "text"

    @classmethod
    def from_dict_to_variables(cls, variables: Optional[Dict[str, Any]]) -> Optional[List["Variable"]]:
        if variables is None:
            return None
        if not isinstance(variables, dict):
            raise TypeError(f"The variables must be a dictionary, but got {variables}")
        if not all(isinstance(key, str) for key in variables.keys()):
            raise TypeError(f"The variables can only have string keys, but got {variables}")
        if all(isinstance(value, str) for value in variables.values()):
            return [Variable(name=key, type="text", value=value) for key, value in variables.items()]
        if not all(isinstance(value, dict) for value in variables.values()):
            raise TypeError(f"The variables can only have either string or dictionary values, but got {variables}")
        return [Variable(name=var_name, **innder_dict) for var_name, innder_dict in variables.items()]


class TrackingEvent(pydantic.BaseModel):
    """
    TrackingEvent is the event that is sent to the tracking service.

    NOTE: the tracking event is one to one mapping to the TrackingEvent API request body.
    """

    run_type: str
    event_name: str
    run_id: str
    task_id: str
    prompt_version: str
    workspace_id: Optional[str] = None
    session_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    model_name: Optional[str] = None
    input_messages: Optional[List[Dict[str, Any]]] = None
    output_message: Optional[Dict[str, Any]] = None
    prompt_template: Optional[List[Dict[str, Any]]] = None
    variables: Optional[Dict[str, str]] = None
    reference: Optional[Dict[str, str]] = None
    error: Optional[Dict[str, Any]] = None
    token_usage: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    params: Optional[Dict[str, Any]] = None
    properties: Optional[Dict[str, Any]] = None
    feedback: Optional[Feedback] = None
    timestamp: Optional[str] = None
    api_key: Optional[str] = Field(exclude=True, default=None)  # set in the header
    api_url: Optional[str] = Field(exclude=True, default=None)  # set the posting url


class PromptVersion(pydantic.BaseModel):
    task_id: str
    version: str
    messages: Optional[List[Dict[str, Any]]] = None
    variable_names: Optional[List[str]] = Field(
        default=None, description="The variable names for the prompt", alias="variables_name"
    )
    model_name: str
    temperature: float
    top_p: float
    criteria: str = Field(default="", description="The criteria for the prompt", alias="eval_dimension")

    model_config = ConfigDict(populate_by_name=True)

    # TODO: support multi-turn template
    @computed_field
    def prompt(self) -> Optional[str]:  # only for single turn template # type: ignore
        if self.messages and len(self.messages) > 0:
            content = self.messages[0].get("content", self.messages[0].get("Content", None))
            if content and isinstance(content, str):
                return content  # type: ignore
            elif content and isinstance(content, list):
                for message in content:
                    if message.get("type") == "text":
                        return message.get("text")  # type: ignore
                    elif message.get("Type") == "text":
                        return message.get("Text")  # type: ignore
        if self.messages:
            logger.error(f"No prompt template found in messages: {self.messages}")
        return None


class EventStreamChunk(pydantic.BaseModel, Generic[T]):
    """
    EventStreamChunk is the chunk of an event stream.
    """

    event: str
    data: Optional[T] = None


class CreateTaskRequest(pydantic.BaseModel):
    task_name: str = Field(..., description="Task name")
    task_category: Literal["DEFAULT", "MULTIMODAL", "DIALOG"] = Field(..., description="Task category")
    messages: List[Dict[str, Any]] = Field(..., description="Prompt template content")
    variables_types: Optional[Dict[str, str]] = Field(None, description="Variable types")
    model_name: Optional[str] = Field(None, description="Target model name")
    criteria: Optional[str] = Field(None, description="The criteria for evaluation")


class TextContent(pydantic.BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageUrl(pydantic.BaseModel):
    url: str


class ImageContent(pydantic.BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl


class Message(pydantic.BaseModel):
    """
    Represents a message, containing role and content.
    role can be "system", "user", or "assistant".
    """

    role: Literal["system", "user", "assistant"]
    content: Union[str, List[Union[TextContent, ImageContent]]]
