import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import AppModal from './AppModal.svelte';

function renderModal(title = 'Telemetry settings') {
  const close = vi.fn();
  const result = render(AppModal, {
    props: { title },
    events: { close }
  });

  return { close, ...result };
}

describe('AppModal', () => {
  it('closes on Escape', async () => {
    const { close } = renderModal();

    await screen.findByRole('dialog', { name: 'Telemetry settings' });
    await fireEvent.keyDown(window, { key: 'Escape' });

    expect(close).toHaveBeenCalledTimes(1);
  });

  it('closes on backdrop click', async () => {
    const { close, container } = renderModal();
    const backdrop = container.querySelector('.modal-backdrop');
    expect(backdrop).not.toBeNull();

    await fireEvent.click(backdrop as HTMLElement);

    expect(close).toHaveBeenCalledTimes(1);
  });

  it('closes from the close button', async () => {
    const { close } = renderModal();

    await fireEvent.click(screen.getByRole('button', { name: 'Close Telemetry settings' }));

    expect(close).toHaveBeenCalledTimes(1);
  });

  it('wraps Tab focus within the modal', async () => {
    renderModal();

    const dialog = await screen.findByRole('dialog', { name: 'Telemetry settings' });
    await waitFor(() => expect(dialog).toHaveFocus());

    const closeButton = screen.getByRole('button', { name: 'Close Telemetry settings' });
    closeButton.focus();
    expect(closeButton).toHaveFocus();

    const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    window.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(closeButton).toHaveFocus();

    const shiftTab = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
    window.dispatchEvent(shiftTab);
    expect(shiftTab.defaultPrevented).toBe(true);
    expect(closeButton).toHaveFocus();
  });

  it('restores focus to the previously focused element on unmount', async () => {
    const opener = document.createElement('button');
    opener.textContent = 'Open modal';
    document.body.append(opener);
    opener.focus();

    try {
      const { unmount } = renderModal();
      const dialog = await screen.findByRole('dialog', { name: 'Telemetry settings' });
      await waitFor(() => expect(dialog).toHaveFocus());

      unmount();

      await waitFor(() => expect(opener).toHaveFocus());
    } finally {
      opener.remove();
    }
  });
});
