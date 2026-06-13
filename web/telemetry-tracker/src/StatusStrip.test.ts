import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import StatusStrip from './StatusStrip.svelte';
import type { CaptureStatus, ListenerStatus } from './types';

const listener: ListenerStatus = {
  state: 'receiving',
  udp_host: '127.0.0.1',
  udp_port: 5400,
  packets_received: 12,
  packets_recorded: 4,
  message: 'receiving UDP telemetry on 127.0.0.1:5400'
};

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
  it('uses flex-growing sections with explicit minimum widths so live text can expand without jitter', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/StatusStrip.svelte'), 'utf8');
    const statusFieldsCss = source.match(/\.status-fields\s*{(?<body>[\s\S]*?)}/)?.groups?.body ?? '';
    const statusSegmentCss = source.match(/\.status-segment\s*{(?<body>[\s\S]*?)}/)?.groups?.body ?? '';

    expect(statusFieldsCss).toContain('display: flex');
    expect(statusFieldsCss).toContain('--status-packets-min-width');
    expect(statusSegmentCss).toContain('flex: var(--status-section-grow, 1) 1 var(--status-section-min-width)');
    expect(statusSegmentCss).toContain('min-width: var(--status-section-min-width)');
    expect(statusFieldsCss).not.toContain('grid-template-columns');
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
});
