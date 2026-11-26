# CASM byte layout (Yamaha SFF1)

Offsets below are zero-based, relative to the chunk payload, excluding its
four-byte tag and four-byte length. These are distinct fields; source chord
codes must never be written into an NTT field.

## Ctab

| Offset | Meaning | Selected values |
| --- | --- | --- |
| 0 | Source MIDI channel | 0..15 |
| 9 | Destination MIDI channel | 0..15 |
| 18 | Source root | 0=C, 5=F, 11=B |
| 19 | Source chord type | 00=Major, 02=Maj7, 08=minor, 13=dominant 7 (hex) |
| 20 | NTR | 0=Root Transposition, 1=Root Fixed |
| 21 | Legacy NTT | 0=Bypass, 1=Melody, 2=Chord, 3=Bass, 4=Melodic Minor, 5=Harmonic Minor |
| 22 | High key | 0..11 |
| 23..24 | Low/high note limits | MIDI note numbers |
| 25 | Retrigger rule | Kept from section templates |

## Cntt

The two-byte payload contains a source channel followed by an **extended NTT**.
Bit 7 of its second byte is the Bass flag. The lower seven bits select
0=Bypass, 1=Melody, 2=Chord, 3=Melodic Minor, 4=Melodic Minor 5th Variation,
5=Harmonic Minor, and further extended tables.

For example, `0C 01` means channel 13, Melody. It does not mean source chord
C7. `0C 02` means channel 13, Chord; it does not select Maj7.

Legacy Ctab NTT and extended Cntt NTT are not identical enumerations.
The converter maps legacy Bass to Melody with Bass enabled (`81` hex),
and legacy Melodic Minor (`04`) to extended Melodic Minor (`03`).
All Ctab records precede all Cntt records inside a CSEG.

## Reference and correction

See [Wierzba / Bedesem, Style Files - Introduction and Details v2.1](https://wierzba.hier-im-netz.de/StyleFileDescription_v21.pdf),
pages 19-25. This is a reverse-engineered description, not an official Yamaha
binary specification. Earlier project notes incorrectly described Cntt as
Source Chord and Ctab offset 19 as NTT; those claims are withdrawn.
