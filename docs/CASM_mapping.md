# CASM Mapping (Yamaha SFF1)

## 1. Overview

Yamaha styles (SFF1) use the **CASM section** to define how accompaniment tracks react to chord changes.

This mapping is critical when converting from CPT, because CPT does not explicitly encode harmonic behavior in the same way.

---

## 2. Core Parameters

Each accompaniment track in Yamaha has the following key parameters:

* **Source Root**
* **Source Chord**
* **NTT (Note Transposition Table)**
* **NTB (Note Transposition Behavior)**
* **Note Limits**
* **RTR (Retrigger Rule)**

---

## 3. Source Root

### Definition

The reference key in which the pattern was recorded.

### Mapping from CPT

```text
Source Root = FF81.original_key
```

| Value | Key |
| ----- | --- |
| 0     | C   |
| 1     | C#  |
| 2     | D   |
| ...   | ... |
| 11    | B   |

---

## 4. Source Chord

### Definition

Defines the harmonic context of the recorded pattern.

### Key Insight

> Source Chord must reflect how the pattern was recorded — not how it should sound.

---

### Practical Rules

#### Chord Accompaniment (ChordPiano, ChordGuitar)

```text
Source Chord = 7
```

Reason:

* avoids unwanted major 7th interpretation
* matches typical Casio chord recordings

---

#### Phrase Tracks (Chord-like)

If phrase behaves harmonically:

```text
Source Chord = 7
```

---

#### Bass

```text
Source Chord = C
```

---

## 5. NTT (Note Transposition Table)

### Definition

Controls how notes are transposed when chords change.

---

### Types

| NTT    | Behavior                    |
| ------ | --------------------------- |
| Melody | Preserves melodic intervals |
| Chord  | Adapts to chord tones       |

---

### Mapping Rules

#### Chord Accompaniment

```text
NTT = Chord
```

---

#### Melody / Non-harmonic Phrase

```text
NTT = Melody
```

---

### Critical Issue

Incorrect NTT leads to:

* chord tracks behaving like melody
* broken harmony
* incorrect voicing

---

## 6. NTT + Source Chord Interaction

These two parameters must be consistent.

### Example

| Source Chord | NTT    | Result                  |
| ------------ | ------ | ----------------------- |
| C            | Melody | melodic behavior        |
| 7            | Chord  | correct chord following |
| Maj7         | Chord  | unwanted major 7th      |

---

## 7. Section Behavior

### Main / Fill Sections

* Full chord behavior enabled
* Use:

  * `Source Chord = 7`
  * `NTT = Chord`

---

### Intro / Ending

* More variable
* May contain:

  * fixed phrases
  * non-looping structures

---

## 8. Common Pitfalls

### 1. Using Maj7 instead of 7

Leads to:

* incorrect harmony
* extra major 7th note

---

### 2. Using Melody NTT for chord tracks

Leads to:

* broken accompaniment
* wrong transposition

---

### 3. Ignoring Source Root

Leads to:

* entire style transposed incorrectly

---

## 9. Conversion Strategy

### Step 1

Extract:

* original_key
* track role
* CCT (Chord Conversion Type)

---

### Step 2

Determine track type:

* Drum
* Bass
* Chord
* Phrase

---

### Step 3

Assign CASM:

#### Chord tracks

```text
Source Root = original_key
Source Chord = 7
NTT = Chord
```

---

#### Phrase tracks

```text
if harmonic:
    Source Chord = 7
    NTT = Chord
else:
    Source Chord = C
    NTT = Melody
```

---

#### Bass

```text
Source Root = original_key
Source Chord = C
NTT = Bass/Chord
```

---

## 10. Reverse Engineering Status

| Feature      | Status           |
| ------------ | ---------------- |
| Source Root  | Fully understood |
| Source Chord | High confidence  |
| NTT behavior | High confidence  |
| NTB / RTR    | Partial          |

---

## 11. Key Insight

> Yamaha style playback is not just MIDI — it is rule-based reinterpretation of MIDI patterns.

CASM defines those rules.

---

## 12. Conclusion

Correct CASM generation is essential for:

* realistic Yamaha playback
* correct chord behavior
* usable converted styles

This is the main challenge in CPT → STY conversion.
