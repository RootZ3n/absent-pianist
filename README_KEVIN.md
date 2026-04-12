# Absent Pianist — How to Use

This program generates piano accompaniment files for hymns so your
church can sing along even without a pianist.

## How to Start

1. Open a terminal (or double-click `start.sh`)
2. Go to: **http://localhost:5111** in your browser
3. That's it. Everything happens in the browser from here.

If `start.sh` doesn't work, you can also run:
```
cd /home/zen/absent-pianist
pip3 install flask
python3 app.py
```

## How to Use

When you open the page, you'll see a list of 50 hymns.

- **Generate All Hymns** (big red button at the top) — generates every
  hymn in the list. Takes a while. Good for first-time setup.

- **Generate** (button next to each hymn) — generates just that one
  hymn. Takes about 30 seconds per hymn.

- You'll see progress messages scrolling as it works. Wait for
  "Generation complete!" before downloading.

- Once a hymn is generated, download links appear next to it:
  - **intro.wav** — a slow, soft intro (first 2 measures)
  - **single.wav** — one full verse, normal speed
  - **refrain.wav** — the chorus/refrain section
  - **ZIP** — all files bundled together (MIDI, sheet music, and WAV)

## What the Files Are

Each hymn gets a folder in the `output/` directory with these files:

| File | What it is |
|------|-----------|
| `intro.wav` | Soft piano intro, slowed down. Play this while the congregation gets ready. |
| `single.wav` | One full verse at normal tempo. The main accompaniment. |
| `refrain.wav` | The chorus section. Play after each verse if the hymn has a distinct refrain. |
| `intro.mid` | Same as intro but as a MIDI file (for electronic keyboards). |
| `single.mid` | Full verse as MIDI. |
| `refrain.mid` | Chorus as MIDI. |
| `*.musicxml` | Sheet music files. Open in MuseScore or print them out. |
| `*.zip` | Everything in one download. |

## Tips

- You can copy the WAV files to a USB drive and play them on any computer,
  phone, or Bluetooth speaker.

- The intro is deliberately slower and quieter — it's meant to signal
  "we're about to start singing."

- If a hymn says "No MIDI source" it means we don't have the music data
  for that hymn yet. Let Zen know and he'll add it.

- You can drop files into the `output/` folder on a USB drive and play
  them directly at church.

## If Something Goes Wrong

- If a hymn fails to generate, try clicking "Generate" on just that
  hymn again. Sometimes downloads time out.

- If the page won't load, make sure the terminal is still running.
  The program stops when you close the terminal.

- If you see "FluidSynth not installed" — that's the program that
  makes the WAV audio files. Ask Zen to install it:
  `sudo apt install fluidsynth`

## What You Need

- Python 3 (already installed)
- Flask (installed automatically by `start.sh`)
- FluidSynth (for WAV files): `sudo apt install fluidsynth`
- The Salamander piano soundfont (already in the `soundfont/` folder)
