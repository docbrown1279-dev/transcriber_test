# Regression — test_voice pipeline

**Verdict:** `PASS`

Soft gate: FAIL here means **manual review required**, not an automatic merge block.

Job dir: `/tmp/pytest-of-app/pytest-0/test_reg_voice_pipeline_soft0/reg_test_voice`

| id | ok | detail |
|---|---|---|
| REG.VAD.IoU | True | iou=0.718 threshold>=0.700 hyp_regions=13 |
| REG.DIAR.speakers | True | speaker_count=2 band=[2,4] |
| REG.ASR.ru_ratio | True | russian_word_ratio=1.000 threshold>=0.900 words=112 |
| REG.ASR.latin | True | latin_chars=0 max=0 |
