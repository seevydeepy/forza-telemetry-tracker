import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import StatusStrip from './StatusStrip.svelte';
import type { CaptureStatus, ListenerState, ListenerStatus } from './types';

const listener: ListenerStatus = {
  state: 'receiving',
  udp_host: '127.0.0.1',
  udp_port: 5400,
  packets_received: 12,
  packets_recorded: 4,
  message: 'receiving UDP telemetry on 127.0.0.1:5400'
};

function listenerWithState(state: ListenerState): ListenerStatus {
  return {
    ...listener,
    state,
    message: `${state} listener`
  };
}

function captureWithPacket(lastIsRaceOn: boolean | null, hasReceivedPackets = true): CaptureStatus {
  const packetType = lastIsRaceOn === true ? 'race' : lastIsRaceOn === false ? 'non_race' : 'unknown';
  return {
    mode: 'auto',
    phase: hasReceivedPackets ? 'receiving_not_recording' : 'idle',
    packet_receipt: {
      state: hasReceivedPackets ? 'receiving' : 'waiting',
      has_received_packets: hasReceivedPackets,
      packets_observed: hasReceivedPackets ? 12 : 0,
      last_timestamp_ms: hasReceivedPackets ? 192 : null,
      last_is_race_on: lastIsRaceOn,
      last_packet_type: packetType
    },
    recording: {
      active: false,
      phase: hasReceivedPackets ? 'receiving_not_recording' : 'idle',
      mode: 'auto',
      total_live_packets_recorded_excluding_prebuffer: 4
    },
    prebuffer: {
      capacity: 300,
      size: 2
    },
    auto_detection: {
      last_signals: {},
      last_reason: 'waiting_for_packet'
    }
  };
}

afterEach(() => cleanup());

describe('StatusStrip', () => {
  it('keeps known sections fixed-width and lets Last event absorb remaining space', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/StatusStrip.svelte'), 'utf8');
    const statusFieldsCss = source.match(/\.status-fields\s*{(?<body>[\s\S]*?)}/)?.groups?.body ?? '';
    const statusSegmentCss = source.match(/\.status-segment\s*{(?<body>[\s\S]*?)}/)?.groups?.body ?? '';
    const statusEventCss = source.match(/\.status-segment-event\s*{(?<body>[\s\S]*?)}/)?.groups?.body ?? '';

    expect(statusFieldsCss).toContain('display: flex');
    expect(statusFieldsCss).toContain('--status-listener-min-width: 12rem');
    expect(statusFieldsCss).toContain('--status-capture-min-width: 14rem');
    expect(statusFieldsCss).not.toContain('--status-packets-min-width');
    expect(statusFieldsCss).not.toContain('--status-storage-min-width');
    expect(statusSegmentCss).toContain('flex: 0 0 var(--status-section-min-width)');
    expect(statusSegmentCss).toContain('min-width: var(--status-section-min-width)');
    expect(statusEventCss).toContain('flex: 1 1 var(--status-event-min-width)');
    expect(source).not.toContain('status-segment-packets');
    expect(source).not.toContain('status-segment-storage');
    expect(source).not.toContain('--status-section-grow');
    expect(statusFieldsCss).not.toContain('grid-template-columns');
  });

  it('drops responsive sections in endpoint, listener, capture order', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/StatusStrip.svelte'), 'utf8');
    const endpointHideIndex = source.search(/\.status-segment-endpoint\s*{\s*display: none;/);
    const listenerHideIndex = source.search(/\.status-segment-listener\s*{\s*display: none;/);
    const captureHideIndex = source.search(/\.status-segment-capture\s*{\s*display: none;/);

    expect(endpointHideIndex).toBeGreaterThan(-1);
    expect(listenerHideIndex).toBeGreaterThan(endpointHideIndex);
    expect(captureHideIndex).toBeGreaterThan(listenerHideIndex);
  });

  it('shows a race packet indicator when the latest packet has IsRaceOn enabled', () => {
    render(StatusStrip, {
      props: {
        listener,
        capture: captureWithPacket(true),
        lastEvent: 'capture updated'
      }
    });

    expect(screen.getByLabelText('Latest packet type: race packet')).toHaveTextContent('Race');
    expect(screen.queryByText('Latest packet')).not.toBeInTheDocument();
  });

  it('shows a non-race packet indicator when the latest packet has IsRaceOn disabled', () => {
    render(StatusStrip, {
      props: {
        listener,
        capture: captureWithPacket(false),
        lastEvent: 'capture updated'
      }
    });

    expect(screen.getByLabelText('Latest packet type: non-race packet')).toHaveTextContent('Non-race');
  });

  it('shows a waiting indicator before any packets arrive', () => {
    render(StatusStrip, {
      props: {
        listener,
        capture: captureWithPacket(null, false),
        lastEvent: 'Dashboard starting'
      }
    });

    expect(screen.getByLabelText('Latest packet type: waiting for telemetry')).toHaveTextContent('Waiting');
  });

  it.each([
    ['receiving', 'Receiving', 'status-listener-receiving'],
    ['recording', 'Recording', 'status-listener-recording'],
    ['waiting', 'Waiting', 'status-listener-waiting'],
    ['starting', 'Starting', 'status-listener-starting'],
    ['error', 'Error', 'status-listener-error']
  ] satisfies [ListenerState, string, string][])(
    'shows a %s listener status indicator',
    (state, label, className) => {
      render(StatusStrip, {
        props: {
          listener: listenerWithState(state),
          capture: captureWithPacket(true),
          lastEvent: 'capture updated'
        }
      });

      const indicator = screen.getByLabelText(`Listener ${state}: ${state} listener`);
      expect(indicator).toHaveTextContent(label);
      expect(indicator).toHaveClass('status-indicator-pill', className);
    }
  );
});
