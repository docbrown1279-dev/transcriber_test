# Silero VAD tune — eval/d1/4

Grid: B0 (baseline 0.5/0.35), B1 (0.35/0.20), B2 (0.25/0.15). `min_speech_ms`=`min_silence_ms`=200.

## Coverage (speech_sec / window)

| kind | window | B0 | B1 | B2 | note |
|---|---|---:|---:|---:|---|
| rescue | `voice_start` | 1.48% | 1.97% | 2.71% | gold 0–13 missing |
| rescue | `voice_long_b` | 0.00% | 0.69% | 1.22% | gold id=5 ~42s hole |
| rescue | `apt_open` | 0.00% | 8.96% | 8.96% | gold id=0 missing |
| rescue | `apt_b_block` | 2.56% | 3.49% | 4.65% | gold B 26–53 missing |
| rescue | `xfmr_tail` | 0.98% | 1.85% | 2.52% | gold B 33–85 missing |
| regression | `apt_flats` | 71.11% | 76.09% | 77.16% | human-good apartments Q |
| regression | `apt_rooms` | 6.76% | 17.78% | 19.20% | human-good rooms |
| regression | `ninth_ready` | 58.67% | 69.33% | 69.33% | human-good ready? |
| regression | `ninth_send` | 9.77% | 13.47% | 14.15% | human-good send plans |
| regression | `ninth_market` | 0.00% | 0.00% | 2.13% | human-good квартирография |

## Rescue delta vs B0 (cover)

- `voice_start`: B1 +0.5%, B2 +1.2% (B0=1.5%)
- `voice_long_b`: B1 +0.7%, B2 +1.2% (B0=0.0%)
- `apt_open`: B1 +9.0%, B2 +9.0% (B0=0.0%)
- `apt_b_block`: B1 +0.9%, B2 +2.1% (B0=2.6%)
- `xfmr_tail`: B1 +0.9%, B2 +1.5% (B0=1.0%)

## Regression delta vs B0 (cover)

- `apt_flats`: B1 +5.0%, B2 +6.0% (B0=71.1%)
- `apt_rooms`: B1 +11.0%, B2 +12.4% (B0=6.8%)
- `ninth_ready`: B1 +10.7%, B2 +10.7% (B0=58.7%)
- `ninth_send`: B1 +3.7%, B2 +4.4% (B0=9.8%)
- `ninth_market`: B1 +0.0%, B2 +2.1% (B0=0.0%)

## Next

If rescue cover rises without regression WARN: pick B1 or B2 into `config/base.yaml` `vad.*`, re-check with ASR smoke on new regions.

## Verdict (auto, 2026-09-05)

- **Regression:** деградации нет — cover на good-окнах не падает (часто растёт).
- **Rescue:** пороги Silero дают лишь **маргинальный** прирост (обычно +0.5…2 п.п.; `apt_open` до +9 п.п.). Длинные дыры (`voice_long_b`, `xfmr_tail`) остаются почти пустыми (~1% cover).
- **Вывод:** крутка `threshold`/`neg_threshold` **не закрывает** проблему attempt 3. Дальше по плану recovery: fallback в дырах (**FSMN** для коммерции / TEN для демо) и/или gain до VAD / per-turn — отдельно.
- **Не менять** `base.yaml` vad на B2 «на удачу» без fallback — пользы мало, риск ложных срабатываний на полном файле не измерен.

