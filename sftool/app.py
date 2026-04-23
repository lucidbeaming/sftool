"""Main application window."""
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional

from .sf2 import read_presets, Preset
from .player import Player
from .keyboard import PianoKeyboard


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('SFTool')
        self.geometry('960x560')
        self.minsize(720, 460)

        self._player: Optional[Player] = None
        self._sf_path: Optional[str] = None
        self._presets: list[Preset] = []

        self._build_menu()
        self._build_ui()
        self._init_player()
        self.protocol('WM_DELETE_WINDOW', self._quit)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_player(self) -> None:
        try:
            self._player = Player()
        except Exception as e:
            messagebox.showerror(
                'Audio Error',
                f'Could not initialise FluidSynth audio:\n\n{e}\n\n'
                'Make sure FluidSynth is installed (e.g. brew install fluid-synth).',
            )

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        mod = 'Command' if sys.platform == 'darwin' else 'Control'
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(
            label='Open Soundfont…',
            command=self._open_sf,
            accelerator=f'{mod}+O',
        )
        file_menu.add_separator()
        file_menu.add_command(
            label='Quit',
            command=self._quit,
            accelerator=f'{mod}+Q',
        )
        menubar.add_cascade(label='File', menu=file_menu)
        self.config(menu=menubar)

        key = 'Command' if sys.platform == 'darwin' else 'Control'
        self.bind(f'<{key}-o>', lambda _e: self._open_sf())
        self.bind(f'<{key}-q>', lambda _e: self._quit())

    # ------------------------------------------------------------------
    # UI layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Status bar (packed first so it anchors to the bottom) ──
        self._status_var = tk.StringVar(value='No soundfont loaded — File → Open Soundfont…')
        status = ttk.Label(
            self,
            textvariable=self._status_var,
            relief=tk.SUNKEN,
            anchor='w',
            padding=(6, 2),
        )
        status.pack(side=tk.BOTTOM, fill=tk.X)

        # ── Main horizontal split ──
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── Left: instrument list ──
        left = ttk.Frame(paned, padding=2)
        paned.add(left, weight=1)
        self._build_instrument_panel(left)

        # ── Right: controls + keyboard ──
        right = ttk.Frame(paned, padding=2)
        paned.add(right, weight=3)
        self._build_keyboard_panel(right)

    def _build_instrument_panel(self, parent) -> None:
        ttk.Label(parent, text='Instruments', font=('Helvetica', 11, 'bold')).pack(
            anchor='w', padx=2, pady=(2, 4)
        )

        # Search bar
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(search_frame, text='Filter:').pack(side=tk.LEFT, padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add('write', lambda *_: self._filter_tree())
        ttk.Entry(search_frame, textvariable=self._search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        # Treeview
        cols = ('bank', 'preset', 'name')
        self._tree = ttk.Treeview(parent, columns=cols, show='headings', selectmode='browse')
        self._tree.heading('bank',   text='Bank',   anchor='center')
        self._tree.heading('preset', text='Preset', anchor='center')
        self._tree.heading('name',   text='Name',   anchor='w')
        self._tree.column('bank',   width=46,  minwidth=40,  anchor='center', stretch=False)
        self._tree.column('preset', width=52,  minwidth=48,  anchor='center', stretch=False)
        self._tree.column('name',   width=190, minwidth=100, anchor='w')

        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind('<<TreeviewSelect>>', self._on_tree_select)

    def _build_keyboard_panel(self, parent) -> None:
        # ── Controls row ──
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=tk.X, pady=(2, 8))

        # Octave
        ttk.Label(ctrl, text='Octave').pack(side=tk.LEFT)
        self._octave_var = tk.IntVar(value=4)
        ttk.Button(ctrl, text='◀', width=2, command=self._octave_down).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Label(ctrl, textvariable=self._octave_var, width=2, anchor='center').pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(ctrl, text='▶', width=2, command=self._octave_up).pack(
            side=tk.LEFT, padx=(0, 12)
        )

        # Velocity
        ttk.Label(ctrl, text='Velocity').pack(side=tk.LEFT)
        self._vel_var = tk.IntVar(value=80)
        ttk.Scale(
            ctrl, from_=1, to=127, variable=self._vel_var,
            orient=tk.HORIZONTAL, length=120,
        ).pack(side=tk.LEFT, padx=4)
        self._vel_label = ttk.Label(ctrl, text='80', width=3)
        self._vel_label.pack(side=tk.LEFT)
        self._vel_var.trace_add(
            'write',
            lambda *_: self._vel_label.config(text=str(self._vel_var.get())),
        )

        # Octave count
        ttk.Label(ctrl, text='  Octaves shown:').pack(side=tk.LEFT, padx=(16, 4))
        self._noct_var = tk.IntVar(value=3)
        for n in (2, 3, 4):
            ttk.Radiobutton(
                ctrl, text=str(n), variable=self._noct_var, value=n,
                command=self._rebuild_keyboard,
            ).pack(side=tk.LEFT)

        # ── Keyboard frame (scrollable horizontally for wider spans) ──
        kb_outer = ttk.Frame(parent)
        kb_outer.pack(fill=tk.BOTH, expand=True)

        self._kb_canvas = tk.Canvas(kb_outer, bg='#1e1e1e', highlightthickness=0)
        hsb = ttk.Scrollbar(kb_outer, orient=tk.HORIZONTAL, command=self._kb_canvas.xview)
        self._kb_canvas.configure(xscrollcommand=hsb.set)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._kb_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._kb_inner = ttk.Frame(self._kb_canvas)
        self._kb_window = self._kb_canvas.create_window(
            (0, 0), window=self._kb_inner, anchor='nw'
        )
        self._kb_inner.bind('<Configure>', self._on_kb_configure)

        self._keyboard: Optional[PianoKeyboard] = None
        self._rebuild_keyboard()

    def _rebuild_keyboard(self) -> None:
        if self._keyboard is not None:
            if self._player:
                self._player.all_notes_off()
            self._keyboard.destroy()

        self._keyboard = PianoKeyboard(
            self._kb_inner,
            on_note_on=self._note_on,
            on_note_off=self._note_off,
            num_octaves=self._noct_var.get(),
            base_octave=self._octave_var.get(),
        )
        self._keyboard.pack(padx=8, pady=8)

    def _on_kb_configure(self, _event) -> None:
        self._kb_canvas.configure(scrollregion=self._kb_canvas.bbox('all'))

    # ------------------------------------------------------------------
    # Soundfont loading
    # ------------------------------------------------------------------

    def _open_sf(self) -> None:
        path = filedialog.askopenfilename(
            title='Open Soundfont',
            filetypes=[('SoundFont 2', '*.sf2'), ('All files', '*.*')],
        )
        if path:
            self.load_soundfont(path)

    def load_soundfont(self, path: str) -> None:
        if self._player is None:
            return
        try:
            self._player.load(path)
        except Exception as e:
            messagebox.showerror('Load Error', f'Could not load soundfont:\n\n{e}')
            return

        self._sf_path = path
        try:
            self._presets = read_presets(path)
        except Exception as e:
            messagebox.showerror('Parse Error', f'Could not read presets:\n\n{e}')
            return

        self._populate_tree(self._presets)
        name = Path(path).name
        self._status_var.set(
            f'{name}  —  {len(self._presets)} preset{"s" if len(self._presets) != 1 else ""}'
        )
        # Auto-select the first instrument
        children = self._tree.get_children()
        if children:
            self._tree.selection_set(children[0])
            self._tree.focus(children[0])
            self._tree.see(children[0])

    def _populate_tree(self, presets: list[Preset]) -> None:
        self._tree.delete(*self._tree.get_children())
        for p in presets:
            self._tree.insert('', 'end', iid=f'{p.bank}:{p.number}',
                              values=(p.bank, p.number, p.name))

    def _filter_tree(self) -> None:
        query = self._search_var.get().lower().strip()
        filtered = (
            self._presets if not query
            else [p for p in self._presets if query in p.name.lower()]
        )
        self._populate_tree(filtered)

    # ------------------------------------------------------------------
    # Instrument selection
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event) -> None:
        sel = self._tree.selection()
        if not sel or self._player is None:
            return
        values = self._tree.item(sel[0])['values']
        bank, preset_num, name = int(values[0]), int(values[1]), values[2]
        self._player.select(bank, preset_num)
        self._status_var.set(
            f'{Path(self._sf_path).name}  —  {name}  (bank {bank}, preset {preset_num})'
        )

    # ------------------------------------------------------------------
    # Octave navigation
    # ------------------------------------------------------------------

    def _octave_down(self) -> None:
        val = self._octave_var.get()
        if val > 0:
            self._octave_var.set(val - 1)
            if self._keyboard:
                self._keyboard.set_base_octave(val - 1)

    def _octave_up(self) -> None:
        val = self._octave_var.get()
        if val < 7:
            self._octave_var.set(val + 1)
            if self._keyboard:
                self._keyboard.set_base_octave(val + 1)

    # ------------------------------------------------------------------
    # Note playback
    # ------------------------------------------------------------------

    def _note_on(self, note: int) -> None:
        if self._player:
            self._player.note_on(note, velocity=self._vel_var.get())

    def _note_off(self, note: int) -> None:
        if self._player:
            self._player.note_off(note)

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _quit(self) -> None:
        if self._player:
            self._player.cleanup()
        self.destroy()
