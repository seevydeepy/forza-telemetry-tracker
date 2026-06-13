<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { AnalysisSummary, DeltaSummary, LapSummary, ReferenceLap, SequenceRange, UnitSystem } from './types';

  export let summary: AnalysisSummary | null = null;
  export let deltaSummary: DeltaSummary | null = null;
  export let selectedLap: LapSummary | null = null;
  export let selectedRange: SequenceRange | null = null;
  export let unitSystem: UnitSystem | string = 'imperial';
  export let referenceLap: ReferenceLap | null = null;

  const dispatch = createEventDispatcher<{
    trackchange: { lapId: string };
  }>();

  const speedUnits: Record<UnitSystem, { label: string; factor: number }> = {
    imperial: { label: 'MPH', factor: 2.2369362920544 },
    metric: { label: 'KPH', factor: 3.6 }
  };

  $: speedUnit = unitSystem === 'metric' ? speedUnits.metric : speedUnits.imperial;

  function formatDecimal(value: number | null | undefined, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    return value.toFixed(digits);
  }

  function formatInteger(value: number | null | undefined) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    return String(Math.round(value));
  }

  function formatSignedDecimal(value: number | null | undefined, digits = 2, suffix = '') {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    const sign = value > 0 ? '+' : '';
    return `${sign}${value.toFixed(digits)}${suffix}`;
  }

  function formatSpeed(value: number | null | undefined, factor: number) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    return (value * factor).toFixed(1);
  }

  function formatSignedSpeed(value: number | null | undefined, factor: number) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    const converted = value * factor;
    const sign = converted > 0 ? '+' : '';
    return `${sign}${converted.toFixed(1)}`;
  }

  function formatMillisecondsAsSeconds(value: number | null | undefined) {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    return formatSignedDecimal(value / 1000, 3, 's');
  }

  function trackLabel(lap: LapSummary | null): string {
    if (lap?.track_profile_name && lap.track_profile_layout) {
      return `${lap.track_profile_name} — ${lap.track_profile_layout}`;
    }
    return lap?.track_profile_name ?? lap?.track_profile_layout ?? 'Unknown track';
  }

  function changeTrackAssignment() {
    if (!selectedLap) return;
    dispatch('trackchange', { lapId: selectedLap.id });
  }

  function formatLapTimeMs(ms: number | null | undefined): string {
    if (ms === null || ms === undefined || Number.isNaN(ms)) return '—';
    const totalSeconds = ms / 1000;
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds - minutes * 60;
    return `${minutes}:${seconds.toFixed(3).padStart(6, '0')}`;
  }

  function referenceSummaryField(ref: ReferenceLap | null, field: keyof AnalysisSummary): number | null {
    if (!ref) return null;
    const refSummary = ref.summary;
    if (refSummary && typeof refSummary === 'object' && field in refSummary) {
      const value = (refSummary as Record<string, unknown>)[field];
      if (typeof value === 'number' && Number.isFinite(value)) return value;
    }
    return null;
  }

  function referenceLapTimeMs(ref: ReferenceLap | null): number | null {
    if (!ref) return null;
    if (typeof ref.lap_time_ms === 'number' && Number.isFinite(ref.lap_time_ms)) return ref.lap_time_ms;
    if (typeof ref.lap_duration_ms === 'number' && Number.isFinite(ref.lap_duration_ms)) return ref.lap_duration_ms;
    const summaryTime = referenceSummaryField(ref, 'lap_time_ms');
    if (summaryTime !== null) return summaryTime;
    const summaryDuration = referenceSummaryField(ref, 'lap_duration_ms');
    if (summaryDuration !== null) return summaryDuration;
    return null;
  }

  type SplitTone = 'better' | 'worse' | 'neutral';

  function splitTone(diff: number | null, lowerIsBetter: boolean): SplitTone {
    if (diff === null || diff === 0) return 'neutral';
    return lowerIsBetter ? (diff < 0 ? 'better' : 'worse') : (diff > 0 ? 'better' : 'worse');
  }

  interface SplitBadge {
    label: string;
    tone: SplitTone;
    ariaLabel: string;
  }

  function makeSplitBadge(diff: number | null, fieldLabel: string, lowerIsBetter: boolean, format: (v: number) => string): SplitBadge | null {
    if (diff === null) return null;
    return {
      label: format(diff),
      tone: splitTone(diff, lowerIsBetter),
      ariaLabel: `${fieldLabel} split: ${format(diff)}`
    };
  }

  $: hasDelta = !!deltaSummary && deltaSummary.reference_sample_count > 0 && deltaSummary.current_sample_count > 0;
  $: selectedLapTrackLabel = trackLabel(selectedLap);
  $: isFullLap = !selectedRange;
  $: showSplits = isFullLap && referenceLap !== null;

  // Lap time split
  $: currentLapTimeMs = (() => {
    if (selectedLap && typeof selectedLap.lap_time_ms === 'number' && Number.isFinite(selectedLap.lap_time_ms)) return selectedLap.lap_time_ms;
    if (summary && typeof summary.lap_time_ms === 'number' && Number.isFinite(summary.lap_time_ms)) return summary.lap_time_ms;
    if (summary && typeof summary.lap_duration_ms === 'number' && Number.isFinite(summary.lap_duration_ms)) return summary.lap_duration_ms;
    return null;
  })();
  $: refLapTimeMs = referenceLapTimeMs(referenceLap);
  $: lapTimeDiffMs = (showSplits && currentLapTimeMs !== null && refLapTimeMs !== null) ? currentLapTimeMs - refLapTimeMs : null;
  $: lapTimeSplit = (() => {
    if (lapTimeDiffMs === null) return null;
    const seconds = lapTimeDiffMs / 1000;
    const sign = seconds > 0 ? '+' : '';
    return {
      label: `${sign}${seconds.toFixed(3)}`,
      tone: splitTone(lapTimeDiffMs, true),
      ariaLabel: `Lap time split: ${sign}${seconds.toFixed(3)}`
    };
  })();

  // Top speed split
  $: topSpeedRef = showSplits && referenceLap ? referenceSummaryField(referenceLap, 'top_speed_mps') : null;
  $: topSpeedSplit = makeSplitBadge(
    (showSplits && summary && topSpeedRef !== null) ? summary.top_speed_mps - topSpeedRef : null,
    'Top speed', false, (v) => formatSignedSpeed(v, speedUnit.factor)
  );

  // Average speed split
  $: avgSpeedRef = showSplits && referenceLap ? referenceSummaryField(referenceLap, 'average_speed_mps') : null;
  $: avgSpeedSplit = makeSplitBadge(
    (showSplits && summary && avgSpeedRef !== null) ? summary.average_speed_mps - avgSpeedRef : null,
    'Average speed', false, (v) => formatSignedSpeed(v, speedUnit.factor)
  );

  // Peak slip split
  $: peakSlipRef = showSplits && referenceLap ? referenceSummaryField(referenceLap, 'peak_combined_slip') : null;
  $: peakSlipSplit = makeSplitBadge(
    (showSplits && summary && peakSlipRef !== null) ? summary.peak_combined_slip - peakSlipRef : null,
    'Peak slip', true, (v) => formatSignedDecimal(v, 4)
  );

  // Limiter samples split
  $: limiterRef = showSplits && referenceLap ? referenceSummaryField(referenceLap, 'limiter_samples') : null;
  $: limiterSplit = makeSplitBadge(
    (showSplits && summary && limiterRef !== null) ? summary.limiter_samples - limiterRef : null,
    'Limiter samples', true, (v) => formatSignedDecimal(v, 0)
  );

  // Bottoming events split
  $: bottomingRef = showSplits && referenceLap ? referenceSummaryField(referenceLap, 'bottoming_events') : null;
  $: bottomingSplit = makeSplitBadge(
    (showSplits && summary && bottomingRef !== null) ? summary.bottoming_events - bottomingRef : null,
    'Bottoming events', true, (v) => formatSignedDecimal(v, 0)
  );
