import json
import os
from datetime import datetime
from typing import Dict, List

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shadow_memory.json")
MAX_PERSISTENT_FACTS = 50
MAX_SESSION_MESSAGES = 16  # Keeps system prompt + last 16 turns in RAM


def _load_raw() -> Dict[str, List[dict]]:
    if not os.path.exists(MEMORY_FILE):
        return {"facts": []}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("facts"), list):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"facts": []}


def _save_raw(data: Dict[str, List[dict]]) -> None:
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_memory(fact: str) -> bool:
    fact = fact.strip()
    if not fact:
        return False

    data = _load_raw()
    if any(item["fact"].lower() == fact.lower() for item in data["facts"]):
        return False

    data["facts"].append({
        "fact": fact,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    data["facts"] = data["facts"][-MAX_PERSISTENT_FACTS:]
    _save_raw(data)
    return True


def delete_memory(keyword: str) -> int:
    kw = keyword.lower().strip()
    if not kw:
        return 0
    data = _load_raw()
    before = len(data["facts"])
    data["facts"] = [item for item in data["facts"] if kw not in item["fact"].lower()]
    removed = before - len(data["facts"])
    if removed:
        _save_raw(data)
    return removed


def process_memory_directive(directive: str) -> bool:
    """Parse 'SAVE: ...' or 'FORGET: ...' from response['memory']. Returns True if disk changed."""
    if not isinstance(directive, str):
        return False
    text = directive.strip()
    if not text:
        return False

    upper = text.upper()
    if upper.startswith("SAVE:"):
        return save_memory(text[5:].strip())
    if upper.startswith("FORGET:"):
        return delete_memory(text[7:].strip()) > 0
    # Fallback: if model wrote a direct fact without the SAVE: prefix
    return save_memory(text)


def get_memory_block() -> str:
    facts = _load_raw()["facts"]
    if not facts:
        return "None yet."
    return "\n".join(f"- {item['fact']}" for item in facts)


def trim_session_memory(msg: list) -> list:
    """Temporary session memory manager: preserves msg[0] (system prompt) + recent turns."""
    if len(msg) <= MAX_SESSION_MESSAGES + 1:
        return msg
    return [msg[0]] + msg[-MAX_SESSION_MESSAGES:]