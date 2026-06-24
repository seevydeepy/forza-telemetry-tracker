# FH6 Map Tile Converter Routing

## Read This When

- A change touches one of this solution's owned paths.
- A symptom matches one of this solution's routing keywords.

## First Files To Inspect

- `docs/okf/fh6-map-tile-converter/routing_guidance.card`
- `docs/okf/fh6-map-tile-converter/solution.md`
- `tools/fh6-map-tile-converter/Program.cs`
- `tools/fh6-map-tile-converter/Swatchbin/SwatchbinReader.cs`
- `tools/fh6-map-tile-converter/Swatchbin/BcnPngWriter.cs`
- `tools/fh6-map-tile-converter/ForzaTelemetryTracker.FH6MapTileConverter.csproj`

## Owned Paths

- tools/fh6-map-tile-converter/

## Symptoms And Search Terms

- map tile
- swatchbin
- forzatechstudio
- forza-map-tile-converter
- inspect-zip
- convert-zip
- Map_Brio_Season.zip
- tileCoordinateSystem
- fh6-row-column-v1
- DXGI
- BCn
- Durango
- world map cache
- texture
- converter

## Handoffs

- If the converter executable is missing, search desktop path resolution and packaging for `forza-map-tile-converter.exe` or `bin/map-converter`.
- If archive inspection or conversion fails, start in `Program.cs`, then `SwatchbinReader.cs` for bundle/TXCB/TXCH parsing or `BcnPngWriter.cs` for format support.
- If generated tiles exist but the overlay is wrong, hand off to the desktop backend and web-dashboard world-map paths after checking the manifest fields and coordinate system here.
- If release packaging fails, hand off to `tools/build-desktop-release.ps1` and desktop package smoke tests after confirming this project publishes successfully.
- If vendored parser code changes, update third-party notice evidence alongside the converter change.

## Known Gaps

- No fixture archive is documented in this bundle, so behaviour claims should be backed by a real FH6 map ZIP or existing backend/web tests.
- Durango/Xbox tiled swatchbins are explicitly unsupported by the PNG writer.
