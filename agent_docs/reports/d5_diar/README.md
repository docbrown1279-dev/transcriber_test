# D5 diarization / TTFT research reports

Frozen demo diarization remains **2A** (`window 1.5/0.75`, AHC `0.85`). No production code from these packs.

| Pack | Branch | Verdict |
|---|---|---|
| [ttft_windows](ttft_windows/report.md) | `cursor/d5-ttft-diar` | Keep 1.5/0.75; threshold alone ≠ quality fix |
| [spectral](spectral/report.md) | `cursor/d5-diar-spectral` | M1≠clean B; windows 3.0 not a TTFT lever ([timing](spectral/timing_windows_5min.md)) |
| [twopass](twopass/report.md) | `cursor/d5-diar-twopass` | 2A quality baseline; 2C@0.85 collapse |
| [unit-AHC FOLLOWUP](twopass/FOLLOWUP_unit_ahc.md) | same | **REFUSED** as 2A substitute → file-split |

Next: `agent_docs/plans/ticket_d5_ttft_file_split.md` (branch `cursor/d5-ttft-split` from main when opened).
UI backlog: `ticket_d5_ui_upload_progress.md`.
