#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cpt2sty_v10.py

CPT -> Yamaha SFF1 style converter with section-specific CASM generation.

Main change in v10:
- keeps generic CASM generation based on CPT data only
- makes Cntt more explicit for each accompaniment family
- forces Source Chord = 7 (byte 0x01, not 0x02/Maj7) for ChordPiano when Casio marks the track as 7th Chord / Variation Chord
- keeps ChordGuitar data-driven, but also respects explicit 7th-chord Casio tagging
- preserves name-independent behavior
"""

import argparse
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

def u16be(b, off=0):
    return (b[off] << 8) | b[off + 1]

def u32be(b, off=0):
    return (b[off] << 24) | (b[off + 1] << 16) | (b[off + 2] << 8) | b[off + 3]

def read_vlq(data, pos):
    value = 0
    while True:
        if pos >= len(data):
            raise ValueError("Unexpected EOF in VLQ")
        c = data[pos]
        pos += 1
        value = (value << 7) | (c & 0x7F)
        if (c & 0x80) == 0:
            break
    return value, pos

def write_vlq(value):
    if value < 0:
        raise ValueError("VLQ cannot encode negative values")
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    out.reverse()
    return bytes(out)

def chunk(tag, payload):
    return tag + len(payload).to_bytes(4, "big") + payload

def meta_text(meta_type, text):
    raw = text.encode("ascii", errors="replace")
    return b"\xFF" + bytes([meta_type]) + write_vlq(len(raw)) + raw

def meta_marker(text):
    return meta_text(0x06, text)

def meta_track_name(text):
    return meta_text(0x03, text)

def meta_tempo(bpm):
    if bpm <= 0:
        bpm = 120
    mpqn = int(round(60000000 / bpm))
    return b"\xFF\x51\x03" + bytes([(mpqn >> 16) & 0xFF, (mpqn >> 8) & 0xFF, mpqn & 0xFF])

def meta_time_signature(num, den):
    if num <= 0:
        num = 4
    if den <= 0:
        den = 4
    power = 0
    d = den
    while d > 1 and d % 2 == 0:
        d //= 2
        power += 1
    return b"\xFF\x58\x04" + bytes([num & 0xFF, power & 0xFF, 24, 8])

def sysex_gm_on():
    return bytes.fromhex("F0 05 7E 7F 09 01 F7")

def sysex_xg_on():
    return bytes.fromhex("F0 43 10 4C 00 00 7E 00 F7")

SECTION_NAMES = {0x0: "Intro", 0x2: "Variation1", 0x3: "Variation2", 0x6: "Fill1", 0x7: "Fill2", 0xA: "Ending"}
PART_NAMES = {0x0: "Drum", 0x3: "Bass", 0x5: "ChordPiano", 0x6: "ChordGuitar", 0x7: "Phrase"}
YAMAHA_SECTION_MAP = {"Intro": "Intro A", "Variation1": "Main A", "Variation2": "Main B", "Fill1": "Fill In AA", "Fill2": "Fill In BB", "Ending": "Ending A"}
PART_TO_MIDI_CHANNEL = {"Drum": 10, "Bass": 11, "ChordPiano": 12, "ChordGuitar": 13, "Phrase": 15}

CCT_INFO = {
    0:  {"name": "Basic Bass", "group": "bass_basic"},
    1:  {"name": "7th Bass", "group": "bass_7th"},
    2:  {"name": "Basic Chord", "group": "chord_basic"},
    3:  {"name": "Basic Chord2", "group": "chord_basic2"},
    4:  {"name": "Variation Chord1", "group": "chord_var7"},
    5:  {"name": "Variation Chord2", "group": "chord_var7"},
    6:  {"name": "7th Chord", "group": "chord_7th"},
    7:  {"name": "Minor Chord", "group": "chord_minor"},
    8:  {"name": "Major Phrase", "group": "phrase_major"},
    9:  {"name": "Minor Bass Phrase", "group": "bass_minor_phrase"},
    10: {"name": "Penta Phrase", "group": "phrase_penta"},
    11: {"name": "Natural Minor", "group": "chord_nat_minor"},
    12: {"name": "Melodic Minor", "group": "chord_melodic_minor"},
    13: {"name": "Harmonic Minor", "group": "chord_harm_minor"},
    14: {"name": "No Change", "group": "phrase_no_change"},
    15: {"name": "Melodic Minor 2", "group": "chord_melodic_minor2"},
    16: {"name": "Dorian Scale", "group": "chord_dorian"},
    17: {"name": "Minor -> Major", "group": "chord_minor_to_major"},
}

def decode_element_id(element_id):
    section_code = (element_id >> 4) & 0x0F
    part_code = element_id & 0x0F
    return {
        "element_id": element_id,
        "element_hex": "0x%02X" % element_id,
        "section_code": section_code,
        "section_name": SECTION_NAMES.get(section_code, "UnknownSection_%X" % section_code),
        "part_code": part_code,
        "part_name": PART_NAMES.get(part_code, "UnknownPart_%X" % part_code),
    }

@dataclass
class CasaItem:
    index: int
    offset_in_header: int
    type: int
    size: int
    payload_hex: str
    meaning: str = ""
    track_index: int | None = None
    decoded: dict = field(default_factory=dict)

@dataclass
class Event:
    index: int
    delta: int
    abs_time: int
    kind: str
    status: int | None
    event_type: str
    raw_hex: str
    raw_bytes: bytes
    meta_type: int | None = None
    payload: bytes = b""
    decoded: dict = field(default_factory=dict)

@dataclass
class Track:
    track_index: int
    offset: int
    length: int
    element_id: int | None = None
    element_info: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    ff81: dict | None = None
    ff82: dict | None = None

@dataclass
class CPTFile:
    file_name: str
    file_path: str
    file_size: int
    casa_len: int
    name: str | None
    track_count_declared: int | None
    resolution: int | None
    tempo_raw: int | None
    timesig_num: int | None
    timesig_den: int | None
    casa_items: list
    element_map: list
    tracks: list

@dataclass
class ValidationIssue:
    level: str
    code: str
    message: str
    track_index: int | None = None
    extra: dict = field(default_factory=dict)

def parse_casa(data):
    if len(data) < 8:
        raise ValueError("File too short")
    if data[:4] != b"CASA":
        raise ValueError("Missing CASA magic")
    casa_len = u32be(data, 4)
    if len(data) < 8 + casa_len:
        raise ValueError("Truncated CASA header")
    header = data[8:8 + casa_len]
    pos = 0
    idx = 0
    items = []
    info = {"name": None, "track_count_declared": None, "resolution": None, "tempo_raw": None, "timesig_num": None, "timesig_den": None, "element_map": []}
    while pos < len(header):
        if pos + 2 > len(header):
            raise ValueError("Broken TLV at header offset %d" % pos)
        typ = header[pos]
        size = header[pos + 1]
        end = pos + 2 + size
        if end > len(header):
            raise ValueError("TLV payload exceeds CASA at offset %d" % pos)
        payload = header[pos + 2:end]
        item = CasaItem(idx, pos, typ, size, payload.hex().upper())
        if typ < 240:
            item.meaning = "element_map"
            if size >= 2:
                track_idx = u16be(payload, 0)
                item.track_index = track_idx
                item.decoded = decode_element_id(typ)
                info["element_map"].append((typ, track_idx))
        elif typ == 241:
            item.meaning = "name"
            info["name"] = payload.decode("ascii", errors="replace")
            item.decoded = {"name": info["name"]}
        elif typ == 242 and size >= 2:
            item.meaning = "track_count"
            info["track_count_declared"] = u16be(payload, 0)
            item.decoded = {"track_count": info["track_count_declared"]}
        elif typ == 243 and size >= 2:
            item.meaning = "resolution"
            info["resolution"] = u16be(payload, 0)
            item.decoded = {"resolution": info["resolution"]}
        elif typ == 244 and size >= 2:
            item.meaning = "tempo"
            info["tempo_raw"] = u16be(payload, 0)
            item.decoded = {"tempo_raw": info["tempo_raw"]}
        elif typ == 245 and size >= 2:
            item.meaning = "time_signature"
            info["timesig_num"] = payload[0]
            info["timesig_den"] = payload[1]
            item.decoded = {"numerator": payload[0], "denominator": payload[1]}
        else:
            item.meaning = "unknown"
        items.append(item)
        idx += 1
        pos = end
    return casa_len, items, info

CHANNEL_DATA_LENGTH = {0x8: 2, 0x9: 2, 0xA: 2, 0xB: 2, 0xC: 1, 0xD: 1, 0xE: 2}

def decode_ff81(payload):
    d = {"raw_len": len(payload), "payload_hex": payload.hex().upper()}
    if len(payload) >= 7:
        d.update({
            "original_key": payload[0],
            "unknown_2": payload[1],
            "cct": payload[2],
            "break_point": payload[3],
            "unknown_5": payload[4],
            "unknown_6": payload[5],
            "inversion": payload[6],
        })
    return d

def decode_ff82(payload):
    d = {"raw_len": len(payload), "payload_hex": payload.hex().upper()}
    if len(payload) >= 1:
        d["bars"] = payload[0]
    return d

def parse_track_events(track_data):
    pos = 0
    abs_time = 0
    running_status = None
    out = []
    idx = 0
    while pos < len(track_data):
        delta, pos = read_vlq(track_data, pos)
        abs_time += delta
        if pos >= len(track_data):
            raise ValueError("Unexpected EOF after delta")
        event_start = pos
        first = track_data[pos]
        if first & 0x80:
            pos += 1
            status = first
        else:
            if running_status is None:
                raise ValueError("Running status used before initialization")
            status = running_status
        raw = bytearray()
        raw.extend(track_data[event_start:pos])
        if status == 0xFF:
            if pos >= len(track_data):
                raise ValueError("Unexpected EOF in meta event")
            meta_type = track_data[pos]
            pos += 1
            raw.append(meta_type)
            vlq_start = pos
            meta_len, pos = read_vlq(track_data, pos)
            raw.extend(track_data[vlq_start:pos])
            if pos + meta_len > len(track_data):
                raise ValueError("Unexpected EOF in meta payload")
            payload = track_data[pos:pos + meta_len]
            pos += meta_len
            raw.extend(payload)
            ev_type = "meta_0x%02X" % meta_type
            decoded = {}
            if meta_type == 0x81:
                ev_type = "meta_ff81"
                decoded = decode_ff81(payload)
            elif meta_type == 0x82:
                ev_type = "meta_ff82"
                decoded = decode_ff82(payload)
            elif meta_type == 0x80:
                ev_type = "meta_ff80"
            elif meta_type == 0x2F:
                ev_type = "meta_end_of_track"
            elif meta_type == 0x51 and len(payload) == 3:
                mpqn = (payload[0] << 16) | (payload[1] << 8) | payload[2]
                decoded = {"mpqn": mpqn, "bpm": (60000000 / mpqn if mpqn else None)}
                ev_type = "meta_tempo"
            elif meta_type == 0x58 and len(payload) >= 2:
                decoded = {"numerator": payload[0], "denominator": 2 ** payload[1]}
                ev_type = "meta_time_signature"
            out.append(Event(idx, delta, abs_time, "meta", 0xFF, ev_type, bytes(raw).hex().upper(), bytes(raw), meta_type, payload, decoded))
            idx += 1
            continue
        if status in (0xF0, 0xF7):
            vlq_start = pos
            data_len, pos = read_vlq(track_data, pos)
            raw.extend(track_data[vlq_start:pos])
            if pos + data_len > len(track_data):
                raise ValueError("Unexpected EOF in sysex")
            payload = track_data[pos:pos + data_len]
            pos += data_len
            raw.extend(payload)
            out.append(Event(idx, delta, abs_time, "sysex", status, "sysex_0x%02X" % status, bytes(raw).hex().upper(), bytes(raw), None, payload))
            idx += 1
            running_status = None
            continue
        hi = (status >> 4) & 0x0F
        if hi not in CHANNEL_DATA_LENGTH:
            raise ValueError("Unsupported status 0x%02X" % status)
        data_len = CHANNEL_DATA_LENGTH[hi]
        if pos + data_len > len(track_data):
            raise ValueError("Unexpected EOF in channel payload")
        payload = track_data[pos:pos + data_len]
        pos += data_len
        raw.extend(payload)
        names = {0x8: "note_off", 0x9: "note_on", 0xA: "poly_aftertouch", 0xB: "control_change", 0xC: "program_change", 0xD: "channel_pressure", 0xE: "pitch_bend"}
        decoded = {"channel0": status & 0x0F}
        out.append(Event(idx, delta, abs_time, "channel", status, names[hi], bytes(raw).hex().upper(), bytes(raw), None, payload, decoded))
        idx += 1
        running_status = status
    return out

def parse_tracks(data, start_pos):
    tracks = []
    pos = start_pos
    ti = 0
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("Incomplete MTrk header at offset %d" % pos)
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("Expected MTrk at offset %d" % pos)
        track_len = u32be(data, pos + 4)
        tstart = pos + 8
        tend = tstart + track_len
        if tend > len(data):
            raise ValueError("Track %d exceeds file size" % ti)
        events = parse_track_events(data[tstart:tend])
        tr = Track(ti, pos, track_len, events=events)
        for ev in events:
            if ev.meta_type == 0x81 and tr.ff81 is None:
                tr.ff81 = ev.decoded
            elif ev.meta_type == 0x82 and tr.ff82 is None:
                tr.ff82 = ev.decoded
        tracks.append(tr)
        pos = tend
        ti += 1
    return tracks

def parse_cpt(path):
    data = path.read_bytes()
    casa_len, casa_items, info = parse_casa(data)
    tracks = parse_tracks(data, 8 + casa_len)
    track_to_element = {track_idx: element_id for element_id, track_idx in info["element_map"]}
    for tr in tracks:
        if tr.track_index in track_to_element:
            tr.element_id = track_to_element[tr.track_index]
            tr.element_info = decode_element_id(tr.element_id)
    return CPTFile(path.name, str(path), len(data), casa_len, info["name"], info["track_count_declared"], info["resolution"], info["tempo_raw"], info["timesig_num"], info["timesig_den"], casa_items, info["element_map"], tracks)

def validate_cpt(cpt):
    issues = []
    def add(level, code, message, track_index=None, **extra):
        issues.append(ValidationIssue(level, code, message, track_index, extra))
    if cpt.track_count_declared is not None and cpt.track_count_declared != len(cpt.tracks):
        add("warning", "TRACK_COUNT_MISMATCH", "CASA declares %s tracks but file contains %s" % (cpt.track_count_declared, len(cpt.tracks)))
    if cpt.resolution is None or cpt.resolution <= 0:
        add("error", "BAD_RESOLUTION", "Invalid resolution: %r" % (cpt.resolution,))
    if not cpt.element_map:
        add("error", "EMPTY_ELEMENT_MAP", "Missing element map")
    for tr in cpt.tracks:
        if tr.element_id is None:
            add("warning", "UNMAPPED_TRACK", "Track %d is not referenced by element map" % tr.track_index, tr.track_index)
    return issues

def compute_ticks_per_bar(cpt):
    res = cpt.resolution or 192
    num = cpt.timesig_num or 4
    den = cpt.timesig_den or 4
    quarter_per_bar = num * (4.0 / den)
    return max(1, int(round(res * quarter_per_bar)))

def compute_track_length_ticks(cpt, track):
    if track.ff82 and track.ff82.get("bars") is not None:
        return int(track.ff82["bars"]) * compute_ticks_per_bar(cpt)
    max_time = 0
    for ev in track.events:
        if ev.meta_type == 0x2F:
            max_time = max(max_time, ev.abs_time)
        elif ev.kind != "meta" or ev.meta_type not in (0x80, 0x81, 0x82):
            max_time = max(max_time, ev.abs_time)
    ticks_per_bar = compute_ticks_per_bar(cpt)
    if max_time == 0:
        return ticks_per_bar
    bars = max(1, (max_time + ticks_per_bar - 1) // ticks_per_bar)
    return bars * ticks_per_bar

BASE_CTAB_SECTION = {
    "Main A": {
        "Drum":        bytearray(bytes.fromhex("095279746D4465662009000FFF07FFFFFFFF0002010006007F0100")),
        "Bass":        bytearray(bytes.fromhex("0A42617373446566200A010FFF03FFFFFFFF00020001031A360200")),
        "ChordPiano":  bytearray(bytes.fromhex("0B43686F72644465660B010FFF03FFFFFFFF0000000207007F0100")),
        "ChordGuitar": bytearray(bytes.fromhex("0C43686F72644465660C010FFF03FFFFFFFF0013000207007F0100")),
        "Phrase":      bytearray(bytes.fromhex("0E50687261736544650E010FFF03FFFFFFFF0000000107007F0100")),
    },
    "Main B": {
        "Drum":        bytearray(bytes.fromhex("095279746D4465662009000FFF07FFFFFFFF0002010006007F0100")),
        "Bass":        bytearray(bytes.fromhex("0A42617373446566200A010FFF03FFFFFFFF00020001031A360200")),
        "ChordPiano":  bytearray(bytes.fromhex("0B43686F72644465660B010FFF03FFFFFFFF0000000207007F0100")),
        "ChordGuitar": bytearray(bytes.fromhex("0C43686F72644465660C010FFF03FFFFFFFF0013000207007F0100")),
        "Phrase":      bytearray(bytes.fromhex("0E50687261736544650E010FFF03FFFFFFFF0013000107007F0100")),
    },
    "Fill In AA": {
        "Drum":        bytearray(bytes.fromhex("095279746D4465662009000FFF07FFFFFFFF0002010006007F0100")),
        "Bass":        bytearray(bytes.fromhex("0A42617373446566200A010FFF03FFFFFFFF00020000031A360200")),
        "ChordPiano":  bytearray(bytes.fromhex("0B43686F72644465660B010FFF03FFFFFFFF0000000207007F0100")),
        "ChordGuitar": bytearray(bytes.fromhex("0C43686F72644465660C010FFF03FFFFFFFF0013000107007F0000")),
        "Phrase":      bytearray(bytes.fromhex("0E50687261736544650E010FFF03FFFFFFFF0000000107007F0100")),
    },
    "Fill In BB": {
        "Drum":        bytearray(bytes.fromhex("095279746D4465662009000FFF07FFFFFFFF0002010006007F0100")),
        "Bass":        bytearray(bytes.fromhex("0A42617373446566200A010FFF03FFFFFFFF00020000031A360200")),
        "ChordPiano":  bytearray(bytes.fromhex("0B43686F72644465660B010FFF03FFFFFFFF0000000207007F0100")),
        "ChordGuitar": bytearray(bytes.fromhex("0C43686F72644465660C010FFF03FFFFFFFF0002000107007F0000")),
        "Phrase":      bytearray(bytes.fromhex("0E50687261736544650E010FFF03FFFFFFFF0002000007007F0100")),
    },
    "Intro A": {
        "Drum":        bytearray(bytes.fromhex("095279746D4465662009000FFF07FFFFFFFF0002010006007F0100")),
        "Bass":        bytearray(bytes.fromhex("0A42617373446566200A010FFF03FFFFFFFF00020000031A360200")),
        "ChordPiano":  bytearray(bytes.fromhex("0B43686F72644465660B010FFF03FFFFFFFF0002000407007F0000")),
        "ChordGuitar": bytearray(bytes.fromhex("0C43686F72644465660C010FFF03FFFFFFFF0002000407007F0000")),
        "Phrase":      bytearray(bytes.fromhex("0E50687261736544650E010FFF03FFFFFFFF0000000107007F0100")),
    },
    "Ending A": {
        "Drum":        bytearray(bytes.fromhex("095279746D4465662009000FFF07FFFFFFFF0002010006007F0100")),
        "Bass":        bytearray(bytes.fromhex("0A42617373446566200A010FFF03FFFFFFFF00020000031A360200")),
        "ChordPiano":  bytearray(bytes.fromhex("0B43686F72644465660B010FFF03FFFFFFFF0002000407007F0000")),
        "ChordGuitar": bytearray(bytes.fromhex("0C43686F72644465660C010FFF03FFFFFFFF0002000407007F0000")),
        "Phrase":      bytearray(bytes.fromhex("0E50687261736544650E010FFF03FFFFFFFF0002000107007F0100")),
    },
}

BASE_CNTT = {
    "Main A": {"Drum": bytes.fromhex("0900"), "Bass": bytes.fromhex("0A81"), "ChordPiano": bytes.fromhex("0B01"), "ChordGuitar": bytes.fromhex("0C01"), "Phrase": bytes.fromhex("0E01")},
    "Main B": {"Drum": bytes.fromhex("0900"), "Bass": bytes.fromhex("0A81"), "ChordPiano": bytes.fromhex("0B01"), "ChordGuitar": bytes.fromhex("0C01"), "Phrase": bytes.fromhex("0E01")},
    "Fill In AA": {"Drum": bytes.fromhex("0900"), "Bass": bytes.fromhex("0A00"), "ChordPiano": bytes.fromhex("0B01"), "ChordGuitar": bytes.fromhex("0C01"), "Phrase": bytes.fromhex("0E01")},
    "Fill In BB": {"Drum": bytes.fromhex("0900"), "Bass": bytes.fromhex("0A00"), "ChordPiano": bytes.fromhex("0B01"), "ChordGuitar": bytes.fromhex("0C01"), "Phrase": bytes.fromhex("0E00")},
    "Intro A": {"Drum": bytes.fromhex("0900"), "Bass": bytes.fromhex("0A00"), "ChordPiano": bytes.fromhex("0B04"), "ChordGuitar": bytes.fromhex("0C04"), "Phrase": bytes.fromhex("0E01")},
    "Ending A": {"Drum": bytes.fromhex("0900"), "Bass": bytes.fromhex("0A00"), "ChordPiano": bytes.fromhex("0B04"), "ChordGuitar": bytes.fromhex("0C04"), "Phrase": bytes.fromhex("0E01")},
}

STYLE_OVERRIDES = {}

def normalized_style_name(name):
    if not name:
        return ""
    # CPT internal names often differ from the source filename.
    # Normalize whitespace and keep the plain internal style name for lookup.
    return " ".join(name.strip().split())

def get_cct(track):
    ff81 = track.ff81 or {}
    return ff81.get("cct")

def get_cct_group(track):
    cct = get_cct(track)
    if cct in CCT_INFO:
        return CCT_INFO[cct]["group"]
    return "unknown"

def get_cct_name(track):
    cct = get_cct(track)
    if cct in CCT_INFO:
        return CCT_INFO[cct]["name"]
    return "Unknown"



def get_note_pitch_classes(track):
    pcs = set()
    for ev in track.events:
        if ev.event_type == "note_on" and len(ev.payload) >= 2 and ev.payload[1] > 0:
            pcs.add(ev.payload[0] % 12)
    return pcs

def infer_harmony_from_notes(track):
    pcs = get_note_pitch_classes(track)
    return {
        "has_minor_3rd": 3 in pcs,
        "has_major_3rd": 4 in pcs,
        "has_perfect_5th": 7 in pcs,
        "has_minor_7th": 10 in pcs,
        "has_major_7th": 11 in pcs,
        "pitch_classes": sorted(pcs),
    }

def choose_source_chord_family(track, yamaha_section):
    part = track.element_info.get("part_name")
    cct_group = get_cct_group(track)

    if part == "Drum":
        return "Cmaj7"

    if part == "Bass":
        if cct_group == "bass_7th":
            return "C7"
        if cct_group in ("bass_minor_phrase", "chord_nat_minor"):
            return "Cm"
        return "C"

    # v6 fix:
    # Yamaha chord-accompaniment parts are safer when their Source Chord reflects
    # the way the source pattern was recorded, not the plain harmony we want to hear.
    # In practice this means chord guitar must default to C7 for normal chord sections,
    # otherwise Yamaha tends to keep/add the 7th during transposition.
    if part == "ChordGuitar":
        if cct_group in (
            "chord_minor",
            "chord_nat_minor",
            "chord_melodic_minor",
            "chord_harm_minor",
            "chord_melodic_minor2",
            "chord_dorian",
            "chord_minor_to_major",
        ):
            return "Cm"
        return "C7"

    if part == "ChordPiano":
        if cct_group in (
            "chord_minor",
            "chord_nat_minor",
            "chord_melodic_minor",
            "chord_harm_minor",
            "chord_melodic_minor2",
            "chord_dorian",
            "chord_minor_to_major",
        ):
            return "Cm"
        if cct_group in ("chord_7th", "chord_var7", "chord_basic", "chord_basic2"):
            return "C7"
        return "C7"

    if part == "Phrase":
        if cct_group == "phrase_no_change":
            return "recorded"
        if cct_group == "chord_nat_minor":
            return "Cm"
        if cct_group == "chord_basic2":
            return "C7"
        return "C"

    return "Cmaj7"


def is_phrase_chordal(track, yamaha_section):
    part = track.element_info.get("part_name")
    if part != "Phrase":
        return False
    if yamaha_section not in ("Main A", "Main B", "Fill In AA", "Fill In BB"):
        return False
    cct_group = get_cct_group(track)
    return cct_group.startswith("chord_")

def should_use_chord_ntt(track, yamaha_section):
    part = track.element_info.get("part_name")
    if yamaha_section not in ("Main A", "Main B", "Fill In AA", "Fill In BB"):
        return False
    if part in ("ChordPiano", "ChordGuitar"):
        return True
    return is_phrase_chordal(track, yamaha_section)

def choose_profile(track, yamaha_section):
    part = track.element_info.get("part_name")
    family = choose_source_chord_family(track, yamaha_section)
    if part == "Drum":
        return "drum"
    if part == "Bass":
        if family == "C7":
            return "bass_7th"
        if family == "Cm":
            return "bass_minor"
        return "bass_basic"
    if part in ("ChordPiano", "ChordGuitar"):
        if family == "C7":
            return "chord_7th"
        if family == "Cm":
            return "chord_minor"
        if family == "C":
            return "chord_basic_c"
        return "chord_basic"
    if part == "Phrase":
        if is_phrase_chordal(track, yamaha_section):
            if family == "Cm":
                return "chord_minor"
            if family == "C7":
                return "chord_7th"
            if family == "C":
                return "chord_basic_c"
        if family == "recorded":
            return "phrase_no_change"
        if family == "C7":
            return "phrase_7th"
        if family == "Cm":
            return "phrase_minor"
        return "phrase_basic"
    return "fallback"

def get_source_root(track):
    ff81 = track.ff81 or {}
    root = ff81.get("original_key")
    if isinstance(root, int):
        return root % 12
    return 0


def make_ctab_default(track, yamaha_section):
    part = track.element_info.get("part_name")
    base = BASE_CTAB_SECTION[yamaha_section][part][:]

    # Source Root is stored in Ctab, not in Cntt.
    # Casio FF81.original_key gives the recorded key center (0=C, 5=F, ...).
    # Yamaha expects that value in the Source Root field for accompaniment tracks.
    if part != "Drum":
        base[18] = get_source_root(track)

    # Project rule:
    # chord accompaniment tracks should default to Yamaha "Chord" NTT,
    # not "Melody". This includes Phrase tracks that Casio itself tags
    # with a chord-oriented CCT in Main/Fill sections.
    if should_use_chord_ntt(track, yamaha_section):
        base[19] = 0x13
    source_family = choose_source_chord_family(track, yamaha_section)
    profile = choose_profile(track, yamaha_section)
    return bytes(base), profile, source_family

def make_cntt_default(track, yamaha_section, source_family):
    part = track.element_info.get("part_name")
    cct_group = get_cct_group(track)
    base = bytearray(BASE_CNTT[yamaha_section][part])

    # Project rule:
    # for accompaniment chord tracks in Main/Fill sections, Yamaha behaves
    # more reliably when Source Chord defaults to dominant 7.
    if part in ("ChordPiano", "ChordGuitar") and yamaha_section in ("Main A", "Main B", "Fill In AA", "Fill In BB"):
        base[1] = 0x01
    elif part == "ChordPiano":
        if cct_group in ("chord_7th", "chord_var7"):
            base[1] = 0x01
        elif source_family == "Cm":
            base[1] = 0x03
        elif source_family == "C":
            base[1] = 0x00

    elif part == "ChordGuitar":
        notes = infer_harmony_from_notes(track)
        if cct_group in ("chord_7th", "chord_var7") or notes["has_minor_7th"]:
            base[1] = 0x01
        elif source_family == "Cm":
            base[1] = 0x03
        elif source_family == "C":
            base[1] = 0x00

    if part == "Bass":
        if source_family == "Cm":
            base[1] = 0x03
        elif source_family == "C7":
            base[1] = 0x01
        else:
            base[1] = base[1]

    if part == "Phrase":
        if is_phrase_chordal(track, yamaha_section):
            if source_family in ("C7", "C"):
                # Project rule: chordal phrase/accompaniment tracks in Main/Fill
                # are more reliable on Yamaha when Source Chord defaults to 7.
                base[1] = 0x01
            elif source_family == "Cm":
                base[1] = 0x03
        else:
            if source_family == "C7":
                base[1] = 0x01
            elif source_family == "Cm":
                base[1] = 0x03
            elif source_family == "C":
                base[1] = 0x00

    return bytes(base)

def apply_style_override(cpt, yamaha_section, track, ctab_payload, cntt_payload):
    return ctab_payload, cntt_payload, False

def build_cseg_for_section(cpt, yamaha_section, tracks):
    payload = bytearray()
    payload.extend(chunk(b"Sdec", yamaha_section.encode("ascii", errors="replace")))
    report_tracks = []
    part_order = ["Drum", "Bass", "ChordPiano", "ChordGuitar", "Phrase"]
    for part_name in part_order:
        track = None
        for tr in tracks:
            if tr.element_info.get("part_name") == part_name:
                track = tr
                break
        if track is None:
            continue
        ctab_payload, profile, source_family = make_ctab_default(track, yamaha_section)
        cntt_payload = make_cntt_default(track, yamaha_section, source_family)
        ctab_payload, cntt_payload, used_override = apply_style_override(cpt, yamaha_section, track, ctab_payload, cntt_payload)
        payload.extend(chunk(b"Ctab", ctab_payload))
        payload.extend(chunk(b"Cntt", cntt_payload))
        report_tracks.append({
            "track_index": track.track_index,
            "part_name": part_name,
            "casio_section": track.element_info.get("section_name"),
            "yamaha_section": yamaha_section,
            "cct": get_cct(track),
            "cct_name": get_cct_name(track),
            "cct_group": get_cct_group(track),
            "selected_profile": profile,
            "source_chord_family": source_family,
            "ff81": track.ff81,
            "ff82": track.ff82,
            "ctab_hex": ctab_payload.hex().upper(),
            "cntt_hex": cntt_payload.hex().upper(),
            "used_style_override": used_override,
        })
    return chunk(b"CSEG", bytes(payload)), {"section": yamaha_section, "tracks": report_tracks}

def build_casm(cpt):
    by_yamaha_section = {}
    for tr in cpt.tracks:
        sec = tr.element_info.get("section_name")
        part = tr.element_info.get("part_name")
        if sec in YAMAHA_SECTION_MAP and part in PART_TO_MIDI_CHANNEL:
            ys = YAMAHA_SECTION_MAP[sec]
            by_yamaha_section.setdefault(ys, []).append(tr)
    cseg_chunks = []
    cseg_reports = []
    order = ["Main A", "Main B", "Fill In AA", "Fill In BB", "Intro A", "Ending A"]
    for ys in order:
        tracks = by_yamaha_section.get(ys, [])
        if not tracks:
            continue
        cseg, report = build_cseg_for_section(cpt, ys, tracks)
        cseg_chunks.append(cseg)
        cseg_reports.append(report)
    return chunk(b"CASM", b"".join(cseg_chunks)), {"csegs": cseg_reports}

def remap_channel_event(raw, target_channel_1based):
    if not raw:
        return raw
    status = raw[0]
    if status < 0x80 or status >= 0xF0:
        return raw
    ch0 = (target_channel_1based - 1) & 0x0F
    return bytes([(status & 0xF0) | ch0]) + raw[1:]

def build_style_track(cpt):
    ticks_per_bar = compute_ticks_per_bar(cpt)
    bpm = cpt.tempo_raw or 120
    num = cpt.timesig_num or 4
    den = cpt.timesig_den or 4
    name = (cpt.name or cpt.file_name.rsplit(".", 1)[0])[:64]
    timeline = []
    def add_event(abs_tick, ev):
        timeline.append((abs_tick, ev))
    add_event(0, meta_track_name(name))
    add_event(0, meta_tempo(bpm))
    add_event(0, meta_time_signature(num, den))
    add_event(0, meta_marker("SFF1"))
    add_event(0, meta_marker("SInt"))
    add_event(0, sysex_gm_on())
    add_event(0, sysex_xg_on())
    for part, midi_ch in PART_TO_MIDI_CHANNEL.items():
        ch0 = midi_ch - 1
        add_event(0, bytes([0xB0 | ch0, 7, 100]))
        add_event(0, bytes([0xB0 | ch0, 10, 64]))
        add_event(0, bytes([0xB0 | ch0, 91, 40]))
    by_section = {}
    for tr in cpt.tracks:
        sec = tr.element_info.get("section_name")
        part = tr.element_info.get("part_name")
        if sec in YAMAHA_SECTION_MAP and part in PART_TO_MIDI_CHANNEL:
            by_section.setdefault(sec, []).append(tr)
    section_order = ["Intro", "Variation1", "Fill1", "Variation2", "Fill2", "Ending"]
    current_start = ticks_per_bar
    for sec in section_order:
        tracks = by_section.get(sec, [])
        if not tracks:
            continue
        add_event(current_start, meta_marker(YAMAHA_SECTION_MAP[sec]))
        section_len = max(compute_track_length_ticks(cpt, tr) for tr in tracks)
        for tr in tracks:
            target_ch = PART_TO_MIDI_CHANNEL[tr.element_info["part_name"]]
            for ev in tr.events:
                if ev.kind == "meta":
                    if ev.meta_type in (0x80, 0x81, 0x82, 0x2F, 0x51, 0x58):
                        continue
                    continue
                if ev.kind == "sysex":
                    continue
                if ev.kind == "channel":
                    raw = remap_channel_event(ev.raw_bytes, target_ch)
                    add_event(current_start + ev.abs_time, raw)
        current_start += section_len
    add_event(current_start + ticks_per_bar, b"\xFF\x2F\x00")
    timeline.sort(key=lambda x: x[0])
    out = bytearray()
    last_tick = 0
    for tick, ev in timeline:
        delta = tick - last_tick
        if delta < 0:
            raise ValueError("Negative delta while building style")
        out.extend(write_vlq(delta))
        out.extend(ev)
        last_tick = tick
    return bytes(out)

def write_style_file(cpt, out_path):
    if not cpt.resolution:
        raise ValueError("Missing resolution")
    midi_track = build_style_track(cpt)
    midi = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + int(cpt.resolution).to_bytes(2, "big")
    midi += chunk(b"MTrk", midi_track)
    casm_chunk, casm_report = build_casm(cpt)
    out_path.write_bytes(midi + casm_chunk)
    return casm_report

def issues_to_jsonable(issues):
    return [asdict(i) for i in issues]

def main():
    ap = argparse.ArgumentParser(description="Convert CPT to Yamaha SFF1 style with section-specific CASM")
    ap.add_argument("input", help="Input .cpt file")
    ap.add_argument("-o", "--output", help="Output .sty file (default: same name, .sty)")
    ap.add_argument("--report", help="Optional JSON report path")
    args = ap.parse_args()
    in_path = Path(args.input)
    if not in_path.is_file():
        print("Input file not found.")
        return 2
    try:
        cpt = parse_cpt(in_path)
    except Exception as e:
        print("Parse error: %s" % e)
        return 2
    issues = validate_cpt(cpt)
    errors = [i for i in issues if i.level == "error"]
    out_path = Path(args.output) if args.output else in_path.with_suffix(".sty")
    report_path = Path(args.report) if args.report else out_path.with_suffix(".json")
    report = {
        "input_file": str(in_path),
        "output_file": str(out_path),
        "parsed_ok": True,
        "structurally_valid": len(errors) == 0,
        "summary": {
            "name": cpt.name,
            "track_count_declared": cpt.track_count_declared,
            "track_count_actual": len(cpt.tracks),
            "resolution": cpt.resolution,
            "tempo_raw": cpt.tempo_raw,
            "timesig_num": cpt.timesig_num,
            "timesig_den": cpt.timesig_den,
        },
        "tracks": [
            {
                "track_index": t.track_index,
                "element_id": t.element_id,
                "element_info": t.element_info,
                "ff81": t.ff81,
                "ff82": t.ff82,
                "cct_name": get_cct_name(t),
                "cct_group": get_cct_group(t),
            }
            for t in cpt.tracks
        ],
        "issues": issues_to_jsonable(issues),
    }
    if errors:
        report["conversion_performed"] = False
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("CPT parsed, but conversion was NOT performed because the file is structurally invalid.")
        for i in errors:
            print("ERROR %s: %s" % (i.code, i.message))
        print("JSON report: %s" % report_path)
        return 1
    try:
        casm_report = write_style_file(cpt, out_path)
        report["conversion_performed"] = True
        report["casm_report"] = casm_report
    except Exception as e:
        report["conversion_performed"] = False
        report["conversion_error"] = str(e)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Conversion error: %s" % e)
        print("JSON report: %s" % report_path)
        return 2
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    warn_count = sum(1 for i in issues if i.level == "warning")
    info_count = sum(1 for i in issues if i.level == "info")
    print("Conversion successful.")
    print("Output style: %s" % out_path)
    print("JSON report:  %s" % report_path)
    print("Warnings: %d, Infos: %d" % (warn_count, info_count))
    print("Note: section-specific CASM profiles are used.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
