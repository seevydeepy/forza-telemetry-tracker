type Fh6InstallFolderPicker = (currentPath?: string | null) => Promise<string | null> | string | null;
type FolderPicker = (currentPath?: string | null) => Promise<string | null> | string | null;
type FilePicker = (currentPath?: string | null) => Promise<string[] | string | null> | string[] | string | null;

type PywebviewApi = {
  choose_fh6_install_folder?: Fh6InstallFolderPicker;
  choose_export_folder?: FolderPicker;
  choose_raw_telemetry_files?: FilePicker;
  choose_raw_telemetry_folder?: FolderPicker;
};

declare global {
  interface Window {
    pywebview?: {
      api?: PywebviewApi;
    };
  }
}

function picker<K extends keyof PywebviewApi>(key: K): NonNullable<PywebviewApi[K]> | null {
  if (typeof window === 'undefined') return null;
  const candidate = window.pywebview?.api?.[key];
  return typeof candidate === 'function' ? candidate.bind(window.pywebview?.api) as NonNullable<PywebviewApi[K]> : null;
}

function fh6InstallFolderPicker(): Fh6InstallFolderPicker | null {
  return picker('choose_fh6_install_folder');
}

function exportFolderPicker(): FolderPicker | null {
  return picker('choose_export_folder');
}

function rawTelemetryFilesPicker(): FilePicker | null {
  return picker('choose_raw_telemetry_files');
}

function rawTelemetryFolderPicker(): FolderPicker | null {
  return picker('choose_raw_telemetry_folder');
}

function cleanSelectedPath(selected: unknown): string | null {
  if (typeof selected !== 'string') return null;
  const trimmed = selected.trim();
  return trimmed || null;
}

function cleanSelectedPaths(selected: unknown): string[] {
  const candidates = Array.isArray(selected) ? selected : typeof selected === 'string' ? [selected] : [];
  const cleaned = candidates
    .filter((item): item is string => typeof item === 'string')
    .map((item) => item.trim())
    .filter(Boolean);
  return Array.from(new Set(cleaned));
}

export function canChooseFh6InstallFolder(): boolean {
  return fh6InstallFolderPicker() !== null;
}

export function canChooseExportFolder(): boolean {
  return exportFolderPicker() !== null;
}

export function canChooseRawTelemetryFiles(): boolean {
  return rawTelemetryFilesPicker() !== null;
}

export function canChooseRawTelemetryFolder(): boolean {
  return rawTelemetryFolderPicker() !== null;
}

export async function chooseFh6InstallFolder(currentPath: string): Promise<string | null> {
  const picker = fh6InstallFolderPicker();
  if (!picker) return null;

  const selected = await picker(currentPath.trim() || null);
  return cleanSelectedPath(selected);
}

export async function chooseExportFolder(currentPath: string): Promise<string | null> {
  const picker = exportFolderPicker();
  if (!picker) return null;

  const selected = await picker(currentPath.trim() || null);
  return cleanSelectedPath(selected);
}

export async function chooseRawTelemetryFiles(currentPath = ''): Promise<string[]> {
  const picker = rawTelemetryFilesPicker();
  if (!picker) return [];

  const selected = await picker(currentPath.trim() || null);
  return cleanSelectedPaths(selected);
}

export async function chooseRawTelemetryFolder(currentPath = ''): Promise<string | null> {
  const picker = rawTelemetryFolderPicker();
  if (!picker) return null;

  const selected = await picker(currentPath.trim() || null);
  return cleanSelectedPath(selected);
}
