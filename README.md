# SFTool

A cross-platform soundfont (`.sf2`) browser and preview tool written in Python. Runs as a desktop GUI or a full-featured terminal UI.

## Features

- Load any SF2 soundfont and browse all presets by bank and number
- Filter instruments by name in real time
- Preview any instrument across octaves using an on-screen keyboard (GUI) or your computer keyboard (TUI)
- Adjust velocity and octave on the fly
- Auto-detects headless/SSH environments and falls back to TUI mode

## Requirements

- Python 3.11+
- [FluidSynth](https://www.fluidsynth.org/) (native library, installed separately)
- `pyfluidsynth` (Python binding, installed via pip)

### Install FluidSynth

**macOS**
```bash
brew install fluid-synth
```

**Ubuntu / Debian**
```bash
sudo apt install fluidsynth
```

**Fedora**
```bash
sudo dnf install fluidsynth
```

**Windows**
Download the installer from https://github.com/FluidSynth/fluidsynth/releases and add the `bin/` directory to your `PATH`.

### Install Python dependencies

```bash
pip install -r requirements.txt
```

## Usage

### GUI mode (default)

```bash
python main.py
python main.py path/to/file.sf2   # open a soundfont on launch
```

A tkinter window opens with a resizable instrument list on the left and an interactive piano keyboard on the right.

![GUI layout]
```
┌─ File ──────────────────────────────────────────────────────┐
│ Instruments  28/28    │  ♪ Modular Fat 1   Bank 0  Preset 0 │
│  Bank Preset Name     │─────────────────────────────────────│
│   0    0  Modular..   │  Octave ◀ 4 ▶   Velocity ──── 80   │
│   0    1  Modular..   │                                     │
│   0    2  Sync 2      │  [piano keyboard]                   │
│   ...                 │                                     │
└───────────────────────┴─────────────────────────────────────┘
```

**GUI controls:**

| Action | How |
|---|---|
| Open soundfont | File → Open Soundfont, or `Cmd/Ctrl+O` |
| Select instrument | Click a row in the list |
| Filter instruments | Type in the filter box above the list |
| Play a note | Click and hold a piano key |
| Slide between notes | Click and drag across keys |
| Change octave | `◀` / `▶` buttons |
| Adjust velocity | Drag the slider |
| Change octaves shown | 2 / 3 / 4 radio buttons |

### TUI mode (terminal)

```bash
python main.py --tui
python main.py --tui path/to/file.sf2
```

On systems without a display (SSH, headless servers) the TUI is selected automatically.

```
 ♪ SFTool ───────── [O]Open  [/]Filter  [↑↓]Navigate  [z/x]Oct  [,/.]Vel  [Q]Quit
 Instruments 28/28  │  ♪  Modular Fat 1                          Bank 0  Preset 0
  000:0  Modular F  │  ──────────────────────────────────────────────────────────
  000:1  Modular F  │  Octave: 4  [z]▼ [x]▲      Velocity: 80  [,]▼ [.]▲
  000:2  Sync 2     │
  000:3  Sync 3     │  ┌───┬───┬───┬───┬───┬───┬───┐  oct 4
  000:4  Synth 10   │  │   ░░  ░░  │   ░░  ░░  ░░  │
  000:5  Synth 14   │  │   ░░  ░░  │   ░░  ░░  ░░  │
  000:6  Bass 3     │  │   │   │   │   │   │   │   │
  000:7  Acid Bass  │  │ C │ D │ E │ F │ G │ A │ B │
                    │  └───┴───┴───┴───┴───┴───┴───┘
  [/] filter        │
                    │    [w] [e]       [t] [y] [u]
                    │  [a] [s] [d]  [f] [g] [h] [j] [k]   z/x=oct  ,/.=vel
 Loaded lucid.sf2  (28 presets)
```

**TUI controls:**

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate instrument list |
| `PgUp` / `PgDn` | Jump 10 instruments |
| `Home` / `End` | First / last instrument |
| `/` | Enter filter mode — type to narrow the list |
| `Esc` | Exit filter mode and clear the filter |
| `O` | Open a soundfont by typing its path |
| `z` / `x` | Octave down / up |
| `,` / `.` | Velocity −5 / +5 |
| `Q` | Quit |

**Piano keyboard layout:**

```
    [w] [e]       [t] [y] [u]
  [a] [s] [d]  [f] [g] [h] [j] [k]
   C  C#  D  D#  E   F  F#  G  G#  A  A#  B  C
```

Notes ring for ~0.45 seconds. Pressing a key while its note is still sounding restarts the envelope.

## Project structure

```
sftool/
├── main.py           Entry point — routes to GUI or TUI
├── requirements.txt
└── sftool/
    ├── sf2.py        Zero-dependency SF2 preset reader (parses PHDR chunk)
    ├── player.py     FluidSynth wrapper — loads SF2, plays/stops notes
    ├── keyboard.py   Clickable piano keyboard widget (tkinter Canvas)
    └── tui.py        Full-screen terminal UI (curses)
```

### Why no `sf2utils` dependency?

`sf2utils` dropped support for Python 3.13+ (it uses the removed `audioop` module). `sftool` ships a minimal PHDR-chunk parser in `sf2.py` that has no dependencies beyond the standard library and works on all Python versions.

## Troubleshooting

**`No module named 'fluidsynth'`** — run `pip install pyfluidsynth`.

**FluidSynth library not found on macOS** — make sure you ran `brew install fluid-synth`. The library should be at `/opt/homebrew/lib/libfluidsynth.dylib`. `main.py` adds this path to `DYLD_LIBRARY_PATH` automatically.

**No sound on Linux** — FluidSynth tries PulseAudio then ALSA. Check that your audio server is running: `pactl info` or `aplay -l`.

**TUI is garbled** — make sure your terminal emulator supports UTF-8 and 256 colours. Set `TERM=xterm-256color` if needed.

## License

MIT
