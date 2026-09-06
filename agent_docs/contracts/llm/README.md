# LLM contracts (examples for D3)

Runtime destinations after Phase B:

| Here | Copied to |
|---|---|
| `base_llm.yaml` | `config/base_llm.yaml` |
| `extra/*.yaml` | `config/llm_extra/` (only if a backend sets `extra_config`) |
| `prompts/**` | `src/transcriber/llm/prompts/` |
| `schemas/*.json` | `src/transcriber/llm/schemas/` |

Do not commit secrets. `api_key_env` is a variable name only. `base_url` lives on the backend, not in extra.
