# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- The TUI no longer crashes drawing the instrument panel: its rule used curses `hline()`, which can't take the `─` character (#7)
- Loading a soundfont no longer hangs the app: `Player.load()` re-acquired its own non-reentrant lock through `all_notes_off()` (#5)

### Added
- README: GUI screenshot and real TUI capture, clone command, Tk requirement note, a soundfont to try, related projects (#9)
- MIT license (#3)

### Changed
- `.gitignore` aligned with the portfolio's common block: logs, Windows thumbnails, shared `.vscode/extensions.json`; soundfont comment points at `examples/` (#1)
