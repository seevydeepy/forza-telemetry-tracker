import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import ReviewTimeline from './ReviewTimeline.svelte';
import type { SequenceRange } from './types';

const bounds: SequenceRange = { startSequence: 10, endSequence: 20 };

function renderTimeline(props: Partial<{ bounds: SequenceRange | null; selectedRange: SequenceRange | null; disabled: boolean; message: string }> = {}) {
  const rangechange = vi.fn();
  render(ReviewTimeline, {
    props: {
      bounds: null,
      selectedRange: null,
      disabled: false,
      ...props
    },
    events: { rangechange }
  });
  return { rangechange };
}

function pointerDownAt(element: HTMLElement, clientX: number, pointerId: number) {
  const event = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, clientX });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  return fireEvent(element, event);
}

describe('ReviewTimeline', () => {
  it('renders an empty message without operable range controls or reset when bounds are unavailable', () => {
    renderTimeline({ message: 'Select a saved lap to review the timeline.' });

    expect(screen.getByRole('region', { name: 'Review timeline' })).toBeInTheDocument();
    expect(screen.getByText('Select a saved lap to review the timeline.')).toBeInTheDocument();
    expect(screen.queryByRole('slider', { name: 'Section start sequence' })).toBeNull();
    expect(screen.queryByRole('slider', { name: 'Section end sequence' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reset timeline to full lap' })).toBeNull();
  });

  it('dispatches rangechange when enabled start and end inputs change', async () => {
    const { rangechange } = renderTimeline({ bounds });

    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '12' } });
    await fireEvent.input(screen.getByRole('slider', { name: 'Section end sequence' }), { target: { value: '18' } });

    expect(rangechange).toHaveBeenCalledTimes(2);
    expect(rangechange.mock.calls[0][0].detail.range).toEqual({ startSequence: 12, endSequence: 20 });
    expect(rangechange.mock.calls[1][0].detail.range).toEqual({ startSequence: 12, endSequence: 18 });
  });

  it('renders start and end thumbs on one shared track with the selected segment between them', () => {
    renderTimeline({
      bounds,
      selectedRange: { startSequence: 12, endSequence: 18 }
    });

    const rangeControl = screen.getByRole('group', { name: 'Timeline selected range' });
    const selectedSegment = screen.getByTestId('timeline-selected-segment');
    const start = screen.getByRole('slider', { name: 'Section start sequence' });
    const end = screen.getByRole('slider', { name: 'Section end sequence' });

    expect(rangeControl).toContainElement(start);
    expect(rangeControl).toContainElement(end);
    expect(selectedSegment).toHaveStyle({ left: '20%', width: '60%' });
    expect(start).toHaveValue('12');
    expect(end).toHaveValue('18');
  });

  it('keeps thumbs from crossing when either side is dragged beyond the other', async () => {
    const { rangechange } = renderTimeline({
      bounds,
      selectedRange: { startSequence: 12, endSequence: 18 }
    });

    const start = screen.getByRole('slider', { name: 'Section start sequence' });
    const end = screen.getByRole('slider', { name: 'Section end sequence' });

    await fireEvent.input(start, { target: { value: '19' } });
    await fireEvent.input(end, { target: { value: '11' } });

    expect(rangechange).toHaveBeenCalledTimes(2);
    expect(rangechange.mock.calls[0][0].detail.range).toEqual({ startSequence: 18, endSequence: 18 });
    expect(rangechange.mock.calls[1][0].detail.range).toEqual({ startSequence: 18, endSequence: 18 });
    expect(start).toHaveValue('18');
    expect(end).toHaveValue('18');
  });

  it('updates the nearest endpoint when the timeline track is clicked', async () => {
    const { rangechange } = renderTimeline({
      bounds,
      selectedRange: { startSequence: 12, endSequence: 18 }
    });

    const rangeControl = screen.getByRole('group', { name: 'Timeline selected range' });
    rangeControl.setPointerCapture = vi.fn();
    vi.spyOn(rangeControl, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      left: 100,
      right: 300,
      top: 0,
      bottom: 32,
      width: 200,
      height: 32,
      toJSON: () => ({})
    });

    await pointerDownAt(rangeControl, 180, 1);
    await pointerDownAt(rangeControl, 280, 2);

    expect(rangechange).toHaveBeenCalledTimes(2);
    expect(rangechange.mock.calls[0][0].detail.range).toEqual({ startSequence: 14, endSequence: 18 });
    expect(rangechange.mock.calls[1][0].detail.range).toEqual({ startSequence: 14, endSequence: 19 });
    expect(rangeControl.setPointerCapture).toHaveBeenCalledWith(1);
    expect(rangeControl.setPointerCapture).toHaveBeenCalledWith(2);
  });

  it('expands a collapsed range toward the clicked side of the timeline track', async () => {
    const { rangechange } = renderTimeline({
      bounds,
      selectedRange: { startSequence: 15, endSequence: 15 }
    });

    const rangeControl = screen.getByRole('group', { name: 'Timeline selected range' });
    rangeControl.setPointerCapture = vi.fn();
    vi.spyOn(rangeControl, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      left: 100,
      right: 300,
      top: 0,
      bottom: 32,
      width: 200,
      height: 32,
      toJSON: () => ({})
    });

    await pointerDownAt(rangeControl, 280, 1);

    expect(rangechange).toHaveBeenCalledTimes(1);
    expect(rangechange.mock.calls[0][0].detail.range).toEqual({ startSequence: 15, endSequence: 19 });
  });

  it('dispatches the full bounds when reset is selected', async () => {
    const { rangechange } = renderTimeline({
      bounds,
      selectedRange: { startSequence: 12, endSequence: 18 }
    });

    await fireEvent.click(screen.getByRole('button', { name: 'Reset timeline to full lap' }));

    expect(rangechange).toHaveBeenCalledTimes(1);
    expect(rangechange.mock.calls[0][0].detail.range).toEqual(bounds);
  });

  it('disables range inputs and reset without dispatching while disabled', async () => {
    const { rangechange } = renderTimeline({ bounds, disabled: true });

    const start = screen.getByRole('slider', { name: 'Section start sequence' });
    const end = screen.getByRole('slider', { name: 'Section end sequence' });
    const reset = screen.getByRole('button', { name: 'Reset timeline to full lap' });
    const rangeControl = screen.getByRole('group', { name: 'Timeline selected range' });
    rangeControl.setPointerCapture = vi.fn();
    expect(start).toBeDisabled();
    expect(end).toBeDisabled();
    expect(reset).toBeDisabled();

    await fireEvent.input(start, { target: { value: '12' } });
    await fireEvent.input(end, { target: { value: '18' } });
    await fireEvent.click(reset);
    await pointerDownAt(rangeControl, 180, 1);

    expect(rangechange).not.toHaveBeenCalled();
    expect(rangeControl.setPointerCapture).not.toHaveBeenCalled();
  });
});
