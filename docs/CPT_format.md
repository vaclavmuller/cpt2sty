# CPT File Format Specification (Unofficial, Reverse Engineered)

## 1. Introduction

The CPT format is used by Casio keyboards to store accompaniment styles.

This specification is unofficial and based entirely on reverse engineering of multiple CPT files and parser behavior.

---

## 2. File Structure Overview

A CPT file begins with a fixed file signature, followed by a variable-length CASA header and then the track data.

```c
struct CPTFile {
    char magic[4];          // "CASA"
    uint32_be header_size;  // size of the following CASA header
    uint8 header[header_size];
    // followed by track data
};
```

### 2.1 Magic

The first 4 bytes are always:

```text
43 41 53 41
```

ASCII:

```text
"CASA"
```

### 2.2 Header Size

Immediately after the magic comes:

```c
uint32_be header_size
```

This is the size of the following CASA header in bytes.

---

## 3. CASA Header Format

The CASA header is a simple TLV sequence.

Each item has the following structure:

```c
struct HeaderItem {
    uint8 type;
    uint8 size;
    uint8 data[size];
};
```

The parser advances as follows:

```c
size = data[n + 1];
n = n + 2 + size;
```

So the header is parsed as a linear sequence of `type-length-value` records until `header_size` bytes are consumed.

---

## 4. Known CASA Header Item Types

### 4.1 Types `< 240` — Element to Track Mapping

Header items with `type < 240` are mapping records from an element ID to a track index.

Observed payload layout:

```c
type: 0x00 .. 0xEF
size: probably 2
data: uint16_be track_index
```

Equivalent parsing logic:

```python
out['element'].append((data[n], read2byte(data, n + 2)))
```

Meaning:

* `data[n]` = element ID
* `read2byte(data, n + 2)` = track index assigned to that element

This strongly suggests that these records define which logical style element points to which track structure in the track area.

---

### 4.2 Type `240` (`0xF0`) — Ignored / Unknown

This item type is currently not interpreted.

Observed parser behavior:

* read `size`
* skip the item
* no output field assigned

So structurally it is valid TLV data, but its semantic meaning remains unknown.

---

### 4.3 Type `241` (`0xF1`) — Style Name

This item stores the style name as ASCII text.

Layout:

```c
type = 241;
size = text_length;
data = ASCII style name;
```

Equivalent parsing logic:

```python
out['name'] = ''.join(map(chr, data[n+2:n+2+size]))
```

---

### 4.4 Type `242` (`0xF2`) — Track Count

This item stores the number of tracks.

Layout:

```c
type = 242;
size = 2;
data = uint16_be track_count;
```

---

### 4.5 Type `243` (`0xF3`) — Resolution / PPQN

This item stores the timing resolution.

Layout:

```c
type = 243;
size = 2;
data = uint16_be reso;
```

Interpretation:

* MIDI timing resolution
* analogous to PPQN (pulses per quarter note)

---

### 4.6 Type `244` (`0xF4`) — Tempo

This item stores tempo as a 16-bit big-endian value.

Layout:

```c
type = 244;
size = 2;
data = uint16_be tempo;
```

Current interpretation:

* structurally confirmed as a plain 16-bit big-endian integer
* no additional transform is visible in the parser
* exact musical interpretation depends on the target software / keyboard behavior

---

### 4.7 Type `245` (`0xF5`) — Time Signature

This item stores the time signature.

Layout:

```c
type = 245;
size = 2;
data[0] = numerator;
data[1] = denominator;
```

Interpretation:

* `data[0]` = time signature numerator
* `data[1]` = denominator, expected to be one of:

  * 2
  * 4
  * 8
  * 16

Example:

```text
04 04 = 4/4
03 04 = 3/4
06 08 = 6/8
```

---

## 5. Summary of Known CASA Header Types

| Type  | Hex   | Meaning                 | Payload                              |
| ----- | ----- | ----------------------- | ------------------------------------ |
| 0–239 | 00–EF | Element → track mapping | `uint16_be track_index`              |
| 240   | F0    | Unknown / ignored       | variable                             |
| 241   | F1    | Style name              | ASCII text                           |
| 242   | F2    | Track count             | `uint16_be`                          |
| 243   | F3    | Resolution / PPQN       | `uint16_be`                          |
| 244   | F4    | Tempo                   | `uint16_be`                          |
| 245   | F5    | Time signature          | `uint8 numerator, uint8 denominator` |

