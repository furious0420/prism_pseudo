# Day 4 — grounded diagnosis examples (2026-09-30 20:36)

Backend `ollama` / model `phi3:mini`

## Pitting corrosion on the landing gear strut, roughly 2mm deep.

- grounded: **True** (top score 0.617)
- citations: [AC_43.13-1B.pdf p.285], [AC_430.13-1B.pdf p.286], [AC_43.13-1B.pdf p.286]
- refused: False
- timing: 20061 ms retrieval + 39437 ms generation = 59498 ms

**Retrieved context**

- `AC_43.13-1B.pdf p.285` (0.617): d. Most parts of landing gear wheels are made from magnesium or aluminum alloys which corrode rapidly unless carefully protected. When the aircraft operates near salt water and off coral beaches, the ...
- `AC_43.13-1B.pdf p.286` (0.592): 6-68. WHEEL WELLS AND LANDING GEAR. Inspect wheel well area and landing gear components for damage to exterior finish coating and corrosion. Particular attention should be given to exposed surfaces of...
- `AC_43.13-1B.pdf p.428` (0.576): motion between normally close-fitting landing gear components may indicate wear, cracks, or improper adjustment. If a crack exists, it will generally be indicated by dirt or metallic particles which t...

**Diagnosis**

> [AC_43.13-1B.pdf p.285]
> d. Most parts of landing gear wheels are
> made from magnesium or aluminum alloys
> which corrode rapidly unless carefully protected.
> 
> [AC_430.13-1B.pdf p.286]
> e. Refinish portions of a wheel where
> paint has deteriorated, peeled, or chipped.
> 
> [AC_43.13-1B.pdf p.286]
> f. Except for friction and bearing surfaces, apply a protective coating to all parts of
> wheels and brake assemblies.
> 
> Diagnosis: Pitting corrosion on the landing gear strut, likely due to rapid corrosion of magnesium or aluminum alloys in corrosive environments. Immediate action: Refinish the affected area where paint has deteriorated, peeled, or chipped. Apply a protective coating to all parts of the wheels and brake assemblies.

---

## Hairline crack found on the wing spar cap during scheduled inspection.

- grounded: **True** (top score 0.580)
- citations: [AC_43.13-1B.pdf p.416], [AC_43.13-1B.pdf p.46], [AC_43.13-1B.pdf p.232]
- refused: False
- timing: 236 ms retrieval + 32381 ms generation = 32617 ms

**Retrieved context**

- `AC_43.13-1B.pdf p.416` (0.580): rivets. Inspect the tip for cracks by grasping it manufacturers publish SB’s and instructions with the hand and slightly twisting about the which prescribe the manner in which these inlongitudinal bla...
- `AC_43.13-1B.pdf p.46` (0.544): front spar rib attach points, both inboard and outboard of the spar reinforcement plate; and the rear spar lift strut and rib attach points. An inspection of both the front and rear spars for compress...
- `AC_43.13-1B.pdf p.232` (0.517): required. An inspector normally should have available suitable measuring devices, a flashlight, and a mirror. (1) Surface cracks. When searching for surface cracks with a flashlight, direct the light ...

**Diagnosis**

> [AC_43.13-1B.pdf p.416]
> A fine line appearing in the fabric or plastic of steel blades may be accomplished by either visual inspection or using a fluorescent penetrant.
> 
> [AC_43.13-1B.pdf p.46]
> The inspection of both the front and rear spars for compression cracks is recommended.
> 
> [AC_43.13-1B.pdf p.232]
> Surface cracks. When searching for surface cracks with a flashlight, direct the light beam at a 5 to 45 degree angle to the inspection surface, towards the face.
> 
> Likely Defect: Compression Crack in the Wing Spar Cap
> 
> Immediate Action: Inspect the wing spar cap for compression cracks using a borescope or cutting inspection holes in the skin for a closer look. If a crack is confirmed, remove the fabric from the spar for a more detailed examination.

---

## White powdery deposit on an aluminium panel near the wheel well.

- grounded: **True** (top score 0.517)
- citations: [AC_20-106.pdf p.14], [AC_43.13-1B.pdf p.297]
- refused: False
- timing: 83 ms retrieval + 11709 ms generation = 11792 ms

**Retrieved context**

