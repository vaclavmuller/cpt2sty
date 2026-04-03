# CASM Byte-Level Specification (Yamaha SFF1, Reverse Engineered)

## 1. Scope

This document describes the reverse-engineered byte-level behavior of selected CASM structures used by the CPT → Yamaha STY converter.

Focus areas:

* `Cntt`
* `Ctab`

These observations are based on:

* generated Yamaha SFF1 styles
* comparison with manually fixed styles
* iterative testing in Yamaha style tools and playback
* listening tests

This is **not** an official Yamaha specification.

---

## 2. CASM Context

In Yamaha SFF1, the CASM section defines how accompaniment tracks react to chord input and how fixed MIDI patterns are reinterpreted during playback.

For the purposes of this converter, the most important substructures were:

* `Cntt`
* `Ctab`

In practical terms:

* `Cntt` carries the **Source Chord**
* `Ctab` carries the **Source Root**, **NTT**, and related transposition behavior

---

## 3. `Cntt`

### 3.1 Purpose

`Cntt` defines the harmonic reference context of the source pattern, especially the **Source Chord**.

This is one of the most critical parameters for correct Yamaha playback.

Incorrect `Cntt` settings can cause:

* unwanted major 7th interpretation
* wrong chord adaptation
* accompaniment parts sounding harmonically incorrect

---

### 3.2 Observed Layout

Empirically, the converter treats `Cntt` as a 2-byte value:

```text
Cntt = 0C xx
```

Where:

* the first byte is observed as constant `0x0C`
* the second byte selects the Yamaha source chord type

Practical structure used by the converter:

```c
struct Cntt {
    uint8 fixed;         // usually 0x0C
    uint8 source_chord;  // Yamaha chord type code
};
```

---

### 3.3 Observed Source Chord Codes

| `Cntt` bytes | Interpreted as |
| ------------ | -------------- |
| `0C 00`      | Major / C      |
| `0C 01`      | 7              |
| `0C 02`      | Maj7           |
| `0C 03`      | minor / Cm     |

These are the values that mattered most during converter development.

---

### 3.4 Critical Finding

A critical discovery from testing:

* `0C 02` is **Maj7**, not plain `7`
* plain `7` must be encoded as:

```text
0C 01
```

This was confirmed by comparison with manually corrected Yamaha styles.

Incorrect use of `0C 02` leads to:

* unwanted major 7th tones
* incorrect chord interpretation

---

### 3.5 Converter Defaults

#### Chord accompaniment

For chord-oriented accompaniment tracks:

```text
Cntt = 0C 01
```

Meaning:

* **Source Chord = 7**

This proved to be the safest default for many chord tracks, especially:

* ChordPiano
* ChordGuitar
* harmonic Phrase tracks

#### Bass

For bass tracks, the converter typically uses:

```text
Cntt = 0C 00
```

Meaning:

* **Source Chord = C**

#### Minor material

For clearly minor source material, the converter may use:

```text
Cntt = 0C 03
```

Meaning:

* **Source Chord = Cm**

---

## 4. `Ctab`

### 4.1 Purpose

`Ctab` carries the transposition behavior for a source pattern.

This includes, in practical converter terms:

* **Source Root**
* **NTT**
* related chord-transposition parameters
* possibly NTB, limits, and flags

`Ctab` is the place where harmonic behavior is actually made usable by Yamaha.

---

### 4.2 Structural Status

Unlike `Cntt`, the full binary layout of `Ctab` is not fully decoded.

However, the converter relies on stable byte positions that were validated by testing. The two most important findings are:

1. `Ctab` contains the **Source Root**
2. `Ctab` contains the **NTT mode**

---

### 4.3 Source Root in `Ctab`

The converter writes the Yamaha **Source Root** into `Ctab` using the CPT `original_key`.

Practical rule:

```text
Source Root = FF81.original_key
```

Key mapping:

| Value | Root |
| ----- | ---- |
| 0     | C    |
| 1     | C#   |
| 2     | D    |
| 3     | D#   |
| 4     | E    |
| 5     | F    |
| 6     | F#   |
| 7     | G    |
| 8     | G#   |
| 9     | A    |
| 10    | A#   |
| 11    | B    |

This became important because factory styles were usually in C, while third-party styles could be recorded in another key such as F.

Ignoring this field causes the entire style to harmonize incorrectly.

---

### 4.4 NTT in `Ctab`

The converter distinguishes mainly between:

* **Melody**
* **Chord**

Empirical testing showed that one critical byte inside `Ctab` determines whether Yamaha treats the pattern as chord-following or melody-like.

Observed practical values:

