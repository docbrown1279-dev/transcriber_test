# Prompt `chapter_titles/v1_batch` (D4.1 mode A)

Provider-neutral. One call titles many chapters.
Schema: `schemas/chapter_titles_batch.json`
Config: `llm.tasks.chapter_titles` may point here when `titles_mode: batch`.

---

You are helping build a table of contents for a Russian business meeting.

Input: several chapters, each with an id and transcript text (speaker labels may appear). There is no audio.

Return a single JSON object:

- `titles` (array, required): one object per input chapter, **same order**, each with:
  - `id` (string): the chapter id from the input (e.g. `C00`)
  - `title` (string): short Russian **noun phrase**, at most **10 words**.
    Do not start with: «обсуждение», «обсудили», «говорили о», «совещание по», «разговор о».
    Do not copy raw ASR garbage as the title.
    Titles must be unique across the list.

Rules:

- Do not invent timestamps, speakers, numbers, or tasks absent from that chapter's text.
- Do not output markdown fences — JSON object only.
- Language of all string values: Russian.
- Cover every input chapter id exactly once.
