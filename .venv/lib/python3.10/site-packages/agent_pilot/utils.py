import hashlib
import uuid
from typing import Any, Dict, List, Optional


def clean_nones(value: Any) -> Any:
    """
    Recursively remove all None values from dictionaries and lists, and returns
    the result as a new dictionary or list.
    """
    try:
        if isinstance(value, list):
            return [clean_nones(x) for x in value if x is not None]
        elif isinstance(value, dict):
            return {key: clean_nones(val) for key, val in value.items() if val is not None}
        else:
            return value
    except Exception:
        return value


def create_uuid_from_string(seed_string: str) -> uuid.UUID:
    seed_bytes = seed_string.encode("utf-8")
    sha256_hash = hashlib.sha256()
    sha256_hash.update(seed_bytes)
    hash_hex = sha256_hash.hexdigest()
    uuid_hex = hash_hex[:32]
    uuid_obj = uuid.UUID(uuid_hex)
    return uuid_obj


def get_messages_content(messages: List[Dict[str, Any]], index: int = 0) -> Optional[str]:
    content = messages[index].get("content", messages[index].get("Content", None))
    if content is None:
        return None
    if isinstance(content, list):
        for item in content:
            if item.get("type", item.get("Type", None)) == "text":
                text = item.get("text", item.get("Text", None))
                if isinstance(text, str):
                    return text
                return None
    if isinstance(content, str):
        return content
    return None