- `AC_20-106.pdf p.14` (0.517): ing is in contact with an eroding chemical such as battery acid, insecticide, fertilizer or defoliants. Contact between two unprotected dissimilar metals sets the stage for galvanic action and corrosi...
- `AC_43.13-1B.pdf p.297` (0.503): distance available to make the inspection.) Corrosion still on the area will appear as a powdery crust slightly different in color than the uncorroded base metal. Darkening of area due to shadows and ...
- `AC_43.13-1B.pdf p.276` (0.468): Par 6-11 AC 43.13-1B CHG 1 ES OF CORROSION 6-13. PITTING CORROSION. Pitting corrosion is one of the most destructive and intense forms of corrosion. It can occur in any metal but is most common on met...

**Diagnosis**

> Pitting corrosion [AC_20-106.pdf p.14]
> 
> Immediate action: Remove the powdery deposit with a soft brush and seek an experienced mechanic's evaluation. Afterward, apply a chromate conversion coating such as MIL-C-81706 or MIL-C-5541 alodine 1200 [AC_43.13-1B.pdf p.297].

---

## Dent in the fuselage skin, about 40mm across and shallow.

- grounded: **True** (top score 0.464)
- citations: [AC_65-15A.pdf p.238], [AC_43.13-1B.pdf p.68]
- refused: False
- timing: 63 ms retrieval + 49837 ms generation = 49900 ms

**Retrieved context**

- `AC_65-15A.pdf p.238` (0.464): Fuselage inner and outer ply skins Position to check Reinforced laminated for separation fuselage member Bulkhead frame member Woodscrew '\Expausion gap (not to be coofused with joint separation) Corr...
- `AC_43.13-1B.pdf p.59` (0.458): (3) If the back of a damaged plywood skin is accessible (such as a fuselage skin), it should be repaired with a scarf patch, following the details shown in figure 1-15. Whenever possible, the edges of...
- `AC_43.13-1B.pdf p.68` (0.458): (3) If the back of a damaged plywood skin is accessible (such as a fuselage skin), it should be repaired with a scarf patch, following the details shown in figure 1-15. Whenever possible, the edges of...

**Diagnosis**

> [AC_65-15A.pdf p.238]
> Fuselage inner and outer ply skins
> Position to check
> Reinforced laminated for separation
> fuselage member
> Bulkhead frame
> member
> Woodscrew
> '\Expausion
> gap (not to be coofused
> with joint separation)
> Corrosion indicating failure of bulkhead
> glued joint to fuselage side
> 
> [AC_43.13-1B.pdf p.68]
> (3) If the back of a damaged plywood
> skin is accessible (such as a fuselage skin), it
> should be repaired with a scarf patch, following the details shown in figure 1-15. Whenever possible, the edges of the patch should be
> supported as shown in section C-C of figure 1-15. When the damage follows or extends to a framing member, the scarf may be
> supported as shown in section B-B of figure 1-15. Damages that do not exceed
> 25 times the skin thickness in diameter after
> being trimmed to a circular shape and are not
> less than 15 times the skin thickness to a
> framing member, may be repaired as shown in
> figure 1-15, section D-D.
> (a) The backing block is carefully
> shaped from solid wood and fitted to the inside
> surface of the skin, and is temporarily held in
> place with nails.
> 
> Diagnosis:
> Likely defect: Dent in the fuselage skin
> Recommended immediate action: Apply a scarf patch as per figure 1-15, section D-D, ensuring the backing block is shaped from solid wood and

---

## Which inspection method finds subsurface cracks in aluminium?

- grounded: **True** (top score 0.678)
- citations: [AC_43.13-1B.pdf p.235]
- refused: False
- timing: 595 ms retrieval + 56946 ms generation = 57541 ms

**Retrieved context**

- `AC_43.13-1B.pdf p.232` (0.678): required. An inspector normally should have available suitable measuring devices, a flashlight, and a mirror. (1) Surface cracks. When searching for surface cracks with a flashlight, direct the light ...
- `AC_43.13-1B.pdf p.235` (0.637): broad areas for randomly-oriented cracks. However, in some instances it is more economical to scan relatively large areas with eddy current rather than strip surface coatings, inspect by other methods...
- `AC_43.13-1B.pdf p.235` (0.610): Service-induced cracks in aircraft structures are generally caused by fatigue or stress corrosion. Both types of cracks initiate at the surface of a part. If this surface is accessible, a high-frequen...

**Diagnosis**

