# Changelog

## Unreleased

Fix invalid MIDI serialization: add the XG SysEx length and normalize the high
bit in Casio Program Change values, with warnings in conversion reports.
Reject other invalid channel data and expand running status before track merging.

Separate CASM source-chord encoding from NTT selection, translate between legacy
and extended NTT numbering, retain Bass flags, and order channel tables before
NTT overrides. Expose decoded CASM parameters in reports. Remove the extra
trailing bar. Correct the previous CASM documentation.

Add independent mido regression tests and GitHub Actions. Validate conversion of
139 supplied CPT styles; hardware playback remains to be checked.
