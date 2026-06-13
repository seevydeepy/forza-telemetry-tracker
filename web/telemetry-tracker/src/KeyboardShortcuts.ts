export type ShortcutAction = 'cycleOverlay' | 'clearSelection' | 'toggleLiveFollow';

export const SHORTCUTS = [
  { key: 'O', action: 'cycleOverlay', label: 'Cycle overlay view' },
  { key: 'Esc', action: 'clearSelection', label: 'Clear selection or close popover' },
  { key: 'Space', action: 'toggleLiveFollow', label: 'Pause or resume live follow' }
] as const satisfies ReadonlyArray<{ key: string; action: ShortcutAction; label: string }>;

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return true;
  if (target.isContentEditable) return true;
  const editableAttribute = target.getAttribute('contenteditable');
  if (editableAttribute !== null && editableAttribute.toLowerCase() !== 'false') return true;
  return !!target.closest('[contenteditable]:not([contenteditable="false"])');
}

export function actionForKey(event: KeyboardEvent): ShortcutAction | null {
  const target = event.composedPath?.()[0] ?? event.target;
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || isEditableTarget(target)) return null;

  const normalizedKey = event.key.toLowerCase();
  if (normalizedKey === 'o') return 'cycleOverlay';
  if (event.key === 'Escape') return 'clearSelection';
  if (event.key === ' ' || event.key === 'Spacebar' || event.key === 'Space' || event.code === 'Space') {
    return 'toggleLiveFollow';
  }
  return null;
}
