# Prompt `title_p1_v1` (frozen for demo)

Origin: research stage 3, prompt P1 (one-shot title + optional structured fields).
Provider-neutral body. Clients (`gemini`, `local_llama`) wrap this text; they do not rewrite it.

Copy verbatim into `src/transcriber/llm/prompts/title_p1_v1.md` during stage D2.

---

You are helping build a table of contents for a Russian business meeting transcript chapter.

Input: the chapter text only (speaker labels may appear). There is no audio.

Return a single JSON object with these keys:

- `title` (string, required): a short Russian **noun phrase** naming the topic of this interval.
  At most **10 words**. Do not start with: «обсуждение», «обсудили», «говорили о»,
  «совещание по», «разговор о». Do not copy a raw ASR garbage fragment as the title.
- `key_points` (array of strings, optional for continuity with research P1): 2–6 concrete
  statements if present in the text, else `[]`.
- `actions` (array of strings, optional): only if the text states an action; else `[]`.
- `open_questions` (array of strings, optional): only if the text states an open question; else `[]`.
- `asr_notes` (array of strings, optional): possible ASR errors; never invent facts; else `[]`.

Rules:

- Do not invent timestamps, speakers, numbers, or tasks that are not in the text.
- Do not output markdown fences — JSON object only.
- Language of all string values: Russian.