> [AC_43.13-1B.pdf p.235]
> Service-induced cracks in aircraft structures
> are generally caused by fatigue or stress corrosion. Both types of cracks initiate at the surface of a part. If this surface is accessible, a
> high-frequency eddy current inspection can be
> performed with a minimum of part preparation
> and a high degree of sensitivity. If the surface
> is less accessible, such as in a subsurface layer
> of structure, low-frequency eddy current inspection can usually be performed. Eddy current inspection can usually be performed without removing surface coatings such as primer,
> paint, and anodic films. Eddy current inspection has the greatest application for inspecting
> small localized areas where possible crack initiation is suspected rather than for scanning
> broad areas for randomly-oriented cracks.
> 
> Technician query: Which inspection method finds subsurface cracks in aluminium?
> 
> Diagnosis: Low-frequency eddy current inspection is used to inspect for subsurface cracks in aluminium.

---

## Surface grains lifting and flaking on a 7075-T6 component.

- grounded: **True** (top score 0.472)
- citations: [AC_65-15A.pdf p.240]
- refused: False
- timing: 201 ms retrieval + 12881 ms generation = 13082 ms

**Retrieved context**

- `AC_65-15A.pdf p.240` (0.472): the grain does not diverge from the longitudinal axis of the material more than specified in column 3 of figure 108. A check of all four faces of the board is necessary to determine the amount of...
- `AC_43.13-1B.pdf p.167` (0.466): b. Repairs to Aluminum Alloy Members. Make repairs to aluminum alloy members with the same material or with suitable material of higher strength. The 7075 alloy has greater tensile strength than other...
- `AC_43.13-1B.pdf p.278` (0.434): defined boundary which chemically differs from the metal within the grain. The grain boundary and the grain center can react with each other as anode and cathode when in contact with an electrolyte. (...

**Diagnosis**

> [AC_65-15A.pdf p.240]
> The likely defect is inter-granular corrosion, particularly exfoliation corrosion, as indicated by the lifting and flaking of surface grains.
> 
> Recommended immediate action: Inspect the component for any visible signs of grain boundary reactions or electrolyte presence, and remove the component from the corrosive environment if possible. Avoid cold straightening or forming of the 7075-T6 material to prevent further cracking.

---

## How do I replace the filter in the crew coffee machine?

- grounded: **True** (top score 0.440)
- citations: _none_
- refused: True
- timing: 87 ms retrieval + 16879 ms generation = 16965 ms

**Retrieved context**

- `AC_43.13-1B.pdf p.436` (0.440): The filter rating is given in terms of “micron,” and is an indication of the particle size that will be filtered out. The replacement interval of these filters is established by the manufacturer and i...
- `AC_65-15A.pdf p.325` (0.423): which is secured to the aircraft structure and con necting lines. Within the head there is a bypass valve which routes the hydraulic fluid directly from the inlet to the outlet port if the filter elem...
- `AC_65-15A.pdf p.325` (0.422): FrcuRE 8-3. Hydraulic filter, micronic type. HUMAN HAIR IS ABOUT 100 MICRONS IN . DIAMETER  0 0 40· MICRON !O-MICRON 5-MICRON PARTICLE PARTICLE PARTICLE 25,400 MICRONS • I INCH FrcURE 8-4. Enlargement...

**Diagnosis**

> The provided manual extracts do not cover this.

---

## Summary

- Queries: 7
- Grounded: 7/7
- Cited correctly: 6/7
- Refused: 1/7 (the coffee machine query SHOULD refuse — that one is a pass)
- Average end-to-end: **34485 ms** (feeds D11-02)

### Problems found

- **UNCITED or FABRICATED CITATION** — `Pitting corrosion on the landing gear strut, roughly 2mm deep.`

Fixes, in order of likelihood:
1. Tighten the prompt — make the citation rule and the refusal sentence more emphatic.
2. Raise `GROUNDING_THRESHOLD` in models/rag.py so weak retrieval stops reaching the model at all.
3. Re-chunk the corpus — passages too small to carry context force the model to fill gaps from memory.

## Prompt template (D4-02 step 4)

```
You are an aircraft maintenance diagnostic assistant.

Answer ONLY from the maintenance manual extracts below. Do not use any outside knowledge, even if you are confident it is correct.

Rules:
- Cite the source for every claim, in the form [document p.N], exactly as the extract is labelled.
- If the extracts do not cover the query, reply exactly: "The provided manual extracts do not cover this." Do not guess.
- Be concise and practical. A technician is reading this at the aircraft.
- State the likely defect, then the recommended immediate action.

Manual extracts:
{context}

Technician query: {query}

Diagnosis:
```
