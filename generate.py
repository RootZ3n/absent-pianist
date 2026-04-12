#!/usr/bin/env python3
"""
Absent Pianist - Hymn Library Generator

Generates a complete music file library for small churches without a pianist.
For each hymn: downloads source MIDI, splits into intro/verse/refrain sections,
converts to MusicXML, and renders to WAV via FluidSynth.

Output per hymn: 9 files (intro/verse/refrain x MIDI/MusicXML/WAV)
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import mido
import requests

BASE_DIR = Path(__file__).parent.resolve()
HYMNS_FILE = BASE_DIR / "hymns.txt"
SOURCES_FILE = BASE_DIR / "hymn_sources.json"
OUTPUT_DIR = BASE_DIR / "output"
SOUNDFONT = BASE_DIR / "soundfont" / "Salamander.sf2"
CACHE_DIR = BASE_DIR / ".cache"

SECTIONS = ["intro", "verse", "refrain"]


def load_hymns():
    """Load hymn list from hymns.txt, one per line."""
    with open(HYMNS_FILE) as f:
        return [line.strip() for line in f if line.strip()]


def load_sources():
    """Load hymn source mappings from hymn_sources.json."""
    if SOURCES_FILE.exists():
        with open(SOURCES_FILE) as f:
            return json.load(f)
    return {}


def save_sources(sources):
    """Write hymn sources back to disk."""
    with open(SOURCES_FILE, "w") as f:
        json.dump(sources, f, indent=2)
        f.write("\n")


def slugify(name):
    """Convert hymn name to filesystem-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s


def hymn_folder(index, name):
    """Return output folder path for a hymn: output/001_amazing_grace/."""
    return OUTPUT_DIR / f"{index:03d}_{slugify(name)}"


