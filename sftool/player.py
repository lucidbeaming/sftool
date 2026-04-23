"""FluidSynth audio player wrapper."""
import threading
from typing import Optional


class Player:
    """Wraps FluidSynth for soundfont loading and note playback."""

    CHANNEL = 0

    def __init__(self):
        import fluidsynth
        self._fs = fluidsynth.Synth(gain=0.8)
        self._started = False
        self._sfid: Optional[int] = None
        self._lock = threading.Lock()
        self._active_notes: set[int] = set()
        self._start_audio()

    def _start_audio(self) -> None:
        """Start audio output, trying common drivers in order."""
        import sys
        drivers = {
            'darwin': ['coreaudio', 'portaudio'],
            'win32':  ['dsound', 'portaudio'],
        }.get(sys.platform, ['pulseaudio', 'alsa', 'jack', 'portaudio'])

        for driver in drivers:
            try:
                self._fs.start(driver=driver)
                self._started = True
                return
            except Exception:
                continue

        # Last resort: no explicit driver (let FluidSynth decide)
        try:
            self._fs.start()
            self._started = True
        except Exception as e:
            raise RuntimeError(
                f'Could not start audio driver. '
                f'Make sure FluidSynth is installed.\n{e}'
            ) from e

    # ------------------------------------------------------------------
    # Soundfont management
    # ------------------------------------------------------------------

    def load(self, path: str) -> None:
        """Load an SF2 file, unloading any previously loaded soundfont."""
        with self._lock:
            self.all_notes_off()
            if self._sfid is not None:
                self._fs.sfunload(self._sfid, update_midi_preset=True)
            self._sfid = self._fs.sfload(path)
            if self._sfid == -1:
                self._sfid = None
                raise RuntimeError(f'FluidSynth could not load: {path}')

    def select(self, bank: int, preset: int) -> None:
        """Select an instrument by bank and preset number."""
        if self._sfid is None:
            return
        self._fs.program_select(self.CHANNEL, self._sfid, bank, preset)

    # ------------------------------------------------------------------
    # Note playback
    # ------------------------------------------------------------------

    def note_on(self, note: int, velocity: int = 80) -> None:
        with self._lock:
            if note not in self._active_notes:
                self._fs.noteon(self.CHANNEL, note, velocity)
                self._active_notes.add(note)

    def note_off(self, note: int) -> None:
        with self._lock:
            if note in self._active_notes:
                self._fs.noteoff(self.CHANNEL, note)
                self._active_notes.discard(note)

    def all_notes_off(self) -> None:
        with self._lock:
            for note in list(self._active_notes):
                self._fs.noteoff(self.CHANNEL, note)
            self._active_notes.clear()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        self.all_notes_off()
        try:
            self._fs.delete()
        except Exception:
            pass
