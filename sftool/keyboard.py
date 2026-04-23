"""Interactive piano keyboard widget built on tkinter Canvas."""
import tkinter as tk
from typing import Callable, Optional

# Semitone offsets within an octave for white keys (C D E F G A B)
WHITE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# For each black key semitone: index of the white key immediately to its left
BLACK_KEY_MAP = {1: 0, 3: 1, 6: 3, 8: 4, 10: 5}

WHITE_W = 30
WHITE_H = 130
BLACK_W = 19
BLACK_H = 82

# Colours
WHITE_NORMAL  = '#fafafa'
WHITE_PRESSED = '#b8d4f8'
WHITE_BORDER  = '#aaaaaa'
BLACK_NORMAL  = '#1e1e1e'
BLACK_PRESSED = '#4a6fa5'
BLACK_BORDER  = '#000000'
LABEL_COLOR   = '#555555'


class PianoKeyboard(tk.Canvas):
    """
    A clickable piano keyboard spanning `num_octaves` octaves starting at
    `base_octave`.  Mouse press/release/drag triggers `on_note_on` /
    `on_note_off` callbacks with the MIDI note number.
    """

    def __init__(
        self,
        parent,
        on_note_on: Callable[[int], None],
        on_note_off: Callable[[int], None],
        num_octaves: int = 3,
        base_octave: int = 4,
        **kwargs,
    ):
        num_white = 7 * num_octaves
        width  = num_white * WHITE_W + 1
        height = WHITE_H + 18   # extra space for octave labels

        super().__init__(
            parent,
            width=width,
            height=height,
            bg='#2b2b2b',
            highlightthickness=0,
            **kwargs,
        )

        self.on_note_on  = on_note_on
        self.on_note_off = on_note_off
        self.num_octaves = num_octaves
        self.base_octave = base_octave

        self._item_to_note: dict[int, int] = {}
        self._note_to_item: dict[int, int] = {}
        self._pressed: set[int] = set()
        self._drag_note: Optional[int] = None

        self._draw()

        self.bind('<ButtonPress-1>',   self._on_press)
        self.bind('<ButtonRelease-1>', self._on_release)
        self.bind('<B1-Motion>',       self._on_drag)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_base_octave(self, octave: int) -> None:
        self.base_octave = max(0, min(8, octave))
        self._draw()

    def release_all(self) -> None:
        """Visually release all pressed keys (call after all_notes_off)."""
        for note in list(self._pressed):
            self._set_key_color(note, pressed=False)
        self._pressed.clear()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _midi(self, octave: int, semitone: int) -> int:
        return (octave + 1) * 12 + semitone

    def _draw(self) -> None:
        self.delete('all')
        self._item_to_note.clear()
        self._note_to_item.clear()
        self._pressed.clear()

        # White keys
        for oct_i in range(self.num_octaves):
            octave = self.base_octave + oct_i
            for wi, semitone in enumerate(WHITE_SEMITONES):
                x = (oct_i * 7 + wi) * WHITE_W
                note = self._midi(octave, semitone)
                item = self.create_rectangle(
                    x + 1, 1, x + WHITE_W - 1, WHITE_H,
                    fill=WHITE_NORMAL, outline=WHITE_BORDER,
                    tags='white_key',
                )
                self._item_to_note[item] = note
                self._note_to_item[note] = item

            # Octave label below the C key
            cx = oct_i * 7 * WHITE_W + WHITE_W // 2
            self.create_text(
                cx, WHITE_H + 9,
                text=f'C{octave}',
                font=('Helvetica', 8),
                fill=LABEL_COLOR,
            )

        # Black keys (drawn after so they sit on top)
        for oct_i in range(self.num_octaves):
            octave = self.base_octave + oct_i
            oct_x = oct_i * 7 * WHITE_W
            for semitone, white_left_idx in BLACK_KEY_MAP.items():
                note = self._midi(octave, semitone)
                x = oct_x + (white_left_idx + 1) * WHITE_W - BLACK_W // 2
                item = self.create_rectangle(
                    x, 1, x + BLACK_W, BLACK_H,
                    fill=BLACK_NORMAL, outline=BLACK_BORDER,
                    tags='black_key',
                )
                self._item_to_note[item] = note
                self._note_to_item[note] = item

    def _set_key_color(self, note: int, pressed: bool) -> None:
        item = self._note_to_item.get(note)
        if item is None:
            return
        is_black = 'black_key' in self.gettags(item)
        if is_black:
            color = BLACK_PRESSED if pressed else BLACK_NORMAL
        else:
            color = WHITE_PRESSED if pressed else WHITE_NORMAL
        self.itemconfig(item, fill=color)

    # ------------------------------------------------------------------
    # Hit testing — black keys take priority (they're drawn on top)
    # ------------------------------------------------------------------

    def _note_at(self, x: int, y: int) -> Optional[int]:
        # find_overlapping returns items back-to-front; last = topmost
        items = self.find_overlapping(x, y, x, y)
        for item in reversed(items):
            if item in self._item_to_note:
                return self._item_to_note[item]
        return None

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def _on_press(self, event) -> None:
        note = self._note_at(event.x, event.y)
        if note is not None:
            self._start_note(note)
        self._drag_note = note

    def _on_release(self, event) -> None:
        for note in list(self._pressed):
            self._stop_note(note)
        self._drag_note = None

    def _on_drag(self, event) -> None:
        note = self._note_at(event.x, event.y)
        if note == self._drag_note:
            return
        # Transition: release old, press new
        if self._drag_note is not None:
            self._stop_note(self._drag_note)
        if note is not None:
            self._start_note(note)
        self._drag_note = note

    def _start_note(self, note: int) -> None:
        if note not in self._pressed:
            self._pressed.add(note)
            self._set_key_color(note, pressed=True)
            self.on_note_on(note)

    def _stop_note(self, note: int) -> None:
        if note in self._pressed:
            self._pressed.discard(note)
            self._set_key_color(note, pressed=False)
            self.on_note_off(note)
