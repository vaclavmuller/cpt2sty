# CPT to CASM mapping

CPT recording context and Yamaha playback rules must be represented separately.
See [the byte layout](CASM_byte_level.md) for field locations and NTT numbering.

## Current policy

- Copy `FF81.original_key` into Ctab source root for non-drum parts.
- Write the selected source family to Ctab offset 19: Major=00, Maj7=02,
  minor=08, dominant 7=13 (hex).
- Retain the existing CCT-based source-family heuristic: chord piano/guitar
  usually use dominant 7, with minor families for the supported minor CCTs.
  Bass and Phrase retain their separate family selection.
- Main/Fill chord piano, guitar, and chord-oriented Phrase use Chord NTT.
- No Change CCT uses Root Fixed and Bypass to preserve recorded notes.
- Other NTR, NTT, limits and retrigger settings start from section templates.
- Derive Cntt from the selected Ctab NTT using the extended numbering.
  Retain the Bass flag for Main A/Main B bass parts.

The JSON report includes source root, source chord code, both NTT codes,
and the Bass flag so recording context can be inspected independently.

## Limits of the evidence

The 139 same-name original/repaired pairs have identical CASM. They establish
the MIDI serialization repairs, not correct harmonic playback. Three additional
manually edited variants also change CASM, including section-specific NTT,
source chord and source root choices. The converter does not hard-code their
filenames or reproduce every manual musical decision.

In particular, GERONIMO's manual variant changes selected source roots from
F to C. There is insufficient evidence for changing the general FF81 root
mapping based on that one example. Audition on a Yamaha instrument is still
needed to validate harmony, especially intros, endings and unusual CCTs.
