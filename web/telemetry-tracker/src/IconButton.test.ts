import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import IconButton from './IconButton.svelte';

describe('IconButton', () => {
  it('renders an svg icon with an accessible label and tooltip', async () => {
    const click = vi.fn();
    render(IconButton, {
      props: {
        icon: 'settings',
        label: 'Open settings',
        title: 'Open telemetry tracker settings',
        onClick: click
      }
    });

    const button = screen.getByRole('button', { name: 'Open settings' });
    expect(button).toHaveAttribute('title', 'Open telemetry tracker settings');
    expect(button.querySelector('svg')).not.toBeNull();

    await fireEvent.click(button);
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('can render a submit button when used inside forms', () => {
    render(IconButton, {
      props: {
        icon: 'map',
        label: 'Save changes',
        type: 'submit'
      }
    });

    const button = screen.getByRole('button', { name: 'Save changes' });
    expect(button).toHaveAttribute('type', 'submit');
    expect(button.querySelector('svg')).toHaveAttribute('viewBox', '0 -960 960 960');
  });
});
