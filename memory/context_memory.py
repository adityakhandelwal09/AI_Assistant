import json
from pathlib import Path

from google.genai import types


DEFAULT_MEMORY_PATH = Path(__file__).with_name("agent_context.json")


def load_context(memory_path=DEFAULT_MEMORY_PATH):
    """Load saved Gemini content history from disk."""
    memory_path = Path(memory_path)
    if not memory_path.exists():
        return []

    try:
        with memory_path.open("r", encoding="utf-8") as memory_file:
            payload = json.load(memory_file)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not load saved memory from {memory_path}: {exc}")
        return []

    if not isinstance(payload, list):
        print(f"Saved memory at {memory_path} is not a list; starting fresh.")
        return []

    try:
        return [types.Content.model_validate(item) for item in payload]
    except Exception as exc:
        print(f"Could not parse saved memory from {memory_path}: {exc}")
        return []


def save_context(content, memory_path=DEFAULT_MEMORY_PATH):
    """Persist Gemini content history to disk as JSON."""
    memory_path = Path(memory_path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    payload = [item.model_dump(mode="json") for item in content]
    temp_path = memory_path.with_suffix(f"{memory_path.suffix}.tmp")

    with temp_path.open("w", encoding="utf-8") as memory_file:
        json.dump(payload, memory_file, indent=2, ensure_ascii=False)
        memory_file.write("\n")

    temp_path.replace(memory_path)
