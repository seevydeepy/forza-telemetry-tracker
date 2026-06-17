type Fh6InstallFolderPicker = (currentPath?: string | null) => Promise<string | null> | string | null;
type FolderPicker = (currentPath?: string | null) => Promise<string | null> | string | null;
export type RawTelemetryNativeSelection = {
  selectionId: string;
  sourceType: 'file' | 'files' | 'folder';
  fileCount: number;
  displayName: string;
  summary: string;
  expiresAtMs: number;
};
type RawTelemetrySelectionPayload = RawTelemetryNativeSelection | {
  selection_id?: unknown;
  selectionId?: unknown;
  source_type?: unknown;
  sourceType?: unknown;
  file_count?: unknown;
  fileCount?: unknown;
  display_name?: unknown;
  displayName?: unknown;
  summary?: unknown;
  expires_at_ms?: unknown;
  expiresAtMs?: unknown;
};
type RawTelemetrySelectionPicker = (
  currentPath?: string | null
) => Promise<RawTelemetrySelectionPayload | null> | RawTelemetrySelectionPayload | null;

type PywebviewApi = {
  choose_fh6_install_folder?: Fh6InstallFolderPicker;
  choose_export_folder?: FolderPicker;
  choose_raw_telemetry_files?: RawTelemetrySelectionPicker;
  choose_raw_telemetry_folder?: RawTelemetrySelectionPicker;
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

function rawTelemetryFilesPicker(): RawTelemetrySelectionPicker | null {
  return picker('choose_raw_telemetry_files');
}

function rawTelemetryFolderPicker(): RawTelemetrySelectionPicker | null {
  return picker('choose_raw_telemetry_folder');
}

function cleanSelectedPath(selected: unknown): string | null {
  if (typeof selected !== 'string') return null;
  const trimmed = selected.trim();
  return trimmed || null;
}

function cleanNativeSelection(selected: RawTelemetrySelectionPayload | null): RawTelemetryNativeSelection | null {
  if (!selected || typeof selected !== 'object') return null;
  const record = selected as Record<string, unknown>;
  const selectionId = String(record.selectionId ?? record.selection_id ?? '').trim();
  const sourceType = String(record.sourceType ?? record.source_type ?? '').trim();
  if (!selectionId || !['file', 'files', 'folder'].includes(sourceType)) return null;
  const fileCount = Number(record.fileCount ?? record.file_count ?? 0);
  return {
    selectionId,
    sourceType: sourceType as RawTelemetryNativeSelection['sourceType'],
    fileCount: Number.isFinite(fileCount) && fileCount > 0 ? fileCount : 0,
    displayName: String(record.displayName ?? record.display_name ?? '').trim(),
    summary: String(record.summary ?? '').trim(),
    expiresAtMs: Number(record.expiresAtMs ?? record.expires_at_ms ?? 0)
  };
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

export async function chooseRawTelemetryFiles(currentPath = ''): Promise<RawTelemetryNativeSelection | null> {
  const picker = rawTelemetryFilesPicker();
  if (!picker) return null;

  const selected = await picker(currentPath.trim() || null);
  return cleanNativeSelection(selected);
}

export async function chooseRawTelemetryFolder(currentPath = ''): Promise<RawTelemetryNativeSelection | null> {
  const picker = rawTelemetryFolderPicker();
  if (!picker) return null;

  const selected = await picker(currentPath.trim() || null);
  return cleanNativeSelection(selected);
}
