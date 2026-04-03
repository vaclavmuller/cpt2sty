# CPT → Yamaha STY Converter

A Python tool for converting **Casio CPT styles** into **Yamaha SFF1 STY styles** with correct harmonic behavior.

---

## Why this exists

Casio CPT and Yamaha STY are structurally and behaviorally different style formats.

A direct mechanical conversion is not sufficient, because Yamaha accompaniment playback depends on correctly configured:

* **Source Root**
* **Source Chord**
* **NTT (Note Transposition Table)**

Without that mapping, the resulting Yamaha style may produce incorrect harmony, such as:

* unwanted major 7th chords
* incorrect chord transposition
* accompaniment parts behaving like melody tracks

This project was created to solve that problem through reverse engineering of both the CPT format and Yamaha CASM behavior.

---

## Features

* Converts `.CPT` → `.STY` (Yamaha SFF1)
* Generates CASM automatically
* Correct handling of:

  * Source Root
  * Source Chord
  * NTT (Chord vs Melody)
* Works with:

  * Casio factory styles
  * third-party styles
* Fully data-driven

---

## Key Insight

> CPT encodes how patterns were recorded, while Yamaha playback depends on how accompaniment tracks are interpreted during chord transposition.

Correct Yamaha playback requires reconstructing that harmonic behavior from CPT data.

---

## Usage

```bash
python cpt2sty "input.CPT"
```

Output:

```text
input.sty
```

---

## Project Structure

```text
/converter
  cpt2sty.py

/docs
  CPT_format.md
  CASM_mapping.md
  CASM_byte_level.md
```

---

## CPT Format

The CPT format is not publicly documented.

This project includes a reverse-engineered specification:

* `docs/CPT_format.md`

---

## Disclaimer

* The CPT format documentation is unofficial
* Some behaviors are based on reverse engineering and empirical testing
* Not all edge cases may be covered yet

---

## Tested With

* Casio factory styles
* third-party CPT styles
* Yamaha Style Creator validation

---

## Contributing

Contributions are welcome, especially in:

* decoding FF80 / FF81 / FF82 meta events
* improving CCT interpretation
* refining CASM generation
* extending compatibility and testing

---

## License

MIT License (recommended)
