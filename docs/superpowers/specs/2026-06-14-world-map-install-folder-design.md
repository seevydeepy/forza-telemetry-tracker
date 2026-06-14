# World Map Install Folder Design

## Goal

The FH6 world map setup flow should ask for the top-level Forza Horizon 6 install folder, not the `media` folder, and both first-run setup and settings should use the same wording and behavior.

## UI

The first-run world map setup panel becomes a centered `AppModal` titled `World Map Setup`, matching existing modal windows. The setup text changes to "Link the tracker to your FH6 game install folder." The path input label changes to `FH6 Local Install Location`, and the placeholder becomes `e.g. C:\SteamLibrary\steamapps\common\ForzaHorizon6`.

The settings menu world-map controls get the same label, placeholder, install-folder wording, and help behavior so the duplicated controls do not drift.

The help affordance uses the existing Material `help` icon from `IconButton`. Pressing it opens a small popover near the cursor or focused button with these steps:

1. Start the game.
2. Open Task Manager.
3. Right click the FH6 process.
4. Click Open file location.

The popover ends with: "The folder that opens is the folder the tracker needs the filepath for to find the map assets."

## Backend

The existing API/storage field `fh6_media_root` stays in place for compatibility with the current schema and client types, but its semantics change to "configured FH6 install root." Backend world-map discovery resolves assets under `<configured root>\media`.

If the configured path itself points at a folder named `media`, the backend does not normalize it. It is treated as invalid input/source missing, per the approved requirement to reject direct media-folder paths.

## Validation

Frontend tests cover setup modal rendering, updated labels/copy/placeholder, help popover content, settings-menu parity, and unchanged request payload shape.

Backend tests cover install-root source discovery and rejection of a direct `media` folder path. Existing helper tests update their fixture expectations from `media_root` to install root where appropriate.
