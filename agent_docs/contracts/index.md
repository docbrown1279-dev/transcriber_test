
# Contracts index

Draft artifacts of Planner Phase A for the `demo` application. Source of truth for requirements
stays `docs/` (read-only): `docs/dev_specs.md` and `docs/research_results/`.

| Contract | Description |
|---|---|
| [`pipeline_artifacts.md`](pipeline_artifacts.md) | JSON artifacts of every pipeline stage: audio, speech, turns, transcript, quality, suggestions, chapters, insights, report, job |
| [`module_interfaces.md`](module_interfaces.md) | Ports (`Protocol`) per swappable component, registry keys per profile, stub policy, frozen prompt ids, quality library API |
| [`config_profiles.md`](config_profiles.md) | Config schema and `demo` values (limits, thresholds, component keys), `dev`/`prod` deltas, required environment variables |
| [`quality_gates.md`](quality_gates.md) | Automated cloud gates G0–G5 with check ids and thresholds, and the cloud restrictions during a gate run |
| [`llm/README.md`](llm/README.md) | D3 LLM examples: where yaml / prompts / schemas copy to at runtime |
| [`llm/base_llm.yaml`](llm/base_llm.yaml) | Example `config/base_llm.yaml` (gemini / nvidia / qwen) |
| [`llm/prompts/chapter_titles/v1.md`](llm/prompts/chapter_titles/v1.md) | Frozen titles prompt (P1) |
| [`llm/prompts/meeting_insights/v1_extract.md`](llm/prompts/meeting_insights/v1_extract.md) | Frozen extract prompt |
| [`llm/prompts/meeting_insights/v1_report.md`](llm/prompts/meeting_insights/v1_report.md) | Frozen report prompt |
| [`llm/schemas/`](llm/schemas/) | JSON Schema files referenced from `llm.tasks.*.schema` |

Plans (Russian, for humans): [`../plans/draft_demo_roadmap.md`](../plans/draft_demo_roadmap.md),
[`../plans/draft_D4_scope.md`](../plans/draft_D4_scope.md) (current stage, INSTRUCTIONS_READY),
[`../plans/draft_D3_scope.md`](../plans/draft_D3_scope.md) (closed / predecessor),
[`../plans/draft_llm_wrapper.md`](../plans/draft_llm_wrapper.md) (API backends + `base_llm.yaml`),
[`../plans/draft_D2_scope.md`](../plans/draft_D2_scope.md) (closed),
[`../plans/draft_D1_scope.md`](../plans/draft_D1_scope.md) (closed),
[`../plans/draft_architecture.md`](../plans/draft_architecture.md),
[`../plans/draft_cloud_workflow.md`](../plans/draft_cloud_workflow.md),
[`../plans/draft_test_strategy.md`](../plans/draft_test_strategy.md).
