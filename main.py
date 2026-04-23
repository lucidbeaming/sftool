#!/usr/bin/env python3
"""
SFTool — soundfont browser and preview tool.

Usage:
  python main.py [file.sf2]          # GUI mode (default when display available)
  python main.py --tui [file.sf2]    # Terminal UI (ncurses)
  python main.py --tui               # Terminal UI, prompt to open file inside
"""
import sys
import os

# Let FluidSynth find its shared library on macOS (Homebrew Intel + Apple Silicon)
if sys.platform == 'darwin':
    for lib_dir in ('/opt/homebrew/lib', '/usr/local/lib'):
        if os.path.isdir(lib_dir):
            cur = os.environ.get('DYLD_LIBRARY_PATH', '')
            if lib_dir not in cur:
                os.environ['DYLD_LIBRARY_PATH'] = f'{lib_dir}:{cur}' if cur else lib_dir
            break


def _sf_arg() -> str | None:
    """Return the first .sf2 argument if present."""
    for arg in sys.argv[1:]:
        if not arg.startswith('--') and arg.endswith('.sf2'):
            return arg
    return None


def run_gui(sf_path: str | None = None) -> None:
    from sftool.app import App
    app = App()
    if sf_path:
        app.after(100, lambda: app.load_soundfont(sf_path))
    app.mainloop()


def run_tui(sf_path: str | None = None) -> None:
    from sftool.tui import TUI
    TUI(sf_path=sf_path).run()


def main() -> None:
    use_tui = '--tui' in sys.argv

    # Auto-fallback to TUI when no display is available (headless / SSH)
    if not use_tui and sys.platform != 'win32':
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            if sys.platform != 'darwin':   # macOS has no DISPLAY but always has a screen
                use_tui = True

    sf_path = _sf_arg()

    if use_tui:
        run_tui(sf_path)
    else:
        run_gui(sf_path)


if __name__ == '__main__':
    main()
