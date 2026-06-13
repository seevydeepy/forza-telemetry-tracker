<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import AppModal from './AppModal.svelte';
  import type { LapSummary, TrackMatchCandidate, TrackProfile } from './types';

  export let lap: LapSummary;
  export let profiles: TrackProfile[] = [];
  export let candidates: TrackMatchCandidate[] = [];
  export let busy = false;
  export let error: string | null = null;

  const dispatch = createEventDispatcher<{
    close: void;
    assign: { profileId: string; sessionId: string; lapId: string };
  }>();

  type SuggestedProfile = {
    profile: TrackProfile;
    candidate: TrackMatchCandidate;
  };

  let search = '';
  let suggestedItems: SuggestedProfile[] = [];
  let suggestedProfileIds = new Set<string>();

  $: profileById = new Map(profiles.map((profile) => [profile.id, profile]));
  $: {
    const nextItems: SuggestedProfile[] = [];
    const nextIds = new Set<string>();
    for (const candidate of candidates) {
      const profileId = candidateProfileId(candidate);
      if (!profileId || nextIds.has(profileId)) continue;
      const profile = profileById.get(profileId);
      if (!profile) continue;
      nextIds.add(profileId);
      nextItems.push({ profile, candidate });
    }
    suggestedItems = nextItems;
    suggestedProfileIds = nextIds;
  }
  $: normalizedSearch = search.trim().toLowerCase();
  $: filteredSuggestedItems = suggestedItems.filter(({ profile }) => profileMatchesSearch(profile, normalizedSearch));
  $: filteredKnownProfiles = profiles.filter(
    (profile) => !suggestedProfileIds.has(profile.id) && profileMatchesSearch(profile, normalizedSearch)
  );
  $: lapLabel = `${lap.session_label} lap ${lap.lap_number ?? '—'}`;

  function candidateProfileId(candidate: TrackMatchCandidate): string | null {
    const trackProfileId = candidate.track_profile_id;
    if (typeof trackProfileId === 'string' && trackProfileId.length > 0) return trackProfileId;

    const assignedTrackProfileId = candidate.assigned_track_profile_id;
    if (typeof assignedTrackProfileId === 'string' && assignedTrackProfileId.length > 0) return assignedTrackProfileId;

    return null;
  }

  function profileTitle(profile: TrackProfile): string {
    return `${profile.name} — ${profile.layout}`;
  }

  function profileMatchesSearch(profile: TrackProfile, query: string): boolean {
    if (!query) return true;
    return `${profile.name} ${profile.layout}`.toLowerCase().includes(query);
  }

  function candidateMeta(candidate: TrackMatchCandidate): string {
    const parts: string[] = [];
    if (typeof candidate.confidence === 'string' && candidate.confidence.trim()) {
      parts.push(candidate.confidence);
    }
    if (typeof candidate.score === 'number' && Number.isFinite(candidate.score)) {
      parts.push(`${Math.round(candidate.score * 100)}% match`);
    }
    return parts.join(' · ');
  }

  function assign(profile: TrackProfile) {
    if (busy) return;
    dispatch('assign', { profileId: profile.id, sessionId: lap.session_id, lapId: lap.id });
  }
</script>

<AppModal title="Change lap track" on:close={() => dispatch('close')}>
  <section class="track-assignment-picker" aria-label="Lap track assignment">
    <p class="lap-context">Assign a known track to {lapLabel}.</p>

    <label class="search-field">
      <span>Search known tracks</span>
      <input type="search" bind:value={search} autocomplete="off" />
    </label>

    {#if busy}
      <p class="status-message">Loading suggested tracks…</p>
    {/if}
    {#if error}
      <p class="error-message" role="alert">{error}</p>
    {/if}

    <section class="profile-section" aria-label="Suggested tracks">
      <h3>Suggested</h3>
      {#if filteredSuggestedItems.length === 0}
        <p class="empty-state">No suggested tracks match this lap.</p>
      {:else}
        <ul class="profile-list">
          {#each filteredSuggestedItems as item (item.profile.id)}
            <li>
              <div>
                <strong>{profileTitle(item.profile)}</strong>
                {#if candidateMeta(item.candidate)}
                  <small>{candidateMeta(item.candidate)}</small>
                {:else}
                  <small>Suggested for this lap</small>
                {/if}
              </div>
              <button type="button" disabled={busy} aria-label={`Assign ${profileTitle(item.profile)}`} on:click={() => assign(item.profile)}>Assign</button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="profile-section" aria-label="All known tracks">
      <h3>All known tracks</h3>
      {#if filteredKnownProfiles.length === 0}
        <p class="empty-state">No other known tracks match your search.</p>
      {:else}
        <ul class="profile-list">
          {#each filteredKnownProfiles as profile (profile.id)}
            <li>
              <div>
                <strong>{profileTitle(profile)}</strong>
                <small>{profile.source} / {profile.confidence}</small>
              </div>
              <button type="button" disabled={busy} aria-label={`Assign ${profileTitle(profile)}`} on:click={() => assign(profile)}>Assign</button>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </section>
</AppModal>

<style>
  .track-assignment-picker {
    display: grid;
    gap: 0.9rem;
    min-width: min(34rem, 80vw);
  }

  .lap-context,
  .status-message,
  .empty-state,
  small,
  label span {
    color: #a1a1aa;
  }

  .lap-context,
  .status-message,
  .empty-state,
  .error-message,
  h3 {
    margin: 0;
  }

  .search-field,
  .profile-section {
    display: grid;
    gap: 0.5rem;
  }

  input {
    background: #18181b;
    border: 1px solid #3f3f46;
    border-radius: 0.65rem;
    color: #e2e8f0;
    padding: 0.5rem 0.65rem;
  }

  .error-message {
    color: #fecaca;
  }

  .profile-list {
    display: grid;
    gap: 0.55rem;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .profile-list li {
    align-items: center;
    background: #1f1f23;
    border: 1px solid #27272a;
    border-radius: 0.75rem;
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
    padding: 0.65rem;
  }

  .profile-list li div {
    display: grid;
    gap: 0.2rem;
  }

  button {
    background: #71717a;
    border: 1px solid #71717a;
    border-radius: 0.65rem;
    color: white;
    padding: 0.45rem 0.7rem;
    white-space: nowrap;
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }
</style>
