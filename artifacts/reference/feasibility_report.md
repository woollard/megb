# MEGB-03A Evidence Inventory and Partition Feasibility Report

Generated: 2026-08-01T04:08:45.473552+00:00
Inventory algorithm version: megb-03a-inventory-v1
Case ID algorithm version: case-id-v1
Dataset (HumanEval) package version: 1.0.3
Dataset (EvalPlus) package version: 0.3.1
EvalPlus dataset version: v0.1.10
EvalPlus dataset hash: fe585eb4df8c88d844eeb463ea4d0302
Artifact checksum: 4086bfb647ccf6bc1d2e15b8f15ed9d9f158f4afa93633ea32d14c9367f2dada

## Policy evaluated

- Minimum development cases: 30
- Minimum reference-only cases: 20
- Target development cases (for 5 disjoint 30-case O4 replicates): 150

## Summary

- Tasks inventoried: 164 (expected 164)
- OK (supports disjoint O4 replicates): 139
- LIMITED (meets minimum, overlapping replicates only): 23
- BLOCKED (cannot meet minimum development + reference-only budget): 2
- Tasks with duplicate cases: 98

## BLOCKED tasks (partition construction cannot proceed for these)

Per the epic's no-silent-fallback policy, these tasks are reported explicitly rather than silently reduced or excluded. MEGB-03B must not freeze a partition until each is resolved by an explicit, approved design amendment.

- `HumanEval/39`: 12 unique cases (base=10, plus=2) — only 12 unique cases available; requires at least 30 development + 20 reference-only (50 total)
- `HumanEval/55`: 45 unique cases (base=5, plus=45) — only 45 unique cases available; requires at least 30 development + 20 reference-only (50 total)

## LIMITED tasks (feasible, but only with overlapping O4 replicates)

