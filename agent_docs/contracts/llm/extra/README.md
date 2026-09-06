# Extra config is optional and backend-scoped.

Use `llm.backends.<name>.extra_config` only for parameters that exist on this
client and not on the other (Gemini-only vs OpenAI-compat, or the reverse).

Do **not** put here:

- `base_url` — field on the backend
- `api_key_env`, `model`, `client` — fields on the backend
- `prompt` / `schema` / `max_tokens` — fields on the task

`null` on the backend means no extra file. Example pattern: `no_temperature.yaml`.
