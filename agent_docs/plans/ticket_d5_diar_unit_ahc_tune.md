# Тикет: тюнинг unit-embed / якоря / 2C+AHC (скорость при той же точности)

**Статус:** CLOSED — **REFUSED** (2026-09-11)  
**Ветка:** `cursor/d5-diar-twopass` @ `b6b34a3` / `f4a85a1`  
**Отчёт:** `cloud_out/FOLLOWUP_unit_ahc.md` + `FOLLOWUP_unit_ahc.json`  
**Следующий:** [`ticket_d5_ttft_file_split.md`](ticket_d5_ttft_file_split.md)

---

## Вердикт

Unit-path (**21** embed vs **366** у 2A на 5′) **не** замена 2A по качеству.  
Лучший «слушать» кандидат: **T1 AHC 0.60** — ловит clip01 greeting B, но clip02/apartments/ninth хуже 2A. T2/T3 не чинят.  
Локальный gold (match):

| clip | 2A | T1 0.60 |
|---|---:|---:|
| clip01 | 0.93 (B=0) | **0.93 (B=1.0)** |
| clip02 | **1.00** | 0.83 |
| clip03 | **0.99** | 0.90 |
| apartments | **0.80** | 0.64 |
| ninth | **0.91** | 0.73 |

Причина: один вектор на VAD-unit не видит смену спикера **внутри** длинного острова; 2A режет её окнами 1.5/0.75.

---

## Что гоняли (FOLLOWUP)

| id | Идея | Итог |
|---|---|---|
| T1 | AHC grid 0.50–0.80 на unit embeds | 0.60 least-bad; не ≈2A |
| T2 | online centroid assign | oversplit / не 2A |
| T3 | long/loud anchors | почти ≡ T2 (units уже длинные) |
