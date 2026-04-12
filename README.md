# Absent Pianist

A hymn library generator for small churches without a pianist. For each hymn in the library, this pipeline produces 9 files: intro, verse, and refrain in MIDI, MusicXML, and WAV formats.

All source material is fully public domain (pre-1925 tune, text, and arrangement).

## Install

```bash
pip install mido music21 requests --break-system-packages
sudo apt install fluidsynth
```

## Soundfont Setup

WAV rendering requires the Salamander Grand Piano soundfont.

1. Download from: https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html
2. Save as: `soundfont/Salamander.sf2`

Without the soundfont, MIDI and MusicXML files still generate — WAV is skipped with a clear message.

## Usage

```bash
# Process all 50 hymns
python generate.py

# Process a single hymn
python generate.py "Amazing Grace"

# Generate MIDI + MusicXML only (skip WAV)
python generate.py --skip-wav

# Show status of all hymns
python generate.py --list
```

## Adding a New Hymn

1. Add the hymn title to `hymns.txt` (one per line)
2. Add an entry to `hymn_sources.json`:

```json
{
  "My New Hymn": {
    "url": "https://example.com/path/to/hymn.mid",
    "source": "pateys",
    "verse_measures": [1, 16],
    "refrain_measures": [9, 16],
    "intro_measures": [1, 2]
  }
}
```

Set `refrain_measures` to `null` if the hymn has no distinct refrain — the script will use the second half of the piece as a fallback.

3. Run: `python generate.py "My New Hymn"`

## Output Structure

```
output/
  001_amazing_grace/
    intro.mid
    verse.mid
    refrain.mid
    intro.musicxml
    verse.musicxml
    refrain.musicxml
    intro.wav
    verse.wav
    refrain.wav
  002_holy_holy_holy/
    ...
```

## Hymn Sources

- Primary: https://www.pateys.nf.ca (370+ public domain hymns, Presbyterian Book of Praise)
- Fallback: https://www.kunstderfuge.com/hymns.htm (hymn MIDI arrangements by various arrangers)

26 of 50 hymns are pre-configured with source URLs. The remaining 24 print a `MISSING SOURCE` message and can be added as URLs are found.

## Status Symbols

| Symbol | Meaning |
|--------|---------|
| ✓ | Complete — all 9 files present |
| ⚠ | Partial — some files missing |
| ✗ | Missing — no source URL configured |
