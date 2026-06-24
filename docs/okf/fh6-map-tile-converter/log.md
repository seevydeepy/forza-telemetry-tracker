# FH6 Map Tile Converter OKF Log

## Bootstrap

- Shallow OKF bundle created from repository structure.

## Deep Backfill

- `Program.cs` exposes two commands: `inspect-zip` serialises `.swatchbin` archive metadata, and `convert-zip` writes PNG tiles plus a manifest.
- `Program.cs` parses tile entry names as `<z>-<row>-<column>.swatchbin`, converts row/column into manifest `x`/`y`, and labels manifests with `fh6-row-column-v1`.
- `SwatchbinReader.cs` loads Forza bundle texture content blobs through the vendored ForzaTechStudio projects and records PC or Durango texture header metadata.
- `BcnPngWriter.cs` supports BC1/2/3/4/5/7 plus selected uncompressed DXGI formats, writes PNG output, and rejects Durango/Xbox tiled swatchbins.
- The project file targets `net9.0-windows`, names the executable `forza-map-tile-converter`, references vendored ForzaTechStudio projects, and uses `BCnEncoder.Net` plus `System.Drawing.Common`.
- Repository searches showed handoffs in contributor build/audit commands, desktop release publishing, desktop package smoke checks, backend converter path resolution, web world-map overlay consumption, and third-party notices.

## Known Gaps

- No sample FH6 map ZIP or golden manifest is documented in this solution bundle.
- The converter's source states Durango/Xbox tiled swatchbins are unsupported.
- Backend and web map-overlay behaviour should be validated in their own solution bundles when changing the manifest shape or served tile URLs.
