# Day 3 — PDF extraction rework (2026-09-30)

The retrieval index was rebuilt after finding that **every chunk in it was
semantically damaged**. Four defects, each of which only became visible once
the previous one was fixed.

## Why this was hard to see

Retrieval *scores* looked healthy throughout — embeddings still matched on
topical keywords even when the underlying sentences were spliced together from
two different columns. `day3_retrieval.md` reported "all 10 queries confident"
against an index that was substantially garbage. Nothing in the metrics said
anything was wrong; the only tell was reading the passages.

## 1. Two-column interleaving

The FAA circulars are two-column. `page.extract_text()` reads straight across
the full page width, so it alternates between columns line by line.

**AC_43.13-1B page 46, before:**

```
(d) Check ribs on either side of strut   physical damage or decay. When removing
attach points for missing or loose rib-to-spar   metal fasteners from wood, check for evidence
        ^ left column                             ^ right column, welded on
```

**After:**

```
(d) Check ribs on either side of strut attach points for missing or loose
rib-to-spar attach nails.
(e) Check ribs on either side of strut attach points for cracks where the cap
strips pass over and under the spars.
```

`find_gutter()` locates the column separator per page and reads each column in
order. Pages with no gutter — contents, tables, figures, the title page — fall
back to whole-page extraction, which is correct rather than a failure.

## 2. The first fix was too strict, and quietly left two documents broken

The initial detector required an **8pt** clear vertical band. Real gutters in
this corpus are **1-2pt** wide. Result:

| Document | two-column pages detected (first fix) | (corrected) |
|---|---:|---:|
| AC_43.13-1B | 415 / 643 | 434 |
| AC_65-15A | **19 / 608** | **496** |
| AC_20-106 | 16 / 92 | 62 |

AC_65-15A is the largest document in the corpus and was still almost entirely
shredded *after* the "fix" was applied. It was caught only by noticing that
19/608 was implausible next to 415/643 in a sibling document.

The corrected detector counts how many words **cross** each x-position and
takes the minimum, rather than demanding a completely empty band. That handles
narrow gutters and also tolerates a full-width heading spanning the columns,
which previously vetoed the whole page.

## 3. Hyphenation splitting words

The typesetting hyphenates across line breaks, and extraction preserves a
**soft hyphen (U+00AD)** — invisible, but present in the text:

```
before:  "pro­\ntected"   "ap­\nplying"   "col­\nlector"
after:   "protected"       "applying"       "collector"
```

This matters beyond tidiness: `"protected"` and `"pro"` + `"tected"` are
different token sequences, so the embedding model was losing recall on every
hyphenated term, and the LLM was reading broken words.

## 4. Table-of-contents lines indexed as content

Contents entries are mostly dot leaders and carry almost no information, but
they embed close to any query mentioning their heading words — so they were
winning retrieval slots from real guidance.

Measured separation on this corpus:

| | dot ratio | alphanumeric ratio |
|---|---|---|
| contents/index chunks | 0.50 – 0.76 | **0.20 – 0.39** |
| real prose | 0.01 – 0.02 | **0.81 – 0.82** |

Nothing falls between 0.39 and 0.81, so the cut at `MIN_ALNUM_RATIO = 0.55` is
not a close judgement. **343 chunks dropped.**

`"pitting corrosion depth limits"`, before:

```
0.572  SECTION 3. CORROSION PROTECTION MEASURES FOR BASIC MATERIALS
       6-29. General...............................................
0.571  Figure 6-5(b). Pitting Corrosion (Magnified Cross Section) ...........
```

after:

```
0.554  ...seen as a general dulling of the surface, and if allowed to continue,
       the surface becomes rough and possibly frosted...
0.541  a. Remove rough edges and all corrosion from the damaged area. All
       dish-outs should be elliptically shaped with the major axis...
```

The score went *down* while the content became far better — the contents lines
were scoring artificially high on keyword overlap. Retrieval score alone was
never a quality signal here.

## Net effect on the index

| | before | after |
|---|---:|---:|
| chunks | 5,364 | 4,972 |
| low-information chunks | included | 343 dropped |
| two-column pages handled correctly | 0 | 992 |

Sample score changes: `corrosion on landing gear strut` 0.599 → 0.678;
`hairline crack in wing spar` 0.580 → 0.590. The meaningful change is the
passage text, not the numbers.

## One thing deliberately not done

During this work the Day 4 gate intermittently hit
`500 — prediction aborted, token repeat limit reached`. Adding Ollama's
`repeat_penalty` suppressed it, but in testing that run produced the citation
`[AC_43.13-1B.pdf p.6-50]` — **a page that was never retrieved**. Trading a
loud failure for a silently fabricated citation is the wrong direction for a
system whose central claim is grounding, so it was rejected. The 500s were
resource contention: Ollama competing with a YOLO training run for CPU.

## Operational note

`ingest_corpus.py --reset` cannot delete the index while the backend holds it
open — Windows refuses, and the raw error names `data_level0.bin`, which
explains nothing. The script now catches that and says to stop `app.py` first.
