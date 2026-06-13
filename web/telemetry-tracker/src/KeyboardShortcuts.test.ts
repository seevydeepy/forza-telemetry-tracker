import { describe, expect, it } from 'vitest';
import { actionForKey } from './KeyboardShortcuts';

function keyboardEvent(key: string, target: EventTarget = document.body, modifiers: Partial<KeyboardEvent> = {}) {
  return {
    altKey: false,
    code: key === ' ' ? 'Space' : '',
    ctrlKey: false,
    defaultPrevented: false,
    key,
    metaKey: false,
    shiftKey: false,
    target,
    composedPath: () => [target, document.body, document, window],
    ...modifiers
  } as unknown as KeyboardEvent;
}

describe('actionForKey', () => {
  it('maps registered keyboard shortcuts to actions', () => {
    expect(actionForKey(keyboardEvent('O'))).toBe('cycleOverlay');
    expect(actionForKey(keyboardEvent('o'))).toBe('cycleOverlay');
    expect(actionForKey(keyboardEvent('R'))).toBeNull();
    expect(actionForKey(keyboardEvent('r'))).toBeNull();
    expect(actionForKey(keyboardEvent('Escape'))).toBe('clearSelection');
    expect(actionForKey(keyboardEvent(' '))).toBe('toggleLiveFollow');
    expect(actionForKey(keyboardEvent('x'))).toBeNull();
  });

  it('ignores browser and system modifier-key combinations', () => {
    expect(actionForKey(keyboardEvent('R', document.body, { ctrlKey: true }))).toBeNull();
    expect(actionForKey(keyboardEvent('R', document.body, { metaKey: true }))).toBeNull();
    expect(actionForKey(keyboardEvent('O', document.body, { ctrlKey: true }))).toBeNull();
    expect(actionForKey(keyboardEvent('O', document.body, { altKey: true }))).toBeNull();
    expect(actionForKey(keyboardEvent('O', document.body, { shiftKey: true }))).toBe('cycleOverlay');
    expect(actionForKey(keyboardEvent('R', document.body, { shiftKey: true }))).toBeNull();
  });

  it('ignores shortcuts from typing and editable targets', () => {
    const input = document.createElement('input');
    const textarea = document.createElement('textarea');
    const select = document.createElement('select');
    const editable = document.createElement('div');
    editable.contentEditable = 'true';
    editable.setAttribute('contenteditable', 'true');

    for (const [label, target] of [
      ['input', input],
      ['textarea', textarea],
      ['select', select],
      ['editable', editable]
    ] as const) {
      expect(actionForKey(keyboardEvent('O', target)), label).toBeNull();
      expect(actionForKey(keyboardEvent('R', target)), label).toBeNull();
      expect(actionForKey(keyboardEvent('Escape', target)), label).toBeNull();
      expect(actionForKey(keyboardEvent(' ', target)), label).toBeNull();
    }
  });
});
