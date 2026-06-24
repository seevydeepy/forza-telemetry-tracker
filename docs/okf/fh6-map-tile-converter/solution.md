# FH6 Map Tile Converter

## Purpose

Windows-only .NET CLI that inspects and converts FH6 `.swatchbin` map tile archives into PNG tile folders plus a JSON manifest for the local world-map cache.

## Owned Paths

- tools/fh6-map-tile-converter/

## Entrypoints

- `tools/fh6-map-tile-converter/Program.cs` exposes `forza-map-tile-converter inspect-zip --input <Map_Brio_Season.zip>` for archive inspection.
- `tools/fh6-map-tile-converter/Program.cs` exposes `forza-map-tile-converter convert-zip --input <Map_Brio_Season.zip> --output <dir> --format png --manifest <manifest.json>` for cache generation.
- `tools/fh6-map-tile-converter/ForzaTelemetryTracker.FH6MapTileConverter.csproj` builds the `forza-map-tile-converter` executable for `net9.0-windows`.

## Neighbouring Systems

- Desktop backend world-map cache code locates the converter executable and serves generated tile sets.
- Desktop release packaging publishes the converter into `bin/map-converter/` and smoke tests assert it is present.
- Web dashboard world-map overlay consumes the tile-set manifest and PNG tile URLs; it should not parse `.swatchbin` files directly.
- Third-party notices cover the vendored ForzaTechStudio parsing code under this solution.

## Maintenance Notes

- Tile archive entries must be named `<z>-<row>-<column>.swatchbin`; the converter emits manifest paths as `<z>/<x>/<y>.png` using `fh6-row-column-v1`.
- The PNG path supports PC swatchbins and rejects Durango/Xbox tiled swatchbins.
- BCn formats are decoded through `BCnEncoder.Net`; uncompressed RGBA/BGRA paths are handled locally.
- Keep changes inside `tools/fh6-map-tile-converter/` unless the backend, packaging, or web manifest contract also changes.