def download_midi(url, dest):
    """Download a MIDI file from URL. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return True
    try:
        print(f"  Downloading: {url}")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        if resp.content[:4] != b"MThd":
            print("  ERROR: Downloaded file is not valid MIDI (no MThd header)")
            return False
        dest.write_bytes(resp.content)
        return True
    except requests.RequestException as e:
        print(f"  ERROR downloading: {e}")
        return False


def force_piano(midi_file_path):
    """Force Acoustic Grand Piano (program 0) on all tracks and all channels."""
    m = mido.MidiFile(midi_file_path)
    channels_used = set()
    for track in m.tracks:
        for msg in track:
            if hasattr(msg, 'channel'):
                channels_used.add(msg.channel)
    for track in m.tracks:
        for channel in channels_used:
            track.insert(0,
                mido.Message('program_change',
                            channel=channel,
                            program=0,
                            time=0))
    m.save(midi_file_path)


def get_measure_count(midi_path, time_sig_numerator=4):
    """Auto-detect the number of measures in a MIDI file."""
    m = mido.MidiFile(midi_path)
    ticks_per_beat = m.ticks_per_beat
    ticks_per_measure = ticks_per_beat * time_sig_numerator
    total_ticks = max(
        sum(msg.time for msg in track)
        for track in m.tracks
    )
    return max(1, total_ticks // ticks_per_measure)


def find_measure_boundaries(mid):
    """
    Analyze a MIDI file and return a list of tick positions marking measure starts.
    Uses time signature events; defaults to 4/4 if none found.
    Returns list of (measure_number, start_tick) tuples, 1-indexed.
    """
    ticks_per_beat = mid.ticks_per_beat

    time_sigs = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "time_signature":
                time_sigs.append((abs_tick, msg.numerator, msg.denominator))

    if not time_sigs:
        time_sigs = [(0, 4, 4)]
    time_sigs.sort(key=lambda x: x[0])

    total_ticks = 0
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
        total_ticks = max(total_ticks, t)

    measures = []
    current_tick = 0
    measure_num = 1
    sig_idx = 0

    while current_tick < total_ticks:
        measures.append((measure_num, current_tick))
        while sig_idx + 1 < len(time_sigs) and time_sigs[sig_idx + 1][0] <= current_tick:
            sig_idx += 1
        _, numerator, denominator = time_sigs[sig_idx]

        beats_per_measure = numerator
        beat_value = 4.0 / denominator
        ticks_per_measure = int(ticks_per_beat * beats_per_measure * beat_value)

        if ticks_per_measure <= 0:
            ticks_per_measure = ticks_per_beat * 4

        current_tick += ticks_per_measure
        measure_num += 1

    return measures


def extract_section(mid, measures, start_measure, end_measure):
    """
    Extract a section of a MIDI file by measure range (1-indexed, inclusive).
    Returns a new mido.MidiFile.
    """
    if not measures:
        return mid

    total_measures = len(measures)
    start_measure = max(1, min(start_measure, total_measures))
    end_measure = max(start_measure, min(end_measure, total_measures))
    start_tick = measures[start_measure - 1][1]

    if end_measure < total_measures:
        end_tick = measures[end_measure][1]
    else:
        end_tick = 0
        for track in mid.tracks:
            t = 0
            for msg in track:
                t += msg.time
            end_tick = max(end_tick, t)

    new_mid = mido.MidiFile(ticks_per_beat=mid.ticks_per_beat)

    for track in mid.tracks:
        new_track = mido.MidiTrack()
        abs_tick = 0
        prev_out_tick = 0
        pending_meta = []

        for msg in track:
            abs_tick += msg.time

            if abs_tick < start_tick and msg.is_meta and msg.type in (
                "set_tempo", "time_signature", "key_signature", "track_name"
            ):
                pending_meta.append(msg.copy(time=0))
                continue

            if abs_tick < start_tick:
                continue
            if abs_tick >= end_tick:
                if msg.is_meta and msg.type == "end_of_track":
                    pass
                else:
                    continue

            if not new_track and pending_meta:
                for meta_msg in pending_meta:
                    new_track.append(meta_msg)

            out_tick = abs_tick - start_tick
            delta = out_tick - prev_out_tick
            if delta < 0:
                delta = 0
            new_track.append(msg.copy(time=delta))
            prev_out_tick = out_tick

        if new_track:
            new_mid.tracks.append(new_track)

    return new_mid


def sanitize_split_midi(mid):
    """Normalize split MIDI endings so FluidSynth does not hang on trailing note-offs."""
    for track in mid.tracks:
        used_channels = sorted({msg.channel for msg in track if hasattr(msg, "channel")})

        while track and track[-1].is_meta and track[-1].type == "end_of_track":
            track.pop()

        idx = len(track) - 1
        while idx >= 0:
            msg = track[idx]
            if not msg.is_meta and msg.type == "note_on" and msg.velocity == 0:
                track[idx] = msg.copy(time=0)
                idx -= 1
                continue
            break

        for channel in used_channels:
            track.append(mido.Message("control_change", channel=channel, control=123, value=0, time=0))

        track.append(mido.MetaMessage("end_of_track", time=1))

    return mid


def split_midi(source_path, hymn_config, out_folder):
    """
    Split a source MIDI into intro, verse, refrain sections.
    Saves intro.mid, verse.mid, refrain.mid to out_folder.
    Returns dict of section -> Path for successfully created files.
    """
    try:
        mid = mido.MidiFile(str(source_path))
    except Exception as e:
        print(f"  ERROR parsing MIDI: {e}")
        return {}

    measures = find_measure_boundaries(mid)
    total_measures = len(measures)

    if total_measures == 0:
        print("  WARNING: No measures detected, using whole file for each section")
        for section in SECTIONS:
            dest = out_folder / f"{section}.mid"
            sanitized = sanitize_split_midi(mido.MidiFile(str(source_path)))
            sanitized.save(str(dest))
        return {section: out_folder / f"{section}.mid" for section in SECTIONS}

    intro_range = hymn_config.get("intro_measures", [1, 2])
    verse_range = hymn_config.get("verse_measures", [1, total_measures])
    refrain_range = hymn_config.get("refrain_measures")

    # Auto-detect measure splits if config has conservative defaults
    # and the MIDI actually has more than 20 measures
    auto_count = get_measure_count(str(source_path))
    if verse_range[1] <= 16 and auto_count > 20:
        print(f"  Auto-detecting splits: {auto_count} measures detected (config had {verse_range})")
        intro_range = [1, 2]
        half = auto_count // 2
        verse_range = [1, half]
        refrain_range = [half + 1, auto_count]

    results = {}

    intro_mid = sanitize_split_midi(extract_section(mid, measures, intro_range[0], intro_range[1]))
    intro_path = out_folder / "intro.mid"
    intro_mid.save(str(intro_path))
    results["intro"] = intro_path

    if verse_range:
        verse_mid = extract_section(mid, measures, verse_range[0], verse_range[1])
    else:
        verse_mid = mid
    verse_mid = sanitize_split_midi(verse_mid)
    verse_path = out_folder / "verse.mid"
    verse_mid.save(str(verse_path))
    results["verse"] = verse_path

    if refrain_range:
        refrain_mid = extract_section(mid, measures, refrain_range[0], refrain_range[1])
    else:
        half = total_measures // 2 + 1
        refrain_mid = extract_section(mid, measures, half, total_measures)
    refrain_mid = sanitize_split_midi(refrain_mid)
    refrain_path = out_folder / "refrain.mid"
    refrain_mid.save(str(refrain_path))
    results["refrain"] = refrain_path

    # Force Acoustic Grand Piano on all section MIDI files
    for section_path in results.values():
        force_piano(str(section_path))

    return results


def midi_to_musicxml(midi_path, xml_path):
    """Convert a MIDI file to MusicXML using music21."""
    try:
        from music21 import converter

        score = converter.parse(str(midi_path))
        score.write("musicxml", fp=str(xml_path))
        return True
    except Exception as e:
        print(f"  ERROR converting to MusicXML: {e}")
        return False


def midi_to_wav(midi_path, wav_path):
    """Render MIDI to WAV using FluidSynth."""
    if not SOUNDFONT.exists():
        print(f"  SKIP WAV: Soundfont not found at {SOUNDFONT}")
        return False

    if not shutil.which("fluidsynth"):
        print("  SKIP WAV: fluidsynth not installed (sudo apt install fluidsynth)")
        return False

    try:
        result = subprocess.run(
            [
                "fluidsynth", "-ni",
                "-F", str(wav_path),
                "-r", "44100",
                str(SOUNDFONT),
                str(midi_path),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            print(f"  ERROR fluidsynth: {result.stderr.strip()}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("  FluidSynth timeout after 90s")
        return False
    except Exception as e:
        print(f"  ERROR rendering WAV: {e}")
        return False


def check_hymn_status(index, name, sources, skip_wav=False):
    """Check status of a hymn. Returns status string and symbol."""
    if name not in sources:
        return "missing", "✗"

    folder = hymn_folder(index, name)
    if not folder.exists():
        return "missing", "✗"

    expected = []
    for section in SECTIONS:
        expected.append(f"{section}.mid")
        expected.append(f"{section}.musicxml")
        if not skip_wav:
            expected.append(f"{section}.wav")

    existing = [f.name for f in folder.iterdir()] if folder.exists() else []
    found = sum(1 for expected_name in expected if expected_name in existing)

    if found == len(expected):
        return "complete", "✓"
    if found > 0:
        return "partial", "⚠"
    return "missing", "✗"


def process_hymn(index, name, sources, skip_wav=False):
    """Process a single hymn through the full pipeline."""
    config = sources.get(name)
    if not config:
        print(f"  MISSING SOURCE: {name}")
        return False

    url = config.get("url")
    if not url or url == "MISSING":
        print(f"  MISSING SOURCE: {name}")
        return False

    folder = hymn_folder(index, name)
    folder.mkdir(parents=True, exist_ok=True)

    cache_path = CACHE_DIR / f"{slugify(name)}_source.mid"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not download_midi(url, cache_path):
        return False

    print("  Splitting MIDI into sections...")
    midi_files = split_midi(cache_path, config, folder)
    if not midi_files:
        print("  ERROR: MIDI splitting failed")
        return False

    print("  Converting to MusicXML...")
    for section in SECTIONS:
        midi_path = folder / f"{section}.mid"
        xml_path = folder / f"{section}.musicxml"
        if midi_path.exists():
            midi_to_musicxml(midi_path, xml_path)

    if skip_wav:
        print("  Skipping WAV generation (--skip-wav)")
    else:
        print("  Rendering WAV files...")
        for section in SECTIONS:
            midi_path = folder / f"{section}.mid"
            wav_path = folder / f"{section}.wav"
            if midi_path.exists():
                midi_to_wav(midi_path, wav_path)

    return True


def list_hymns(hymns, sources, skip_wav=False):
    """Print status of all hymns."""
    print(f"\n{'#':>3}  {'Status':^8}  Hymn")
    print(f"{'':->3}  {'':->8}  {'':->40}")

    for i, name in enumerate(hymns, 1):
        if name not in sources:
            symbol = "✗"
        else:
            folder = hymn_folder(i, name)
            if not folder.exists():
                symbol = "○"
            else:
                _, symbol = check_hymn_status(i, name, sources, skip_wav)
        print(f"{i:>3}  {symbol:^8}  {name}")

    in_sources = sum(1 for hymn in hymns if hymn in sources)
    print(f"\n{in_sources}/{len(hymns)} hymns have source URLs configured")


def main():
    parser = argparse.ArgumentParser(description="Absent Pianist - Hymn Library Generator")
    parser.add_argument("hymn", nargs="?", default=None, help="Process a single hymn by name (default: all)")
    parser.add_argument("--skip-wav", action="store_true", help="Generate MIDI and MusicXML only, skip WAV rendering")
    parser.add_argument("--list", action="store_true", dest="list_hymns", help="Show all hymns and their processing status")
    args = parser.parse_args()

    hymns = load_hymns()
    sources = load_sources()

    if args.list_hymns:
        list_hymns(hymns, sources, args.skip_wav)
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.hymn:
        matches = [hymn for hymn in hymns if hymn.lower() == args.hymn.lower()]
        if not matches:
            matches = [hymn for hymn in hymns if args.hymn.lower() in hymn.lower()]

        if not matches:
            print(f"ERROR: Hymn '{args.hymn}' not found in hymns.txt")
            sys.exit(1)

        for name in matches:
            index = hymns.index(name) + 1
            print(f"\nProcessing {index}/{len(hymns)}: {name}")
            process_hymn(index, name, sources, args.skip_wav)
    else:
        loop_count = 0
        while True:
            loop_count += 1
            print(f"\n{'='*60}")
            print(f"LOOP #{loop_count} — Starting continuous generation pass")
            print(f"{'='*60}")

            success = 0
            skipped = 0
            failed = 0

            for i, name in enumerate(hymns, 1):
                print(f"\nProcessing {i}/{len(hymns)}: {name}")
                if name not in sources or sources.get(name, {}).get("url") == "MISSING":
                    print(f"  MISSING SOURCE: {name}")
                    skipped += 1
                    continue

                if process_hymn(i, name, sources, args.skip_wav):
                    success += 1
                else:
                    failed += 1

            print(f"\n{'='*50}")
            print(f"Loop #{loop_count} complete — Success: {success}  Skipped: {skipped}  Failed: {failed}")
            print(f"Total: {len(hymns)} hymns")
            print(f"\nLooping back to start... Press Ctrl+C to stop.")


if __name__ == "__main__":
    main()
