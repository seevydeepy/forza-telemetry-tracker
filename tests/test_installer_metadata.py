from pathlib import Path


INSTALLER_SCRIPT = Path("packaging/installer/forza-telemetry-tracker.iss")


def test_installer_uses_exe_icon_for_windows_app_surfaces() -> None:
    script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert "UninstallDisplayIcon={app}\\{#AppExeName}" in script
    assert (
        'Name: "{group}\\{#AppName}"; Filename: "{app}\\{#AppExeName}"; '
        'IconFilename: "{app}\\{#AppExeName}"; IconIndex: 0'
    ) in script
    assert (
        'Name: "{autodesktop}\\{#AppName}"; Filename: "{app}\\{#AppExeName}"; '
        'IconFilename: "{app}\\{#AppExeName}"; IconIndex: 0; Tasks: desktopicon'
    ) in script


def test_installer_refreshes_stale_start_menu_icon_cache() -> None:
    script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    assert '[InstallDelete]\nType: files; Name: "{group}\\{#AppName}.lnk"' in script
    assert "ShellChangeNotifyAssociationChanged = $08000000;" in script
    assert "ShellChangeNotifyIdList = $0000;" in script
    assert "external 'SHChangeNotifyW@shell32.dll stdcall'" in script
    assert "SHChangeNotify(ShellChangeNotifyAssociationChanged, ShellChangeNotifyIdList, 0, 0);" in script
