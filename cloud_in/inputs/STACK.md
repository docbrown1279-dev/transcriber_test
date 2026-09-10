# Stack notes — D5.diar-twopass

| Use | Do not |
|---|---|
| Silero VAD + existing merge/premerge knobs | invent new VAD engine |
| Stage1 cheap features: MFCC / spectral flux / energy (+ optional F0) via numpy/scipy/librosa-if-already-present | new heavy deps without need; no second speaker DNN |
| Stage1A / Stage2: WeSpeaker ResNet34 ONNX | pyannote, VBx, Jina |
| AHC and/or spectral clustering on affinity | hard K∈[2,4] prior |
| Windows for 2A: 1.5/0.75; 2B: non-overlap | coarser 3.0/1.5 as speed lever (already rejected) |
