# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Breaking:** look up titles on TMDb instead of IMDb. IMDb now blocks
  Cinemagoer, so lookups had stopped working. Set `TMDB_API_KEY` to a TMDb API
  key or read access token.
- Files with no confirmed TMDb match are skipped instead of renamed from the
  filename alone.
- Only video and subtitle files are renamed; samples and trailers are skipped.

### Fixed

- Renaming could overwrite an existing file when two files cleaned up to the
  same name.
- The extension was lost when the year came right before it (`Movie.2010.mkv`).
- Title matching was case-sensitive.
- Crash on Python 3.14 (no current event loop).

## [2.0.4] - 2025-06-13

### Fixed

- IMDb search and matching

## [2.0.3] - 2025-05-13

### Fixed

- Extraction

## [2.0.2] - 2025-05-13

### Added

- support for more patterns

## [2.0.1] - 2025-05-11

### Added

- support for more patterns

## [2.0.0] - 2025-05-11

### Added

- use imdb and fuzzy match for intelligent matching
- add --watch to make continuous watching optional
- support for more patterns

## [1.0.0] - 2025-05-04

### Added

- First release
- Ability to run fixer on a list of files in a directory
- Auto run when changes are detected in the directory

## [0.0.1] - 2025-04-30

### Added

- Stub release
