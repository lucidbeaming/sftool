"""
Terminal UI for SFTool — curses-based soundfont browser and preview.

Piano key bindings (QWERTY layout, one octave):
    [w][e]   [t][y][u]
  [a][s][d][f][g][h][j][k]

  z = octave down  x = octave up
  , = velocity -5  . = velocity +5
"""
import curses
import sys
import threading
from pathlib import Path
from typing import Optional

from .sf2 import read_presets, Preset
from .player import Player

# ── Piano key → semitone ─────────────────────────────────────────────────────
# One octave: a=C  w=C#  s=D  e=D#  d=E  f=F  t=F#  g=G  y=G#  h=A  u=A#  j=B
# k = high C (semitone 12, next octave)
NOTE_KEYS: list[tuple[str, int]] = [
    ('a',  0), ('w',  1), ('s',  2), ('e',  3),
    ('d',  4), ('f',  5), ('t',  6), ('g',  7),
    ('y',  8), ('h',  9), ('u', 10), ('j', 11),
    ('k', 12),
]
KEY_TO_SEMI = {ch: s for ch, s in NOTE_KEYS}

# Which keyboard chars are "black keys"
BLACK_CHARS = {'w', 'e', 't', 'y', 'u'}

NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B']

# White key semitones within an octave: C D E F G A B
WHITE_SEMIS = [0, 2, 4, 5, 7, 9, 11]
# Black key: white-key index → semitone  (C→C#, D→D#, F→F#, G→G#, A→A#)
BLACK_GAPS  = {0: 1, 1: 3, 3: 6, 4: 8, 5: 10}

# ── Color pair IDs ───────────────────────────────────────────────────────────
C_TITLE = 1   # cyan bold
C_SEL   = 2   # black on cyan — selected row
C_ACT   = 3   # green bold — active note
C_DIM   = 4   # dim white
C_NAME  = 5   # magenta bold — instrument name
C_WK    = 6   # white on blue — piano white key
C_BK    = 7   # black on white — piano black key
C_BDR   = 8   # bold white — borders
C_WARN  = 9   # yellow — values (octave, velocity)
C_FILT  = 10  # black on yellow — filter bar


# ── Tiny drawing helpers ──────────────────────────────────────────────────────

