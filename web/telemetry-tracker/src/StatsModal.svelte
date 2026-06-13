<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import AppModal from './AppModal.svelte';
  import * as dashboardFormat from './dashboardFormat';
  import type { StatsFavourite, StatsSummary, UnitSystem } from './types';

  export let stats: StatsSummary | null = null;
  export let unitSystem: UnitSystem = 'imperial';
  export let loading = false;
  export let error: string | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
  }>();

  const MISSING = '\u2014';

  type StatCard = {
    label: string;
    value: string;
    detail?: string;
  };

  function lapCountText(count: number): string {
    return `${dashboardFormat.formatNumber(count)} ${count === 1 ? 'lap' : 'laps'}`;
  }

  function favouriteValue(favourite: StatsFavourite | null): string {
    return favourite?.value?.trim() || MISSING;
  }

  function favouriteDetail(favourite: StatsFavourite | null): string | undefined {
    return favourite ? lapCountText(favourite.lap_count) : undefined;
  }

  function favouriteTrackDetail(favourite: StatsFavourite | null): string | undefined {
    if (!favourite) return undefined;
    return [favourite.detail?.trim(), lapCountText(favourite.lap_count)].filter(Boolean).join(' · ');
  }

  function formatRacingTime(valueMs: number | null | undefined): string {
    if (typeof valueMs !== 'number' || !Number.isFinite(valueMs)) return MISSING;

    const totalSeconds = Math.max(0, Math.floor(valueMs / 1000));
    if (totalSeconds === 0) return '0s';

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
      return `${hours}h ${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`;
    }

    if (minutes > 0) {
      return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
    }

    return `${seconds}s`;
  }

  function buildCards(summary: StatsSummary, speedUnitSystem: UnitSystem): StatCard[] {
    return [
      {
        label: 'Laps recorded',
        value: dashboardFormat.formatNumber(summary.laps_recorded)
      },
      {
        label: 'Sessions created',
        value: dashboardFormat.formatNumber(summary.sessions_created)
      },
      {
        label: 'Tracks driven',
        value: dashboardFormat.formatNumber(summary.tracks_driven)
      },
      {
        label: 'Cars driven',
        value: dashboardFormat.formatNumber(summary.cars_driven)
      },
      {
        label: 'Max speed',
        value: dashboardFormat.formatSpeed(summary.max_speed_mps, speedUnitSystem)
      },
      {
        label: 'Favourite car',
        value: favouriteValue(summary.favourite_car),
        detail: favouriteDetail(summary.favourite_car)
      },
      {
        label: 'Favourite track',
        value: favouriteValue(summary.favourite_track),
        detail: favouriteTrackDetail(summary.favourite_track)
      },
      {
        label: 'Favourite PI class',
        value: favouriteValue(summary.favourite_pi_class),
        detail: favouriteDetail(summary.favourite_pi_class)
      },
      {
        label: 'Favoured drive',
        value: favouriteValue(summary.favoured_drive),
        detail: favouriteDetail(summary.favoured_drive)
      },
      {
        label: 'Lifetime Telemetry Recorded',
        value: formatRacingTime(summary.time_spent_racing_ms)
      }
    ];
  }

  $: cards = stats ? buildCards(stats, unitSystem) : [];
</script>

<AppModal title="Stats" on:close={() => dispatch('close')}>
  <section class="stats-modal" aria-label="Stats summary">
    {#if loading}
      <p class="stats-modal-state" aria-live="polite">Loading stats…</p>
    {:else if error}
      <div class="stats-modal-state stats-modal-error" role="alert">
        <strong>Unable to load stats</strong>
        <span>{error}</span>
      </div>
    {:else if !stats}
      <p class="stats-modal-state">No recorded stats yet.</p>
    {:else}
      <div class="stats-card-grid" aria-label="Recorded stats cards">
        {#each cards as card}
          <article class="stats-card" role="group" aria-label={card.label}>
            <h3>{card.label}</h3>
            <p class="stats-card-value">{card.value}</p>
            {#if card.detail}
              <p class="stats-card-detail">{card.detail}</p>
            {/if}
          </article>
        {/each}
      </div>
    {/if}
  </section>
</AppModal>

<style>
  .stats-modal {
    display: grid;
    gap: 1rem;
    max-width: 54rem;
    min-width: min(32rem, 78vw);
  }

  .stats-modal-state {
    background: rgb(255 255 255 / 6%);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.85rem;
    color: var(--text-primary);
    margin: 0;
    padding: 1rem;
  }

  .stats-modal-error {
    color: #fecaca;
    display: grid;
    gap: 0.35rem;
  }

  .stats-modal-error span {
    color: #fca5a5;
  }

  .stats-card-grid {
    display: grid;
    gap: 0.75rem;
    grid-template-columns: repeat(auto-fit, minmax(11.5rem, 1fr));
  }

  .stats-card {
    background: rgb(255 255 255 / 6%);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.85rem;
    display: grid;
    gap: 0.35rem;
    min-width: 0;
    padding: 0.9rem;
  }

  .stats-card h3 {
    color: var(--text-secondary);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    margin: 0;
    text-transform: uppercase;
  }

  .stats-card-value {
    color: var(--text-primary);
    font-size: clamp(1.25rem, 2.5vw, 1.75rem);
    font-weight: 760;
    line-height: 1.15;
    margin: 0;
    overflow-wrap: anywhere;
  }

  .stats-card-detail {
    color: var(--text-secondary);
    font-size: 0.88rem;
    margin: 0;
    overflow-wrap: anywhere;
  }

  @media (max-width: 42rem) {
    .stats-modal {
      min-width: 0;
    }
  }
</style>
