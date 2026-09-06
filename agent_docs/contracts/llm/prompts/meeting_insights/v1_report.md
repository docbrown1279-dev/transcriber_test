# Prompt `meeting_insights/v1_report` (frozen for demo)

Origin: research stages 3b/3c — one summary call after merged insights.
Runtime path: `src/transcriber/llm/prompts/meeting_insights/v1_report.md`
Schema: `src/transcriber/llm/schemas/meeting_report.json`
Config: `llm.tasks.meeting_insights.report`

Placeholders: `{{chapter_index}}`, `{{insights_json}}`.
Do not send the full meeting ASR. The model must not invent timestamps.

---

You write a short draft protocol for a Russian business meeting.

Input: chapter index and per-chapter insights already extracted from the transcript.
There is no audio. Produce a working draft, not a final signed protocol.

Return a single JSON object with these keys:

- `summary` (string): 1–3 short Russian paragraphs. What the meeting was about,
  what was agreed or left open. No invented decisions.
- `key_moments` (array): **5–12** items, the strongest facts from the insights.
  Each item: `{"text": "…", "chapter_id": "C01", "segment_id": "s0008"}`.
  `chapter_id` and `segment_id` must appear in the input insights (`src`).
  Prefer numbers, conditions, agreements, explicit next steps. Drop filler.

Rules:

- Do not invent timestamps, speakers, names, numbers, or owners.
- Do not output `start`, `end`, or speaker fields.
- Do not start `summary` or any `text` with: «обсуждение», «обсудили»,
  «говорили о», «совещание по», «разговор о».
- Do not dump every chapter as a section — that belongs in insights, not here.
- Do not output markdown fences — JSON object only.
- Language of all string values: Russian.

Chapter index:
{{chapter_index}}

Insights:
{{insights_json}}