</script>

<section class="lap-breakdown" aria-label="Lap breakdown">
  {#if selectedLap}
    <div class="track-summary">
      <span class="track-summary-label">Track</span>
      <button
        type="button"
        class="track-change-button"
        aria-label={`Change track assignment: ${selectedLapTrackLabel}`}
        on:click={changeTrackAssignment}
      >
        {selectedLapTrackLabel}
      </button>
    </div>
  {/if}

  {#if summary}
    <dl>
      {#if isFullLap && currentLapTimeMs !== null}
        <div>
          <dt>Lap time</dt>
          <dd>{formatLapTimeMs(currentLapTimeMs)}{#if lapTimeSplit}<span class="split-badge {lapTimeSplit.tone}" aria-label={lapTimeSplit.ariaLabel}>{lapTimeSplit.label}</span>{/if}</dd>
        </div>
      {/if}
      <div>
        <dt>Top speed ({speedUnit.label})</dt>
        <dd>{formatSpeed(summary.top_speed_mps, speedUnit.factor)}{#if topSpeedSplit}<span class="split-badge {topSpeedSplit.tone}" aria-label={topSpeedSplit.ariaLabel}>{topSpeedSplit.label}</span>{/if}</dd>
      </div>
      <div>
        <dt>Average speed ({speedUnit.label})</dt>
        <dd>{formatSpeed(summary.average_speed_mps, speedUnit.factor)}{#if avgSpeedSplit}<span class="split-badge {avgSpeedSplit.tone}" aria-label={avgSpeedSplit.ariaLabel}>{avgSpeedSplit.label}</span>{/if}</dd>
      </div>
      <div>
        <dt>Peak slip</dt>
        <dd>{formatDecimal(summary.peak_combined_slip, 4)}{#if peakSlipSplit}<span class="split-badge {peakSlipSplit.tone}" aria-label={peakSlipSplit.ariaLabel}>{peakSlipSplit.label}</span>{/if}</dd>
      </div>
      <div>
        <dt>Limiter samples</dt>
        <dd>{formatInteger(summary.limiter_samples)}{#if limiterSplit}<span class="split-badge {limiterSplit.tone}" aria-label={limiterSplit.ariaLabel}>{limiterSplit.label}</span>{/if}</dd>
      </div>
      <div>
        <dt>Bottoming events</dt>
        <dd>{formatInteger(summary.bottoming_events)}{#if bottomingSplit}<span class="split-badge {bottomingSplit.tone}" aria-label={bottomingSplit.ariaLabel}>{bottomingSplit.label}</span>{/if}</dd>
      </div>
      <div>
        <dt>Packet count</dt>
        <dd>{formatInteger(summary.packet_count)}</dd>
      </div>
      <div>
        <dt>Sequence range</dt>
        <dd>{summary.start_sequence}–{summary.end_sequence}</dd>
      </div>
    </dl>
  {:else}
    <p class="empty-state">No lap summary is available yet.</p>
  {/if}

  <section class="delta-panel" aria-label="Reference delta summary">
    <div class="delta-header">
      <h3>{selectedRange ? 'Selected section delta' : 'Full lap delta'}</h3>
      {#if hasDelta && deltaSummary}
        <span class="summary-badge">{deltaSummary.current_sample_count}/{deltaSummary.reference_sample_count} samples</span>
      {/if}
    </div>

    {#if hasDelta && deltaSummary}
      <dl class="delta-grid">
        <div>
          <dt>Time delta</dt>
          <dd>{formatMillisecondsAsSeconds(deltaSummary.time_delta_ms)}</dd>
        </div>
        <div>
          <dt>Avg speed delta ({speedUnit.label})</dt>
          <dd>{formatSignedSpeed(deltaSummary.average_speed_delta_mps, speedUnit.factor)}</dd>
        </div>
        <div>
          <dt>Max gain</dt>
          <dd>{formatMillisecondsAsSeconds(-deltaSummary.max_gain_ms)}</dd>
        </div>
        <div>
          <dt>Max loss</dt>
          <dd>{formatMillisecondsAsSeconds(deltaSummary.max_loss_ms)}</dd>
        </div>
        <div>
          <dt>Compared samples</dt>
          <dd>{formatInteger(deltaSummary.current_sample_count)}</dd>
        </div>
        <div>
          <dt>Reference samples</dt>
          <dd>{formatInteger(deltaSummary.reference_sample_count)}</dd>
        </div>
      </dl>
    {:else}
      <p class="empty-state">No reference delta is available for this lap and scope.</p>
    {/if}
  </section>
</section>

<style>
  .lap-breakdown {
    border: 1px solid #27272a;
    border-radius: 1rem;
    display: grid;
    gap: 0.75rem;
    padding: 1rem;
  }

  h3,
  .empty-state {
    margin: 0;
  }

  h3 {
    font-size: 0.95rem;
  }

  .summary-badge {
    background: #1f1f23;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    color: #d4d4d8;
    font-size: 0.85rem;
    padding: 0.2rem 0.6rem;
  }

  .track-summary {
    align-items: center;
    background: #1f1f23;
    border: 1px solid #27272a;
    border-radius: 0.9rem;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
    padding: 0.75rem;
  }

  .track-summary-label {
    color: #a1a1aa;
    font-size: 0.85rem;
  }

  .track-change-button {
    background: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 999px;
    color: #f4f4f5;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 700;
    min-width: 0;
    overflow: hidden;
    padding: 0.35rem 0.7rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .track-change-button:hover,
  .track-change-button:focus-visible {
    background: #3f3f46;
  }

  dl {
    display: grid;
    gap: 0.6rem;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    margin: 0;
  }

  dl div {
    background: #1f1f23;
    border: 1px solid #27272a;
    border-radius: 0.9rem;
    padding: 0.75rem;
  }

  dt {
    color: #a1a1aa;
    font-size: 0.85rem;
  }

  dd {
    font-size: 1.1rem;
    font-weight: 600;
    margin: 0.35rem 0 0;
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.35rem;
  }

  .split-badge {
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.15rem 0.45rem;
    white-space: nowrap;
  }

  .split-badge.better {
    background: #14532d;
    color: #4ade80;
  }

  .split-badge.worse {
    background: #450a0a;
    color: #f87171;
  }

  .split-badge.neutral {
    background: #27272a;
    color: #a1a1aa;
  }

  .empty-state {
    color: #a1a1aa;
  }

  .delta-panel {
    border-top: 1px solid #27272a;
    display: grid;
    gap: 0.75rem;
    padding-top: 0.75rem;
  }

  .delta-header {
    align-items: center;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
  }

  .delta-grid {
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  }
</style>
