import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import mido

import cpt2sty as converter


def chunks(data):
    position = 0
    while position < len(data):
        if position + 8 > len(data):
            raise AssertionError("Incomplete chunk header")
        tag = data[position:position + 4]
        size = int.from_bytes(data[position + 4:position + 8], "big")
        end = position + 8 + size
        if end > len(data):
            raise AssertionError("Chunk exceeds its parent")
        yield tag, data[position + 8:end]
        position = end


def track(part="ChordPiano", cct=6, root=5):
    return converter.Track(0, 0, 0, element_id=0x25,
                           element_info={"part_name": part, "section_name": "Variation1"},
                           ff81={"cct": cct, "original_key": root})


class MidiRegressionTests(unittest.TestCase):
    def test_cli_converts_a_cpt_and_reports_program_normalization(self):
        # A complete synthetic CPT keeps the end-to-end check available in CI.
        casa = bytes.fromhex("25 02 0000 F2 02 0001 F3 02 00C0 F4 02 0078 F5 02 0404")
        body = bytes.fromhex("00 FF81 07 05000600000000 00 FF82 01 01 00 CB A5 00 9B 3C40")
        body += converter.write_vlq(192) + bytes.fromhex("9B 3C00")
        body += converter.write_vlq(576) + bytes.fromhex("FF2F00")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.CPT"
            source.write_bytes(converter.chunk(b"CASA", casa) + converter.chunk(b"MTrk", body))
            result = subprocess.run([sys.executable, converter.__file__, str(source)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            messages = mido.MidiFile(source.with_suffix(".sty")).tracks[0]
            self.assertEqual([m.program for m in messages if m.type == "program_change"], [0x25])
            self.assertEqual(sum(m.time for m in messages), 1536)
            report = json.loads(source.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertTrue(report["conversion_performed"])
            self.assertEqual([issue["code"] for issue in report["issues"]], ["PROGRAM_HIGH_BIT"])
            detail = report["casm_report"]["csegs"][0]["tracks"][0]
            self.assertEqual((detail["source_root"], detail["source_chord_code"], detail["cntt_ntt"]),
                             (5, 0x13, 2))

    def test_xg_message_does_not_consume_following_events(self):
        body = b"\x00" + converter.sysex_xg_on() + bytes.fromhex("00 B9 07 64 00 FF 2F 00")
        header = bytes.fromhex("4D546864 00000006 0000 0001 00C0")
        midi = mido.MidiFile(file=io.BytesIO(header + converter.chunk(b"MTrk", body)))
        self.assertEqual([message.type for message in midi.tracks[0]],
                         ["sysex", "control_change", "end_of_track"])
        self.assertEqual(tuple(midi.tracks[0][0].data), (0x43, 0x10, 0x4C, 0, 0, 0x7E, 0))

    def test_casio_program_high_bit_is_removed(self):
        for original, expected in [(0x95, 0x15), (0x8C, 0x0C), (0xA5, 0x25),
                                   (0x8E, 0x0E), (0xA1, 0x21), (127, 127)]:
            with self.subTest(original=original):
                self.assertEqual(converter.remap_channel_event(bytes([0xCB, original]), 13),
                                 bytes([0xCC, expected]))

    def test_other_invalid_midi_data_is_rejected(self):
        with self.assertRaises(ValueError):
            converter.remap_channel_event(bytes.fromhex("90 80 40"), 12)

    def test_running_status_survives_track_merging(self):
        events = converter.parse_track_events(bytes.fromhex("00 90 3C 40 00 40 40"))
        # An event on another channel can appear between these source events.
        merged = [converter.remap_channel_event(events[0].raw_bytes, 12),
                  bytes.fromhex("99 24 40"),
                  converter.remap_channel_event(events[1].raw_bytes, 12)]
        self.assertEqual(merged[-1], bytes.fromhex("9B 40 40"))


class CasmRegressionTests(unittest.TestCase):
    def test_source_chord_does_not_select_the_ntt(self):
        for cct, expected_chord in [(6, 0x13), (7, 0x08)]:
            with self.subTest(cct=cct):
                source = track(cct=cct)
                ctab, _, _ = converter.make_ctab_default(source, "Main A")
                cntt = converter.make_cntt_default(source, "Main A", ctab)
                self.assertEqual(ctab[18:22], bytes([5, expected_chord, 0, 2]))
                self.assertEqual(cntt, bytes([11, 2]))

    def test_legacy_and_extended_minor_tables_use_different_codes(self):
        source = track()
        ctab, _, _ = converter.make_ctab_default(source, "Intro A")
        self.assertEqual(ctab[21], 4)  # Ctab: Melodic Minor
        self.assertEqual(converter.make_cntt_default(source, "Intro A", ctab)[1], 3)

    def test_bass_flag_survives_source_chord_changes(self):
        for cct, chord in [(0, 0), (1, 0x13), (9, 8)]:
            source = track("Bass", cct)
            ctab, _, _ = converter.make_ctab_default(source, "Main A")
            self.assertEqual(ctab[19], chord)
            self.assertEqual(converter.make_cntt_default(source, "Main A", ctab), bytes([10, 0x81]))

    def test_no_change_preserves_recorded_notes(self):
        source = track("Phrase", 14)
        ctab, _, _ = converter.make_ctab_default(source, "Main A")
        self.assertEqual(ctab[20:22], bytes([1, 0]))
        self.assertEqual(converter.make_cntt_default(source, "Main A", ctab)[1], 0)

    def test_channel_tables_precede_ntt_overrides(self):
        segment, _ = converter.build_cseg_for_section(None, "Main A", [track(), track("Bass", 0)])
        _, body = next(chunks(segment))
        self.assertEqual([tag for tag, _ in chunks(body)],
                         [b"Sdec", b"Ctab", b"Ctab", b"Cntt", b"Cntt"])


class CorpusRegressionTests(unittest.TestCase):
    def test_all_available_cpt_files(self):
        root = Path(__file__).resolve().parents[1]
        inputs = sorted((root / "styles").rglob("*.CPT"))
        if not inputs:
            self.skipTest("Local CPT corpus is not included in the GitHub repository")
        with tempfile.TemporaryDirectory() as directory:
            for index, path in enumerate(inputs):
                with self.subTest(path=path.name):
                    cpt = converter.parse_cpt(path)
                    self.assertFalse([issue for issue in converter.validate_cpt(cpt) if issue.level == "error"])
                    output = Path(directory) / f"{index}.sty"
                    converter.write_style_file(cpt, output)
                    messages = mido.MidiFile(output).tracks[0]
                    reference = root / "fixed styles" / path.parts[-3] / path.with_suffix(".sty").name
                    if reference.exists():
                        expected = mido.MidiFile(reference).tracks[0]
                        self.assertEqual(messages[:-1], expected[:-1])
                        self.assertEqual(expected[-1].time - messages[-1].time,
                                         converter.compute_ticks_per_bar(cpt))
                    self.assertEqual(messages[-1].type, "end_of_track")
                    top = dict(chunks(output.read_bytes()))
                    for _, body in chunks(top[b"CASM"]):
                        entries = list(chunks(body))
                        tables = {value[0]: value for tag, value in entries if tag == b"Ctab"}
                        overrides = {value[0]: value for tag, value in entries if tag == b"Cntt"}
                        self.assertEqual(tables.keys(), overrides.keys())
                        for channel, table in tables.items():
                            self.assertEqual(overrides[channel][1] & 0x7F,
                                             converter.CTAB_TO_CNTT_NTT[table[21]] & 0x7F)


if __name__ == "__main__":
    unittest.main()