- `HumanEval/1`: 87 unique cases — only 67 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/100`: 112 unique cases — only 92 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/106`: 104 unique cases — only 84 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/123`: 139 unique cases — only 119 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/130`: 115 unique cases — only 95 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/138`: 113 unique cases — only 93 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/139`: 127 unique cases — only 107 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/147`: 115 unique cases — only 95 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/15`: 135 unique cases — only 115 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/19`: 131 unique cases — only 111 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/24`: 169 unique cases — only 149 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/25`: 145 unique cases — only 125 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/31`: 159 unique cases — only 139 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/36`: 152 unique cases — only 132 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/41`: 79 unique cases — only 59 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/46`: 132 unique cases — only 112 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/5`: 156 unique cases — only 136 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/6`: 69 unique cases — only 49 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/60`: 160 unique cases — only 140 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/63`: 65 unique cases — only 45 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/75`: 95 unique cases — only 75 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/77`: 164 unique cases — only 144 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required
- `HumanEval/83`: 109 unique cases — only 89 development cases available (< target 150); 5 fully disjoint 30-case O4 replicates not possible, overlapping replicates would be required

## Tasks with duplicate cases

- `HumanEval/10`: 1 duplicate case group(s)
- `HumanEval/100`: 5 duplicate case group(s)
- `HumanEval/101`: 1 duplicate case group(s)
- `HumanEval/102`: 2 duplicate case group(s)
- `HumanEval/103`: 1 duplicate case group(s)
- `HumanEval/105`: 1 duplicate case group(s)
- `HumanEval/106`: 4 duplicate case group(s)
- `HumanEval/107`: 5 duplicate case group(s)
- `HumanEval/109`: 1 duplicate case group(s)
- `HumanEval/11`: 1 duplicate case group(s)
- `HumanEval/111`: 3 duplicate case group(s)
- `HumanEval/112`: 1 duplicate case group(s)
- `HumanEval/116`: 2 duplicate case group(s)
- `HumanEval/117`: 7 duplicate case group(s)
- `HumanEval/12`: 1 duplicate case group(s)
- `HumanEval/123`: 4 duplicate case group(s)
- `HumanEval/124`: 1 duplicate case group(s)
- `HumanEval/125`: 1 duplicate case group(s)
- `HumanEval/126`: 1 duplicate case group(s)
- `HumanEval/127`: 1 duplicate case group(s)
- `HumanEval/128`: 1 duplicate case group(s)
- `HumanEval/129`: 2 duplicate case group(s)
- `HumanEval/13`: 1 duplicate case group(s)
- `HumanEval/130`: 10 duplicate case group(s)
- `HumanEval/131`: 2 duplicate case group(s)
- `HumanEval/132`: 4 duplicate case group(s)
- `HumanEval/134`: 2 duplicate case group(s)
- `HumanEval/135`: 1 duplicate case group(s)
- `HumanEval/137`: 2 duplicate case group(s)
- `HumanEval/138`: 8 duplicate case group(s)
- `HumanEval/139`: 4 duplicate case group(s)
- `HumanEval/14`: 1 duplicate case group(s)
- `HumanEval/140`: 1 duplicate case group(s)
- `HumanEval/144`: 1 duplicate case group(s)
- `HumanEval/146`: 1 duplicate case group(s)
- `HumanEval/147`: 4 duplicate case group(s)
- `HumanEval/148`: 5 duplicate case group(s)
- `HumanEval/15`: 2 duplicate case group(s)
- `HumanEval/151`: 1 duplicate case group(s)
- `HumanEval/152`: 1 duplicate case group(s)
- `HumanEval/155`: 2 duplicate case group(s)
- `HumanEval/156`: 8 duplicate case group(s)
- `HumanEval/157`: 2 duplicate case group(s)
- `HumanEval/16`: 1 duplicate case group(s)
- `HumanEval/161`: 1 duplicate case group(s)
- `HumanEval/162`: 1 duplicate case group(s)
- `HumanEval/17`: 2 duplicate case group(s)
- `HumanEval/19`: 2 duplicate case group(s)
- `HumanEval/20`: 5 duplicate case group(s)
- `HumanEval/23`: 1 duplicate case group(s)
- `HumanEval/24`: 4 duplicate case group(s)
- `HumanEval/25`: 1 duplicate case group(s)
- `HumanEval/27`: 1 duplicate case group(s)
- `HumanEval/28`: 1 duplicate case group(s)
- `HumanEval/3`: 1 duplicate case group(s)
- `HumanEval/30`: 1 duplicate case group(s)
- `HumanEval/31`: 7 duplicate case group(s)
- `HumanEval/32`: 2 duplicate case group(s)
- `HumanEval/33`: 3 duplicate case group(s)
- `HumanEval/36`: 4 duplicate case group(s)
- `HumanEval/41`: 4 duplicate case group(s)
- `HumanEval/42`: 1 duplicate case group(s)
- `HumanEval/44`: 11 duplicate case group(s)
- `HumanEval/45`: 1 duplicate case group(s)
- `HumanEval/46`: 4 duplicate case group(s)
- `HumanEval/48`: 1 duplicate case group(s)
- `HumanEval/49`: 1 duplicate case group(s)
- `HumanEval/51`: 1 duplicate case group(s)
- `HumanEval/53`: 2 duplicate case group(s)
- `HumanEval/55`: 5 duplicate case group(s)
- `HumanEval/56`: 2 duplicate case group(s)
- `HumanEval/59`: 3 duplicate case group(s)
- `HumanEval/60`: 4 duplicate case group(s)
- `HumanEval/61`: 3 duplicate case group(s)
- `HumanEval/63`: 5 duplicate case group(s)
- `HumanEval/66`: 1 duplicate case group(s)
- `HumanEval/67`: 1 duplicate case group(s)
- `HumanEval/68`: 1 duplicate case group(s)
- `HumanEval/70`: 1 duplicate case group(s)
- `HumanEval/71`: 3 duplicate case group(s)
- `HumanEval/74`: 1 duplicate case group(s)
- `HumanEval/75`: 2 duplicate case group(s)
- `HumanEval/76`: 3 duplicate case group(s)
- `HumanEval/77`: 7 duplicate case group(s)
- `HumanEval/78`: 6 duplicate case group(s)
- `HumanEval/79`: 2 duplicate case group(s)
- `HumanEval/82`: 1 duplicate case group(s)
- `HumanEval/86`: 1 duplicate case group(s)
- `HumanEval/87`: 1 duplicate case group(s)
- `HumanEval/88`: 2 duplicate case group(s)
- `HumanEval/89`: 5 duplicate case group(s)
- `HumanEval/9`: 1 duplicate case group(s)
- `HumanEval/90`: 2 duplicate case group(s)
- `HumanEval/95`: 7 duplicate case group(s)
- `HumanEval/96`: 10 duplicate case group(s)
- `HumanEval/97`: 8 duplicate case group(s)
- `HumanEval/98`: 1 duplicate case group(s)
- `HumanEval/99`: 1 duplicate case group(s)