---

## 6. Parser Model for the Header

A minimal parser for the CASA header can be expressed as:

```python
n = 0
while n < header_size:
    item_type = header[n]
    item_size = header[n + 1]
    item_data = header[n + 2:n + 2 + item_size]

    # handle item_type here

    n += 2 + item_size
```

This confirms that the CASA header is not a fixed struct, but a compact extensible TLV container.

---

## 7. Remaining File Content

After the CASA header, the file continues with the track data.

At a high level:

* the header defines global metadata
* the element mapping records link logical style elements to track indices
* the remainder of the file contains the musical content for those tracks

The track area is more complex and contains the per-track pattern/event data used by the style engine.

---

## 8. Current Confidence Level

The following parts are considered high-confidence:

* file magic `"CASA"`
* 32-bit big-endian `header_size`
* TLV structure of the CASA header
* meaning of item types `F1` to `F5`
* element-to-track mapping records for types `< 240`

The following remain incomplete:

* full semantics of type `F0`
* full binary structure of the track area after the header
* all event-level details and auxiliary blocks

## 9. Track Data Structure (MIDI-Based)

After the CASA header, the CPT file contains track data.

Each track is stored as a **standard MIDI event stream**, extended with Casio-specific meta events.

---

## 9.1 Core Principle

> CPT track data is fundamentally a MIDI track.

This means:

* Delta-time encoded events
* Standard MIDI event types:

  * Note On / Note Off
  * Control Change
  * Program Change
* Standard MIDI meta events:

  * `FF 2F` (End of Track)
  * etc.

---

## 9.2 Casio-Specific Meta Events

Casio extends MIDI using meta events of the form:

```text
FF xx ...
```

Where:

* `FF` = MIDI Meta Event
* `xx` = Casio-defined subtype

---

## 9.3 Known Casio Meta Events

### 9.3.1 `FF 81` — Style / Track Metadata

This event appears inside tracks and carries additional structural or behavioral data.

Observed uses:

* may define per-track parameters
* may relate to section or element behavior
* exact structure varies depending on context

---

### 9.3.2 `FF 82` — Additional Metadata

Observed but not fully decoded.

Likely used for:

* track-specific configuration
* articulation or playback hints

---

### 9.3.3 `FF 80` — Control / Structural Marker

Observed in multiple tracks.

Possible roles:

* section boundary markers
* loop control
* variation triggers

Exact semantics are still under investigation.

---

## 9.4 Event Structure

All events follow standard MIDI encoding:

```text
[delta-time] [event]
```

Where event can be:

* MIDI channel event
* SysEx (rare)
* Meta event (`FF xx`)

---

## 9.5 Track Termination

Tracks end with standard MIDI:

```text
FF 2F 00
```

---

## 9.6 Important Observations

### 1. Compatibility

Because CPT uses standard MIDI encoding:

* existing MIDI parsers can read most data
* only custom handling is needed for `FF 80–FF 82`

---

### 2. Separation of Concerns

* CASA header → structure, mapping, metadata
* MIDI tracks → actual musical content

---

### 3. Conversion Implication

For CPT → Yamaha conversion:

* MIDI events are mostly copied directly
* transformation is applied only via:

  * CASM (Source Chord, NTT, etc.)
  * interpretation of CCT and metadata

---

## 9.7 Key Insight

> CPT does not encode harmony explicitly — it encodes performance in a reference key.

Harmony is reconstructed later via:

* CCT
* Source Chord
* NTT (in Yamaha)

---

## 9.8 Reverse Engineering Status

| Feature              | Status               |
| -------------------- | -------------------- |
| MIDI event stream    | Fully understood     |
| FF 80–82 meta events | Partially understood |
| Timing model         | High confidence      |
| Track boundaries     | High confidence      |

---

## 9.9 Future Work

* Full decoding of FF 80 / FF 81 / FF 82 payloads
* Mapping of section boundaries from meta events
* Identification of articulation parameters

