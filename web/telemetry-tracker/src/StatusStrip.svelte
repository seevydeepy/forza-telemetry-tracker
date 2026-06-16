<script lang="ts">
  import type { CaptureStatus, ListenerState, ListenerStatus, PacketRaceState } from './types';

  export let listener: ListenerStatus;
  export let capture: CaptureStatus;
  export let lastEvent = 'Dashboard starting';

  function compactEvent(value: string) {
    return value.trim().replace(/\s+/g, ' ');
  }

  function compactPhase(value: string) {
    if (value === 'receiving_not_recording') return 'receiving';
    return value.replace(/_/g, ' ');
  }

  type PacketTypeDisplay = {
    state: PacketRaceState | 'waiting';
    label: string;
    title: string;
    ariaLabel: string;
  };

  function packetTypeDisplay(captureStatus: CaptureStatus): PacketTypeDisplay {
    const receipt = captureStatus.packet_receipt;
    if (!receipt.has_received_packets) {
      return {
        state: 'waiting',
        label: 'Waiting',
        title: 'No packet has been received yet.',
        ariaLabel: 'Latest packet type: waiting for telemetry'
      };
    }

    if (receipt.last_is_race_on === true || receipt.last_packet_type === 'race') {
      return {
        state: 'race',
        label: 'Race',
        title: 'The latest received packet has IsRaceOn enabled.',
        ariaLabel: 'Latest packet type: race packet'
      };
    }

    if (receipt.last_is_race_on === false || receipt.last_packet_type === 'non_race') {
      return {
        state: 'non_race',
        label: 'Non-race',
        title: 'The latest received packet has IsRaceOn disabled.',
        ariaLabel: 'Latest packet type: non-race packet'
      };
    }

    return {
      state: 'unknown',
      label: 'Unknown',
      title: 'A packet has been received, but its race state was not included in the status payload.',
      ariaLabel: 'Latest packet type: unknown'
    };
  }

  function listenerStateLabel(state: ListenerState) {
    switch (state) {
      case 'starting':
        return 'Starting';
      case 'waiting':
        return 'Waiting';
      case 'receiving':
        return 'Receiving';
      case 'recording':
        return 'Recording';
      case 'error':
        return 'Error';
    }
  }

  $: endpoint = `UDP ${listener.udp_host}:${listener.udp_port}`;
  $: latestPacket = packetTypeDisplay(capture);
  $: listenerText = `${listener.state}: ${listener.message}`;
  $: listenerDisplayText = listenerStateLabel(listener.state);
  $: capturePhaseText = capture.recording.active ? 'recording' : compactPhase(capture.phase);
  $: captureText = `${capture.mode} · ${capturePhaseText}`;
  $: eventText = lastEvent || 'No recent telemetry event';
  $: eventDisplayText = compactEvent(eventText);
</script>

<section class="status-strip" aria-label="Telemetry status bar">
  <div class="status-fields" role="status" aria-label="Telemetry status" aria-live="off" aria-atomic="false">
    <div class="status-segment status-segment-endpoint">
      <span class="status-label">Endpoint</span>
      <strong>{endpoint}</strong>
    </div>
    <div class="status-segment status-segment-latest">
      <strong
        class={`status-indicator-pill status-packet-${latestPacket.state}`}
        aria-label={latestPacket.ariaLabel}
        title={latestPacket.title}
      >
        {latestPacket.label}
      </strong>
    </div>
    <div class="status-segment status-segment-listener">
      <span class="status-label">Listener</span>
      <strong
        class={`status-indicator-pill status-listener-${listener.state}`}
        aria-label={`Listener ${listenerText}`}
        title={listenerText}
      >
        {listenerDisplayText}
      </strong>
    </div>
    <div
      class="status-segment status-segment-capture"
      title={`${capture.mode} · ${capture.phase}${capture.recording.active ? ' · recording active' : ''}`}
    >
      <span class="status-label">Capture</span>
      <span>{captureText}</span>
    </div>
    <div class="status-segment status-segment-event" title={eventText}>
      <span class="status-label">Last event</span>
      <span aria-label={`Last event: ${eventText}`}>{eventDisplayText}</span>
    </div>
  </div>
</section>

