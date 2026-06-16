<script lang="ts">
  import type { CaptureStatus, ListenerStatus, PacketRaceState } from './types';

  export let listener: ListenerStatus;
  export let capture: CaptureStatus;
  export let lastEvent = 'Dashboard starting';

  const numberFormatter = new Intl.NumberFormat();

  function formatNumber(value: number | null | undefined) {
    return numberFormatter.format(value ?? 0);
  }

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

  $: endpoint = `UDP ${listener.udp_host}:${listener.udp_port}`;
  $: packetsObserved = Math.max(listener.packets_received, capture.packet_receipt.packets_observed);
  $: packetText = `${formatNumber(packetsObserved)} observed · ${formatNumber(listener.packets_recorded)} recorded`;
  $: latestPacket = packetTypeDisplay(capture);
  $: listenerText = `${listener.state}: ${listener.message}`;
  $: listenerDisplayText = listener.state;
  $: capturePhaseText = capture.recording.active ? 'recording' : compactPhase(capture.phase);
  $: captureText = `${capture.mode} · ${capturePhaseText}`;
  $: storageText = `Prebuffer ${formatNumber(capture.prebuffer.size)}/${formatNumber(capture.prebuffer.capacity)} · saved ${formatNumber(capture.recording.total_live_packets_recorded_excluding_prebuffer)}`;
  $: eventText = lastEvent || 'No recent telemetry event';
  $: eventDisplayText = compactEvent(eventText);
</script>

<section class="status-strip" aria-label="Telemetry status bar">
  <div class="status-fields" role="status" aria-label="Telemetry status" aria-live="off" aria-atomic="false">
    <div class="status-segment status-segment-endpoint">
      <span class="status-label">Endpoint</span>
      <strong>{endpoint}</strong>
    </div>
    <div class="status-segment status-segment-packets">
      <span class="status-label">Packets</span>
      <span>{packetText}</span>
    </div>
    <div class="status-segment status-segment-latest">
      <span class="status-label">Latest packet</span>
      <strong
        class={`status-packet-pill status-packet-${latestPacket.state}`}
        aria-label={latestPacket.ariaLabel}
        title={latestPacket.title}
      >
        {latestPacket.label}
      </strong>
    </div>
    <div class="status-segment status-segment-listener">
      <span class="status-label">Listener</span>
      <span aria-label={`Listener ${listenerText}`} title={listenerText}>{listenerDisplayText}</span>
    </div>
    <div
      class="status-segment status-segment-capture"
      title={`${capture.mode} · ${capture.phase}${capture.recording.active ? ' · recording active' : ''}`}
    >
      <span class="status-label">Capture</span>
      <span>{captureText}</span>
    </div>
    <div class="status-segment status-segment-storage">
      <span class="status-label">Storage</span>
      <span>{storageText}</span>
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
    --status-packets-min-width: 18rem;
    --status-latest-min-width: 11.25rem;
    --status-listener-min-width: 8rem;
    --status-capture-min-width: 11.25rem;
    --status-storage-min-width: 15rem;
    --status-event-min-width: 11.75rem;

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

  .status-segment-packets {
    --status-section-min-width: var(--status-packets-min-width);
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

  .status-segment-storage {
    --status-section-min-width: var(--status-storage-min-width);
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

  .status-packet-pill {
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

  .status-packet-pill::before {
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

  @media (max-width: 1540px) {
    .status-segment-storage {
      display: none;
    }
  }

  @media (max-width: 1300px) {
    .status-segment-capture {
      display: none;
    }
  }

  @media (max-width: 1180px) {
    .status-fields {
      --status-endpoint-min-width: 11rem;
      --status-packets-min-width: 17rem;
      --status-latest-min-width: 11rem;
      --status-listener-min-width: 8rem;
      --status-event-min-width: 11.5rem;
    }
  }

  @media (max-width: 900px) {
    .status-fields {
      --status-endpoint-min-width: 10.5rem;
      --status-latest-min-width: 10.5rem;
      --status-listener-min-width: 8rem;
      --status-event-min-width: 11rem;
    }

    .status-segment-packets,
    .status-segment-capture,
    .status-segment-storage {
      display: none;
    }
  }
</style>
