# Draft — final split diar A/B (V1/V2/V3)

**Status:** prompt ready (paste OK)  
**Stack:** unified normalize + shared VAD + WeSpeaker 0.85

## Intuition

Among ~300–900 windows, cut seams change only a handful → **V1 EOS AHC on concatenated part embeddings** should be very close to full15 (deterministic AHC; not RNG luck). Not a TTFT path.

**V2** = online constrained merge (previous labels must stay).  
**V3** = H1 + one glue/margin tune.

Then stop-line and move on.