| Byte value | Interpreted as |
| ---------- | -------------- |
| `00`       | Melody-like    |
| `02`       | Chord          |

This is the key rule the converter ended up using.

#### Melody (`00`)

* preserves intervals
* ignores chord tones
* suitable for lead phrases

#### Chord (`02`)

* adapts notes to chord tones
* required for accompaniment tracks

---

### 4.5 Critical Practical Finding

A recurring failure case during development was:

* the accompaniment sounded as if it were a melody track
* chord notes did not adapt correctly
* voicing was broken

In those cases, the fix was to change the relevant `Ctab` NTT byte from:

```text
00 -> Melody
```

to

```text
02 -> Chord
```

This matched the behavior of manually corrected styles.

---

### 4.6 Example Observation

During testing, a generated style was verified to contain:

```text
Cntt = 0C 02
```

and Yamaha displayed the source chord as **Maj7**.

After correction, the style used:

```text
Cntt = 0C 01
```

and Yamaha displayed the source chord as **7**.

Similarly, chord-oriented tracks that still behaved incorrectly were found to have a `Ctab` NTT byte corresponding to **Melody**, and changing it to the **Chord** value fixed the playback.

---

### 4.7 Partial Layout Hypothesis

Based on consistent behavior, `Ctab` likely contains fields equivalent to:

```c
struct Ctab {
    uint8 ...;          // flags / header
    uint8 source_root;  // confirmed field
    uint8 ntt;          // confirmed field (00 / 02)
    uint8 ...;          // additional parameters
};
```

Exact byte offsets remain under investigation.

---

## 5. Combined Behavior (`Cntt` + `Ctab`)

These two structures must be consistent.

### 5.1 Chord tracks

For:

* ChordPiano
* ChordGuitar
* harmonic Phrase tracks

use:

```text
Cntt = 0C 01
Ctab.NTT = 02
Ctab.SourceRoot = original_key
```

Meaning:

* Source Chord = 7
* NTT = Chord
* Source Root = actual style key

### 5.2 Melody / non-harmonic phrase

For melodic material:

```text
Cntt = 0C 00
Ctab.NTT = 00
Ctab.SourceRoot = original_key
```

Meaning:

* Source Chord = C
* NTT = Melody

### 5.3 Bass

For bass tracks:

```text
Cntt = 0C 00
Ctab.SourceRoot = original_key
```

The NTT/NTB handling for bass is more nuanced and remains less fully documented than the chord-track case.

### 5.4 Incorrect setup example

```text
Cntt = 0C 02
Ctab.ntt = 02
```

Result:

* Yamaha interprets the pattern as Maj7
* unwanted major 7th appears

---

## 6. Interaction with CPT Data

Mapping pipeline:

```text
CPT -> (CCT + original_key) -> CASM (Cntt + Ctab)
```

Where:

* CPT provides recording context
* CASM reconstructs harmonic behavior

---

## 7. Reverse Engineering Method

Findings were obtained via:

* comparing generated vs manually corrected styles
* observing Yamaha Style Creator behavior
* iterative modification of `Cntt` and `Ctab`
* listening tests

---

## 8. Confidence Levels

| Finding                           | Confidence |
| --------------------------------- | ---------- |
| `Cntt 0C 01 = 7`                  | High       |
| `Cntt 0C 02 = Maj7`               | High       |
| `Cntt 0C 00 = Major/C`            | High       |
| `Cntt 0C 03 = minor/Cm`           | Medium     |
| `Ctab` contains Source Root       | High       |
| `Ctab` contains NTT control byte  | High       |
| `Ctab NTT 00 = Melody`            | High       |
| `Ctab NTT 02 = Chord`             | High       |
| full official `Ctab` field layout | Partial    |

---

## 9. Important Caveat

These notes describe the byte-level behavior that was sufficient to build a working converter and fix real musical problems.

They should be understood as:

* **reverse-engineered implementation notes**
* not a complete official Yamaha CASM specification

A fuller future document could extend this with:

* exact byte offsets within `Ctab`
* NTB values
* note limits
* RTR behavior
* per-section / per-track differences

---

## 10. Summary

The most important byte-level findings were:

1. `Cntt` controls **Source Chord**
2. `0C 01` means **7**
3. `0C 02` means **Maj7**
4. `Ctab` carries **Source Root**
5. `Ctab` also carries the critical **NTT selector**
6. Setting chord tracks to:

   * `Source Chord = 7`
   * `NTT = Chord`
   * `Source Root = original_key`

   solved the major harmonic problems in conversion.

These findings form the practical core of the current CPT → Yamaha STY converter.
