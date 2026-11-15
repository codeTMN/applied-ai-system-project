# Comparison: full system vs baselines

Run 2026-11-15 15:09 with `python eval.py --compare` (same 22 cases for every variant).

| Variant | All cases | English | Naija | Guardrails | Checks | Avg confidence | Avg time |
|---|---|---|---|---|---|---|---|
| Full system (retrieval + few-shot) | 21/22 (95%) | 11/11 (100%) | 5/6 (83%) | 5/5 (100%) | 79/80 (99%) | 0.86 | 6.0 s |
| No retrieval | 17/22 (77%) | 10/11 (91%) | 2/6 (33%) | 5/5 (100%) | 75/80 (94%) | 0.89 | 6.8 s |
| No few-shot examples | 21/22 (95%) | 11/11 (100%) | 5/6 (83%) | 5/5 (100%) | 79/80 (99%) | 0.87 | 6.5 s |
| Agent mode | 22/22 (100%) | 11/11 (100%) | 6/6 (100%) | 5/5 (100%) | 80/80 (100%) | 0.81 | 10.1 s |
