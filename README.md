# CPT to Yamaha STY Converter

Convert Casio CTK-731 CPT accompaniment patterns to Yamaha SFF1 STY files.
Requires Python 3.10 or newer; conversion uses only the Python standard library.

## Usage

```bash
python cpt2sty.py "input.CPT"
python cpt2sty.py "input.CPT" -o "output.sty" --report "output.json"
```

The converter writes an STY and a JSON diagnostic report. Source files are
unchanged. Invalid channel data prevents conversion, except for the observed
Casio Program Change high bit: the program number is normalized to its lower
seven bits and reported as a `PROGRAM_HIGH_BIT` warning.

## Fixes in this update

- Include the missing SMF length in XG System On SysEx messages.
- Normalize high-bit Program Change values found in four supplied CPT files.
- Expand running status before merging tracks onto different MIDI channels.
- Store source chord types in Ctab, and NTT in Ctab/Cntt with the correct,
  separate numbering. Keep Cntt consistent with Ctab and preserve Bass flags.
- Write all Ctab records before Cntt records within each section.
- End the MIDI track at the end of the last section without an extra empty bar.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

`mido` is a test dependency, not a converter runtime dependency. GitHub Actions
runs the synthetic regressions, including a complete CPT-to-STY CLI conversion.
If local `styles/` and `fixed styles/` folders are present, the tests also
convert all available CPT files, load the results through mido, compare their
MIDI events with the repairs, and check CASM consistency.

The supplied corpus contains 139 original styles. All generated outputs load;
16 Program Change values are normalized across ENDLESS, JINGLE, VAHDE and
VOYAGE. MIDI events match the same-name repairs, with the final empty bar
removed. This validates file structure and event preservation. Hardware playback
and every manual harmonic edit in the three extra variants are not verified.

## Format notes

- [CPT structure](docs/CPT_format.md)
- [CPT to CASM policy and limitations](docs/CASM_mapping.md)
- [CASM byte layout](docs/CASM_byte_level.md)

CPT decoding and source-family selection remain partly based on reverse
engineering. See the mapping notes before adjusting harmonic rules.
