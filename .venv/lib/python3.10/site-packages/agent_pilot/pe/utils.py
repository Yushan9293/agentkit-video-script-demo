import json
import re
from typing import Optional

from agent_pilot.pe.models import GeneratePromptChunk, GeneratePromptStreamResponseChunk


def parse_event_stream_line(
    line: str,
    prompt_chunk: Optional[GeneratePromptStreamResponseChunk] = None,
) -> Optional[GeneratePromptStreamResponseChunk]:
    """
    Parse a single line of an event stream.
    """
    # print(f'line: {line}')
    if prompt_chunk and prompt_chunk.event == "message" and not prompt_chunk.data.content:  # type: ignore
        if line.startswith("data: "):
            regex = r'data: "(?P<data>.*)"'
            match = re.match(regex, line)
            if match:
                # Properly decode escape sequences like \n in the content
                content = match.group("data")
                decoded_content = json.loads(f'"{content}"')
                prompt_chunk.data.content = decoded_content  # type: ignore
                return prompt_chunk
    elif prompt_chunk and prompt_chunk.event == "usage" and not prompt_chunk.data.usage:  # type: ignore
        if line.startswith("data: "):
            regex = r"data: (?P<data>.*)"
            match = re.match(regex, line)
            if match:
                prompt_chunk.data.usage = json.loads(match.group("data"))  # type: ignore
                return prompt_chunk
    elif prompt_chunk and prompt_chunk.event == "error" and not prompt_chunk.data.error:  # type: ignore
        if line.startswith("data: "):
            regex = r"data: (?P<data>.*)"
            match = re.match(regex, line)
            if match:
                prompt_chunk.data.error = match.group("data")  # type: ignore
                return prompt_chunk
    else:
        if line.startswith("event:"):
            regex = r"event: (?P<event>[^:]+)"
            match = re.match(regex, line)
            if match:
                return GeneratePromptStreamResponseChunk(
                    event=match.group("event").strip(),
                    data=GeneratePromptChunk(content="", usage=None, error=None),
                )
    return None
