# Final A/B cheat-sheet

All on **one unified gain** + shared VAD.

| ID | Idea | TTFT? |
|---|---|---|
| **V1** | Embed each part → **one AHC at end** on all embeddings | No (quality ceiling ≈ full) |
| **V2** | Per-part clusters → merge into previous; past labels frozen; centroid = CoM, nudge ≤20 tries | Yes |
| **V3** | H1 + one light tune (micro-cluster → previous cluster id, or H3 margin) | Yes |

Refs: `full15`, H1 in `split3_cluster_rebuild`.
