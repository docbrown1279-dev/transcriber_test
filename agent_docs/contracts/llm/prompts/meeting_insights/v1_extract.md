# Prompt `meeting_insights/v1_extract` (frozen for demo)

Origin: research stage 3c extract. Provider-neutral.
Runtime path: `src/transcriber/llm/prompts/meeting_insights/v1_extract.md`
Schema: `src/transcriber/llm/schemas/chapter_extract.json`
Config: `llm.tasks.meeting_insights.extract`

Placeholders (all must be substituted; leftover `{{…}}` is an error):

- `{{chapter_id}}` `{{title}}` `{{start}}` `{{end}}`
- `{{chapter_text}}` — speaker-prefixed non-empty segments
- `{{src_catalog}}` — `segment_id | start-end | SPEAKER` lines

---

You extract facts from one chapter of a Russian business meeting transcript.

Input: chapter text and an allowed-source catalog. There is no audio.
Chapter {{chapter_id}} «{{title}}» ({{start}}–{{end}} s).

Return a single JSON object with these keys:

- `key_points` (array): 2–6 concrete statements (decision, number, condition, agreement)
  that are actually in the text. If the chapter has no such fact, return `[]`.
  Each item: `{"text": "…", "segment_ids": ["s0001"]}`.
  `segment_ids` must be copied from the catalog; at least one id per key point.
- `actions` (array): only if the text states a follow-up action. Else `[]`.
  Each item: `{"text": "…", "segment_ids": ["s0001"]}`.
- `open_questions` (array): only if the text states an unresolved question. Else `[]`.
  Same item shape as `actions`.
- `asr_notes` (array): possible ASR errors; never invent facts. Else `[]`.
  Each item: `{"text": "…"}`.

Rules:

- Do not invent timestamps, speakers, numbers, owners, or tasks that are not in the text.
- Do not output `start`, `end`, or speaker fields — only `segment_ids` from the catalog.
- Do not start any `text` with: «обсуждение», «обсудили», «говорили о», «совещание по», «разговор о».
- Do not copy raw ASR garbage as a fact.
- Do not output markdown fences — JSON object only.
- Language of all string values: Russian.

Allowed sources:
{{src_catalog}}

Chapter text:
{{chapter_text}}
