type Fh6InstallFolderPicker = (currentPath?: string | null) => Promise<string | null> | string | null;

type PywebviewApi = {
  choose_fh6_install_folder?: Fh6InstallFolderPicker;
};

declare global {
  interface Window {
    pywebview?: {
      api?: PywebviewApi;
    };
  }
}

function fh6InstallFolderPicker(): Fh6InstallFolderPicker | null {
  if (typeof window === 'undefined') return null;
  const picker = window.pywebview?.api?.choose_fh6_install_folder;
  return typeof picker === 'function' ? picker.bind(window.pywebview?.api) : null;
}

export function canChooseFh6InstallFolder(): boolean {
  return fh6InstallFolderPicker() !== null;
}

export async function chooseFh6InstallFolder(currentPath: string): Promise<string | null> {
  const picker = fh6InstallFolderPicker();
  if (!picker) return null;

  const selected = await picker(currentPath.trim() || null);
  if (typeof selected !== 'string') return null;

  const trimmed = selected.trim();
  return trimmed || null;
}
