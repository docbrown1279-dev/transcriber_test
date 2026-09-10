# Progress log (append-only)

- 2026-09-10T13:51:39+03:00 cloud infra: prior handoffs used; no .cursor/environment.json — rely on Dockerfile/uv sync (note)
- 2026-09-10T13:51:39+03:00 handoff D5.TTFT-diar cursor/d5-ttft-diar (windows+cluster tuner; no gold; no H0)
- 2026-09-10T16:15:28+03:00 handoff D5.diar-spectral cursor/d5-diar-spectral (spectral/hybrid; 5min timing; no crumb-primary)
- 2026-09-10T13:22:00+00:00 cloud D5.diar-spectral: M1 spectral recovers clip01 [42,45] solo cluster; M2 oversplits; 5min embed ~11.6s cold load 2.1s; report in cloud_out/; no PR
- 2026-09-10T14:22:00+00:00 cloud D5.diar-spectral timing_windows_5min: 1.5/0.75=366 win 11.57s vs 3.0/1.5=176 win 10.88s (same VAD); no PR
