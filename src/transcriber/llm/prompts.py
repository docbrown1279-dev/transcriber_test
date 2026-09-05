"""Loading of immutable, package-owned LLM prompts."""

from pathlib import Path


def load_prompt(prompt_id: str) -> str:
    """Загружает зафиксированный markdown-промпт по безопасному идентификатору."""
    if not prompt_id or Path(prompt_id).name != prompt_id:
        raise ValueError(f"Invalid prompt id: {prompt_id!r}")
    prompt_path = Path(__file__).with_name("prompts") / f"{prompt_id}.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt not found: {prompt_id}")
    return prompt_path.read_text(encoding="utf-8")