def _put(win, y, x, text, attr=0):
    """addstr that silently ignores any out-of-bounds write."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    try:
        win.addstr(y, x, text[:w - x], attr)
    except curses.error:
        pass


def _hline(win, y, x, ch, n, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0:
        return
    try:
        # addstr, not hline: hline() only takes single-byte characters, and '─' isn't one
        win.addstr(y, x, ch * min(n, w - x), attr)
    except curses.error:
        pass


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ── TUI ──────────────────────────────────────────────────────────────────────

class TUI:
    NOTE_DURATION = 0.45   # seconds a keyboard-triggered note rings

    def __init__(self, sf_path: Optional[str] = None):
        self.sf_path     = sf_path
        self.player: Optional[Player] = None
        self.presets: list[Preset] = []
        self.filtered: list[Preset] = []
        self.selected    = 0
        self.scroll      = 0
        self.octave      = 4
        self.velocity    = 80
        self.filter_text = ''
        self.filter_mode = False
        self._active: set[int] = set()
        self._timers: dict[int, threading.Timer] = {}
        self._lock  = threading.Lock()
        self.status = ''
        self.error  = ''

    # ── Entry ─────────────────────────────────────────────────────────────────

    def run(self) -> None:
        curses.wrapper(self._main)

    def _main(self, stdscr: curses.window) -> None:
        self._init_colors()
        curses.curs_set(0)
        stdscr.timeout(40)   # 40 ms ≈ 25 fps
        self.stdscr = stdscr

        try:
            self.player = Player()
        except Exception as e:
            self.error = f'Audio init failed: {e}'

        if self.sf_path:
            self._load(self.sf_path)

        while True:
            try:
                self._draw(stdscr)
            except curses.error:
                pass
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                stdscr.clear()
                continue
            if key == -1:
                continue
            if not self._handle(key):
                break

        if self.player:
            self.player.cleanup()

    def _init_colors(self) -> None:
        curses.start_color()
        curses.use_default_colors()
        bg = -1
        curses.init_pair(C_TITLE, curses.COLOR_CYAN,    bg)
        curses.init_pair(C_SEL,   curses.COLOR_BLACK,   curses.COLOR_CYAN)
        curses.init_pair(C_ACT,   curses.COLOR_GREEN,   bg)
        curses.init_pair(C_DIM,   curses.COLOR_WHITE,   bg)
        curses.init_pair(C_NAME,  curses.COLOR_MAGENTA, bg)
        curses.init_pair(C_WK,    curses.COLOR_WHITE,   curses.COLOR_BLUE)
        curses.init_pair(C_BK,    curses.COLOR_BLACK,   curses.COLOR_WHITE)
        curses.init_pair(C_BDR,   curses.COLOR_WHITE,   bg)
        curses.init_pair(C_WARN,  curses.COLOR_YELLOW,  bg)
        curses.init_pair(C_FILT,  curses.COLOR_BLACK,   curses.COLOR_YELLOW)

    # ── Soundfont loading ─────────────────────────────────────────────────────

    def _load(self, path: str) -> None:
        if not self.player:
            return
        try:
            self.player.load(path)
            self.presets  = read_presets(path)
            self.sf_path  = path
            self._apply_filter()
            self.selected = 0
            self.scroll   = 0
            n = len(self.presets)
            self.status   = f'{Path(path).name}  ({n} preset{"s" if n != 1 else ""})'
            self.error    = ''
            if self.filtered:
                p = self.filtered[0]
                self.player.select(p.bank, p.number)
        except Exception as e:
            self.error = str(e)

    def _apply_filter(self) -> None:
        q = self.filter_text.lower()
        self.filtered = (
            self.presets if not q
            else [p for p in self.presets if q in p.name.lower()]
        )
        self.selected = _clamp(self.selected, 0, max(0, len(self.filtered) - 1))

    def _select(self, idx: int) -> None:
        if not self.filtered or not self.player:
            return
        self.selected = _clamp(idx, 0, len(self.filtered) - 1)
        p = self.filtered[self.selected]
        self.player.select(p.bank, p.number)
        self.player.all_notes_off()
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()
            self._active.clear()

    # ── Note playback ─────────────────────────────────────────────────────────

    def _play(self, ch: str) -> None:
        if self.player is None or ch not in KEY_TO_SEMI:
            return
        semi = KEY_TO_SEMI[ch]
        if semi == 12:
            note = (self.octave + 2) * 12
        else:
            note = (self.octave + 1) * 12 + semi
        note = _clamp(note, 0, 127)

        with self._lock:
            if note in self._timers:
                self._timers[note].cancel()
            self.player.note_on(note, self.velocity)
            self._active.add(note)

        def _off():
            with self._lock:
                self.player.note_off(note)
                self._active.discard(note)
                self._timers.pop(note, None)

        t = threading.Timer(self.NOTE_DURATION, _off)
        t.daemon = True
        t.start()
        with self._lock:
            self._timers[note] = t

    # ── Key handling ──────────────────────────────────────────────────────────

    def _handle(self, key: int) -> bool:
        """Return False to quit."""
        ch = chr(key) if 0 < key < 128 else ''

        # Filter mode: typing narrows the instrument list
        if self.filter_mode:
            if key in (27,):                            # Esc: exit & clear
                self.filter_mode = False
                self.filter_text = ''
                self._apply_filter()
                curses.curs_set(0)
            elif key in (curses.KEY_ENTER, 10, 13):    # Enter: confirm
                self.filter_mode = False
                curses.curs_set(0)
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                self.filter_text = self.filter_text[:-1]
                self._apply_filter()
            elif ch and ch.isprintable():
                self.filter_text += ch
                self._apply_filter()
            return True

        # Quit
        if ch in ('q', 'Q'):
            return False

        # Open file
        if ch in ('o', 'O'):
            self._prompt_open()
            return True

        # Filter
        if ch == '/':
            self.filter_mode = True
            curses.curs_set(1)
            return True

        # Octave
        if ch == 'z':
            self.octave = _clamp(self.octave - 1, 0, 7)
            return True
        if ch == 'x':
            self.octave = _clamp(self.octave + 1, 0, 7)
            return True

        # Velocity
        if ch == ',':
            self.velocity = _clamp(self.velocity - 5, 1, 127)
            return True
        if ch == '.':
            self.velocity = _clamp(self.velocity + 5, 1, 127)
            return True

        # List navigation (arrow keys only; letter keys go to piano)
        if key == curses.KEY_UP:
            self._select(self.selected - 1)
            return True
        if key == curses.KEY_DOWN:
            self._select(self.selected + 1)
            return True
        if key == curses.KEY_PPAGE:
            self._select(self.selected - 10)
            return True
        if key == curses.KEY_NPAGE:
            self._select(self.selected + 10)
            return True
        if key == curses.KEY_HOME:
            self._select(0)
            return True
        if key == curses.KEY_END:
            self._select(len(self.filtered) - 1)
            return True

        # Piano keys
        if ch in KEY_TO_SEMI:
            self._play(ch)
            return True

        return True

    def _prompt_open(self) -> None:
        h, w = self.stdscr.getmaxyx()
        prompt = ' Open SF2: '
        curses.curs_set(1)
        curses.echo()
        _put(self.stdscr, h - 1, 0,
             (prompt + ' ' * w)[:w],
             curses.color_pair(C_FILT) | curses.A_BOLD)
        self.stdscr.move(h - 1, len(prompt))
        self.stdscr.refresh()
        try:
            raw  = self.stdscr.getstr(h - 1, len(prompt), w - len(prompt) - 2)
            path = raw.decode().strip()
            if path:
                self._load(path)
        except Exception:
            pass
        finally:
            curses.noecho()
            curses.curs_set(0)

    # ── Top-level draw ────────────────────────────────────────────────────────

    def _draw(self, stdscr: curses.window) -> None:
        h, w = stdscr.getmaxyx()
        if h < 14 or w < 52:
            stdscr.erase()
            _put(stdscr, 0, 0, 'Terminal too small — please resize')
            stdscr.refresh()
            return

        stdscr.erase()

        split = min(34, w // 3)     # left panel width
        rw    = w - split - 1       # right panel usable width

        self._draw_header(stdscr, w)
        self._draw_list(stdscr,  y0=1, x0=0,         rows=h - 2, cols=split)
        self._draw_vbar(stdscr,  y0=1, x=split,       rows=h - 2)
        self._draw_right(stdscr, y0=1, x0=split + 1,  rows=h - 2, cols=rw)
        self._draw_status(stdscr, h - 1, w)

        stdscr.refresh()

    # ── Header ────────────────────────────────────────────────────────────────

    def _draw_header(self, win, w: int) -> None:
        left  = ' ♪ SFTool '
        right = ' [O]Open  [/]Filter  [↑↓]Navigate  [z/x]Oct  [,/.]Vel  [Q]Quit '
        pad   = '─' * max(0, w - len(left) - len(right))
        bar   = (left + pad + right)[:w]
        _put(win, 0, 0, bar, curses.color_pair(C_TITLE) | curses.A_BOLD)

    # ── Instrument list ───────────────────────────────────────────────────────

    def _draw_list(self, win, y0, x0, rows, cols) -> None:
        total   = len(self.presets)
        visible = len(self.filtered)
        hdr     = f' Instruments {visible}/{total} '
        _put(win, y0, x0, hdr.ljust(cols)[:cols],
             curses.color_pair(C_BDR) | curses.A_BOLD)

        body_rows = rows - 2   # one for header, one for filter bar

        # Scroll: keep selected visible
        if self.selected < self.scroll:
            self.scroll = self.selected
        elif self.selected >= self.scroll + body_rows:
            self.scroll = self.selected - body_rows + 1

        for i in range(body_rows):
            idx = self.scroll + i
            row = y0 + 1 + i
            if idx >= len(self.filtered):
                _put(win, row, x0, ' ' * cols)
                continue
            p    = self.filtered[idx]
            line = f' {p.bank:3d}:{p.number:<3d}  {p.name}'
            line = line.ljust(cols)[:cols]
            attr = (curses.color_pair(C_SEL) | curses.A_BOLD
                    if idx == self.selected
                    else curses.color_pair(C_DIM))
            _put(win, row, x0, line, attr)

        # Filter bar
        frow = y0 + rows - 1
        if self.filter_mode:
            bar  = f' /{self.filter_text}_'
            attr = curses.color_pair(C_FILT) | curses.A_BOLD
        elif self.filter_text:
            bar  = f' /{self.filter_text}  (Esc clears)'
            attr = curses.color_pair(C_WARN)
        else:
            bar  = ' [/] filter'
            attr = curses.color_pair(C_DIM) | curses.A_DIM
        _put(win, frow, x0, bar.ljust(cols)[:cols], attr)

    # ── Vertical divider ──────────────────────────────────────────────────────

    def _draw_vbar(self, win, y0, x, rows) -> None:
        attr = curses.color_pair(C_BDR)
        for r in range(rows):
            _put(win, y0 + r, x, '│', attr)

    # ── Right panel ───────────────────────────────────────────────────────────

    def _draw_right(self, win, y0, x0, rows, cols) -> None:
        cx, cy = x0 + 1, y0

        # Instrument name
        if self.filtered and self.selected < len(self.filtered):
            p    = self.filtered[self.selected]
            name = f' ♪  {p.name}'
            meta = f' Bank {p.bank}  Preset {p.number} '
            _put(win, cy, cx, name, curses.color_pair(C_NAME) | curses.A_BOLD)
            _put(win, cy, x0 + cols - len(meta), meta, curses.color_pair(C_DIM))
        else:
            _put(win, cy, cx, ' No soundfont — press [O] to open',
                 curses.color_pair(C_DIM) | curses.A_DIM)
        cy += 1

        # Separator
        _hline(win, cy, x0, '─', cols, curses.color_pair(C_BDR))
        cy += 1

        # Octave / velocity row
        _put(win, cy, cx, 'Octave: ', curses.color_pair(C_DIM))
        _put(win, cy, cx + 8, str(self.octave),
             curses.color_pair(C_WARN) | curses.A_BOLD)
        _put(win, cy, cx + 10, ' [z]▼ [x]▲    Velocity: ',
             curses.color_pair(C_DIM) | curses.A_DIM)
        vx = cx + 34
        _put(win, cy, vx, str(self.velocity),
             curses.color_pair(C_WARN) | curses.A_BOLD)
        _put(win, cy, vx + 3, ' [,]▼ [.]▲',
             curses.color_pair(C_DIM) | curses.A_DIM)
        cy += 2

        # Piano
        cy = self._draw_piano(win, cy, cx, cols - 2)
        cy += 1

        # Key hints
        self._draw_hints(win, cy, cx, cols - 2)

    # ── ASCII piano keyboard ──────────────────────────────────────────────────
    #
    #  WW = 4 chars per white key (3 body + 1 border)
    #  Total width: 7 * 4 + 1 = 29 chars
    #
    #  ┌───┬───┬───┬───┬───┬───┬───┐
    #  │   ░░  ░░  │   ░░  ░░  ░░  │   ← rows 1-2: black key overlays
    #  │   ░░  ░░  │   ░░  ░░  ░░  │
    #  │   │   │   │   │   │   │   │   ← row 3: gap below black keys
    #  │ C │ D │ E │ F │ G │ A │ B │   ← row 4: note names
    #  └───┴───┴───┴───┴───┴───┴───┘

    WW = 4   # white key width in chars (body + right border)

    def _draw_piano(self, win, y: int, x: int, max_w: int) -> int:
        WW      = self.WW
        WHITES  = 7
        piano_w = WHITES * WW + 1   # 29

        if max_w < piano_w:
            return y

        with self._lock:
            active = set(self._active)

        base = (self.octave + 1) * 12   # MIDI note for C of current octave

        def note(semi):
            return base + semi

        b  = curses.color_pair(C_BDR)
        wn = curses.color_pair(C_WK)
        wa = curses.color_pair(C_ACT) | curses.A_BOLD | curses.A_REVERSE
        bn = curses.color_pair(C_BK)
        ba = curses.color_pair(C_ACT) | curses.A_BOLD

        def wattr(semi):
            return wa if note(semi) in active else wn

        def battr(semi):
            return ba if note(semi) in active else bn

        # Top border
        top = '┌' + '───┬' * (WHITES - 1) + '───┐'
        _put(win, y, x, top, b)

        # Rows 1-4: key bodies
        for row in range(1, 5):
            # Left border
            _put(win, y + row, x, '│', b)
            # White key cells
            for wi, semi in enumerate(WHITE_SEMIS):
                kx    = x + wi * WW + 1
                press = note(semi) in active
                fill  = '▓▓▓' if press else '   '
                _put(win, y + row, kx, fill, wattr(semi))
                _put(win, y + row, x + (wi + 1) * WW, '│', b)
            # Black key overlays (rows 1-2 only; row 3 shows gap, row 4 note names)
            if row <= 2:
                for wi, bsemi in BLACK_GAPS.items():
                    bx = x + wi * WW + WW - 1   # overlaps last char of white + border
                    fill = '▒▒' if note(bsemi) in active else '░░'
                    _put(win, y + row, bx, fill, battr(bsemi))
            elif row == 4:
                # Re-draw note names on top of the white key fill
                for wi, semi in enumerate(WHITE_SEMIS):
                    kx   = x + wi * WW + 1
                    name = NOTE_NAMES[semi]
                    _put(win, y + row, kx, f'{name:<3}', wattr(semi))

        # Bottom border
        bot = '└' + '───┴' * (WHITES - 1) + '───┘'
        _put(win, y + 5, x, bot, b)

        # Octave label to the right
        _put(win, y + 2, x + piano_w + 1, f'oct {self.octave}',
             curses.color_pair(C_WARN) | curses.A_BOLD)

        return y + 6

    # ── Key hints ─────────────────────────────────────────────────────────────
    #
    #    [w] [e]       [t] [y] [u]
    #  [a] [s] [d]  [f] [g] [h] [j] [k]

    def _draw_hints(self, win, y: int, x: int, max_w: int) -> None:
        with self._lock:
            active = set(self._active)

        base = (self.octave + 1) * 12

        def attr(ch):
            semi = KEY_TO_SEMI.get(ch, -1)
            if semi < 0:
                return curses.color_pair(C_DIM) | curses.A_DIM
            note = base + semi if semi < 12 else base + 12
            if note in active:
                return curses.color_pair(C_ACT) | curses.A_BOLD
            if ch in BLACK_CHARS:
                return curses.color_pair(C_DIM)
            return curses.color_pair(C_DIM)

        # Black-key row (offset 2 chars to sit above the gaps)
        BLACK_ROW = ['w', 'e', ' ', 't', 'y', 'u']
        bx = x + 2
        for ch in BLACK_ROW:
            if ch == ' ':
                bx += self.WW
            else:
                _put(win, y, bx, f'[{ch}]', attr(ch))
                bx += self.WW

        # White-key row
        WHITE_ROW = ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k']
        wx = x
        for ch in WHITE_ROW:
            _put(win, y + 1, wx, f'[{ch}]', attr(ch))
            wx += self.WW

        _put(win, y + 1, wx + 1, ' z/x=oct  ,/.=vel',
             curses.color_pair(C_DIM) | curses.A_DIM)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _draw_status(self, win, y: int, w: int) -> None:
        if self.error:
            msg  = f' ✗  {self.error}'
            attr = curses.color_pair(C_WARN) | curses.A_BOLD
        elif self.status:
            msg  = f'    {self.status}'
            attr = curses.color_pair(C_DIM)
        else:
            msg  = '    Ready — open a soundfont with [O]'
            attr = curses.color_pair(C_DIM) | curses.A_DIM
        _put(win, y, 0, msg.ljust(w)[:w], attr)


# ── Module entry ──────────────────────────────────────────────────────────────

def main(sf_path: Optional[str] = None) -> None:
    TUI(sf_path=sf_path).run()


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else None
    main(path)
