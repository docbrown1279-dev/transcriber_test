
# Contracts index

Draft artifacts of Planner Phase A for the `demo` application. Source of truth for requirements
stays `docs/` (read-only): `docs/dev_specs.md` and `docs/research_results/`.

| Contract | Description |
|---|---|
| [`pipeline_artifacts.md`](pipeline_artifacts.md) | JSON artifacts of every pipeline stage: audio, speech, turns, transcript, quality, suggestions, chapters, insights, report, job |
| [`module_interfaces.md`](module_interfaces.md) | Ports (`Protocol`) per swappable component, registry keys per profile, stub policy, frozen prompt ids, quality library API |
| [`config_profiles.md`](config_profiles.md) | Config schema and `demo` values (limits, thresholds, component keys), `dev`/`prod` deltas, required environment variables |
| [`quality_gates.md`](quality_gates.md) | Automated cloud gates G0–G5 with check ids and thresholds, and the cloud restrictions during a gate run |
| [`prompts/title_p1_v1.md`](prompts/title_p1_v1.md) | Frozen chapter-title prompt body (P1) for D2 — copy into `src/transcriber/llm/prompts/` |

Plans (Russian, for humans): [`../plans/draft_demo_roadmap.md`](../plans/draft_demo_roadmap.md),
[`../plans/draft_D2_scope.md`](../plans/draft_D2_scope.md) (current stage),
[`../plans/draft_D1_scope.md`](../plans/draft_D1_scope.md) (closed / predecessor),
[`../plans/draft_architecture.md`](../plans/draft_architecture.md),
[`../plans/draft_cloud_workflow.md`](../plans/draft_cloud_workflow.md),
[`../plans/draft_test_strategy.md`](../plans/draft_test_strategy.md).
