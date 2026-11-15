# Consistency check

Run 2026-11-15 14:36 with `python eval.py --consistency`. Each request was run 3 times; overlap = shared songs / all songs across two runs (1.0 = identical).

| Request | Run 1 vs 2 | Run 1 vs 3 | Run 2 vs 3 | Songs in all 3 runs |
|---|---|---|---|---|
| upbeat songs for a summer road trip | 0.43 | 0.43 | 1.00 | 3/5 |
| I dey feel somehow today | 1.00 | 1.00 | 1.00 | 5/5 |
| smooth jazz for a quiet evening | 1.00 | 1.00 | 1.00 | 5/5 |

**Average overlap: 0.87**