<style>
  .status-strip {
    align-items: center;
    background: #111113;
    color: #d4d4d8;
    display: grid;
    font-variant-numeric: tabular-nums;
    gap: 1rem;
    min-height: 0;
    overflow: hidden;
    padding: 0.35rem 1rem;
    white-space: nowrap;
  }

  .status-fields {
    --status-endpoint-min-width: 12rem;
    --status-latest-min-width: 6.75rem;
    --status-listener-min-width: 12rem;
    --status-capture-min-width: 14rem;
    --status-event-min-width: 14rem;

    align-items: center;
    display: flex;
    gap: 0.5rem;
    min-width: 0;
    overflow: hidden;
    width: 100%;
  }

  .status-segment {
    --status-section-min-width: 10rem;

    align-items: baseline;
    border-left: 1px solid #27272a;
    display: inline-flex;
    flex: 0 0 var(--status-section-min-width);
    gap: 0.4rem;
    max-width: 100%;
    min-width: var(--status-section-min-width);
    overflow: hidden;
    padding-left: 0.75rem;
  }

  .status-segment:first-child {
    border-left: 0;
    padding-left: 0;
  }

  .status-segment-endpoint {
    --status-section-min-width: var(--status-endpoint-min-width);
  }

  .status-segment-latest {
    --status-section-min-width: var(--status-latest-min-width);
  }

  .status-segment-listener {
    --status-section-min-width: var(--status-listener-min-width);
  }

  .status-segment-capture {
    --status-section-min-width: var(--status-capture-min-width);
  }

  .status-segment-event {
    flex: 1 1 var(--status-event-min-width);
    --status-section-min-width: var(--status-event-min-width);
  }

  .status-segment span:last-child,
  .status-segment strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .status-segment span:last-child,
  .status-segment-endpoint strong {
    flex: 1 1 auto;
  }

  .status-segment-endpoint strong {
    color: #f4f4f5;
    font-size: 0.82rem;
  }

  .status-indicator-pill {
    align-items: center;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    display: inline-flex;
    font-size: 0.72rem;
    font-weight: 800;
    gap: 0.35rem;
    letter-spacing: 0.03em;
    line-height: 1;
    padding: 0.16rem 0.48rem;
    text-transform: uppercase;
  }

  .status-indicator-pill::before {
    background: currentColor;
    border-radius: 999px;
    content: '';
    flex: 0 0 auto;
    height: 0.45rem;
    width: 0.45rem;
  }

  .status-packet-race {
    background: rgba(34, 197, 94, 0.16);
    border-color: rgba(34, 197, 94, 0.45);
    color: #bbf7d0;
  }

  .status-packet-non_race {
    background: rgba(245, 158, 11, 0.16);
    border-color: rgba(245, 158, 11, 0.45);
    color: #fde68a;
  }

  .status-packet-waiting,
  .status-packet-unknown {
    background: rgba(113, 113, 122, 0.16);
    border-color: rgba(113, 113, 122, 0.42);
    color: #d4d4d8;
  }

  .status-listener-receiving,
  .status-listener-recording {
    background: rgba(34, 197, 94, 0.16);
    border-color: rgba(34, 197, 94, 0.45);
    color: #bbf7d0;
  }

  .status-listener-starting,
  .status-listener-waiting {
    background: rgba(245, 158, 11, 0.16);
    border-color: rgba(245, 158, 11, 0.45);
    color: #fde68a;
  }

  .status-listener-error {
    background: rgba(239, 68, 68, 0.16);
    border-color: rgba(239, 68, 68, 0.45);
    color: #fecaca;
  }

  .status-label {
    color: #71717a;
    flex: 0 0 auto;
    font-size: 0.7rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .status-segment-event {
    color: #f4f4f5;
  }

  @media (max-width: 1020px) {
    .status-segment-endpoint {
      display: none;
    }

    .status-segment-latest {
      border-left: 0;
      padding-left: 0;
    }
  }

  @media (max-width: 800px) {
    .status-segment-listener {
      display: none;
    }
  }

  @media (max-width: 620px) {
    .status-fields {
      --status-event-min-width: 8rem;
    }

    .status-segment-capture {
      display: none;
    }
  }
</style>
