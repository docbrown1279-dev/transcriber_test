# Gate D4.1

**Verdict:** PASS_WITH_WARNINGS

- Phase 0 baseline: PASS
- Mode A batch titles: PASS (1 call / 6 chapters)
- Mode B pipeline: PASS functionally (TTFT ~24s) but WARN on LLM call inflation (14) and suffix dedupe
- Recommendation: enable A in demo; B experimental until commit policy fixed
