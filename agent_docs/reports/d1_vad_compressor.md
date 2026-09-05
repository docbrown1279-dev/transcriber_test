# VAD compressor A/B — eval/d1/4

Same 5 rescue + 5 regression windows as Silero tune. Silero thresholds = B0 (0.5/0.35).
Audio filter applied **only** for VAD input (simulates `vad_input.wav`); ASR path untouched.

| preset | ffmpeg `-af` |
|---|---|
| `C0_raw` | _(none)_ |
| `C1_comp_light` | acompressor thr≈−30 dBFS ratio=4 makeup×4 |
| `C2_comp_hot` | acompressor ratio=6 makeup×8 + alimiter |
| `C3_dynaudnorm` | dynaudnorm f=150 g=7 |

## Coverage

| kind | window | C0 | C1 | C2 | C3 | note |
|---|---|---:|---:|---:|---:|---|
| rescue | `voice_start` | 1.48% | 25.60% | 34.95% | 43.82% | gold 0–13 missing |
| rescue | `voice_long_b` | 0.00% | 36.11% | 40.53% | 42.82% | gold id=5 ~42s hole |
| rescue | `apt_open` | 0.00% | 28.80% | 46.72% | 53.12% | gold id=0 missing |
| rescue | `apt_b_block` | 2.56% | 31.77% | 42.36% | 48.41% | gold B 26–53 missing |
| rescue | `xfmr_tail` | 0.98% | 31.26% | 49.48% | 54.77% | gold B 33–85 missing |
| regression | `apt_flats` | 71.11% | 87.47% | 83.56% | 87.82% | human-good apartments Q |
| regression | `apt_rooms` | 6.76% | 44.09% | 50.49% | 44.09% | human-good rooms |
| regression | `ninth_ready` | 58.67% | 65.07% | 65.07% | 64.00% | human-good ready? |
| regression | `ninth_send` | 9.77% | 53.56% | 77.14% | 78.15% | human-good send plans |
| regression | `ninth_market` | 0.00% | 24.89% | 66.84% | 52.27% | human-good квартирография |

## Rescue Δ cover vs C0

- `voice_start`: C0=1.5%; C1_comp_light +24.1%, C2_comp_hot +33.5%, C3_dynaudnorm +42.3%
- `voice_long_b`: C0=0.0%; C1_comp_light +36.1%, C2_comp_hot +40.5%, C3_dynaudnorm +42.8%
- `apt_open`: C0=0.0%; C1_comp_light +28.8%, C2_comp_hot +46.7%, C3_dynaudnorm +53.1%
- `apt_b_block`: C0=2.6%; C1_comp_light +29.2%, C2_comp_hot +39.8%, C3_dynaudnorm +45.8%
- `xfmr_tail`: C0=1.0%; C1_comp_light +30.3%, C2_comp_hot +48.5%, C3_dynaudnorm +53.8%

## Regression Δ cover vs C0

- `apt_flats`: C0=71.1%; C1_comp_light +16.4%, C2_comp_hot +12.5%, C3_dynaudnorm +16.7%
- `apt_rooms`: C0=6.8%; C1_comp_light +37.3%, C2_comp_hot +43.7%, C3_dynaudnorm +37.3%
- `ninth_ready`: C0=58.7%; C1_comp_light +6.4%, C2_comp_hot +6.4%, C3_dynaudnorm +5.3%
- `ninth_send`: C0=9.8%; C1_comp_light +43.8%, C2_comp_hot +67.4%, C3_dynaudnorm +68.4%
- `ninth_market`: C0=0.0%; C1_comp_light +24.9%, C2_comp_hot +66.8%, C3_dynaudnorm +52.3%

## Verdict

Compressor **helps** on at least one rescue window (Δ≥5pp and cover≥15%): `voice_start` via C3_dynaudnorm (1%→44%), `voice_long_b` via C3_dynaudnorm (0%→43%), `apt_open` via C3_dynaudnorm (0%→53%), `apt_b_block` via C3_dynaudnorm (3%→48%), `xfmr_tail` via C3_dynaudnorm (1%→55%).
If still weak → dual-path alone is not enough; revisit hole-fallback (FSMN/TEN).
