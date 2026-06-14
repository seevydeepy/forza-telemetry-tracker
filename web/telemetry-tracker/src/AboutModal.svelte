<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import {
    checkForUpdates,
    clearAppUpdateToken,
    fetchAppAbout,
    saveAppUpdateToken
  } from './api';
  import AppModal from './AppModal.svelte';
  import type {
    AppAboutPayload,
    AppAboutUpdates,
    AppUpdateCheckResponse,
    ToastLevel
  } from './types';

  const dispatch = createEventDispatcher<{
    close: void;
    toast: { level: ToastLevel; message: string; sticky?: boolean };
  }>();

  let about: AppAboutPayload | null = null;
  let aboutLoading = true;
  let aboutError: string | null = null;
  let checkResult: AppUpdateCheckResponse | null = null;
  let checking = false;
  let updateError: string | null = null;
  let tokenPanelOpen = false;
  let tokenInput = '';
  let tokenBusy = false;

  $: updates = about?.updates ?? null;
  $: updateAvailable = checkResult?.status === 'update_available';
  $: latestVersion = checkResult?.latest_version ?? null;
  $: releaseUrl = updateAvailable ? checkResult?.release_url ?? null : null;
  $: updateSupported = Boolean(updates?.supported);
  $: checkDisabled = !updateSupported || checking;

  function toast(level: ToastLevel, message: string, sticky = false) {
    dispatch('toast', { level, message, sticky });
  }

  function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error && error.message ? error.message : fallback;
  }

  function describeTokenSource(source: AppAboutUpdates['token_source']): string {
    if (source === 'environment') return 'environment variable';
    if (source === 'credential_manager') return 'Windows Credential Manager';
    return 'unknown source';
  }

  function formatDate(value: string | null): string {
    if (!value) return 'Not recorded';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.valueOf())) return value;
    return parsed.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    });
  }

  async function loadAbout() {
    aboutLoading = true;
    aboutError = null;
    try {
      about = await fetchAppAbout();
    } catch (error) {
      aboutError = errorMessage(error, 'Could not load installed version information.');
    } finally {
      aboutLoading = false;
    }
  }

  async function runUpdateCheck() {
    if (checkDisabled) return;
    checking = true;
    updateError = null;
    try {
      checkResult = await checkForUpdates(true);
    } catch (error) {
      updateError = errorMessage(error, 'Could not contact GitHub Releases.');
    } finally {
      checking = false;
    }
  }

  function applyTokenStatus(next: Partial<AppAboutUpdates>) {
    if (!about) return;
    about = {
      ...about,
      updates: {
        ...about.updates,
        ...next
      }
    };
    checkResult = null;
  }

  async function saveToken() {
    const token = tokenInput.trim();
    if (!token || tokenBusy) return;
    tokenBusy = true;
    try {
      const status = await saveAppUpdateToken(token);
      tokenInput = '';
      tokenPanelOpen = false;
      applyTokenStatus(status);
      toast('success', status.message || 'GitHub token saved.');
    } catch {
      toast('error', 'Could not save GitHub token.');
    } finally {
      tokenBusy = false;
    }
  }

  async function clearToken() {
    if (tokenBusy) return;
    tokenBusy = true;
    try {
      const status = await clearAppUpdateToken();
      applyTokenStatus(status);
      toast('success', status.message || 'GitHub token removed.');
    } catch {
      toast('error', 'Could not remove GitHub token.');
    } finally {
      tokenBusy = false;
    }
  }

  onMount(() => {
    void loadAbout();
  });
</script>

<AppModal title="About" on:close={() => dispatch('close')}>
  <section class="about-modal" aria-label="About Forza Telemetry Tracker">
    {#if aboutLoading}
      <p class="modal-state" aria-live="polite">Loading version information…</p>
    {:else if aboutError}
      <div class="modal-state modal-state-error" role="alert">
        <strong>Unable to load About information</strong>
        <span>{aboutError}</span>
        <button type="button" class="secondary-action about-inline-action" on:click={loadAbout}>Retry</button>
      </div>
    {:else if about}
      <header class="about-title-block">
        <div>
          <h3>{about.name}</h3>
          <p>Installed version {about.version}</p>
        </div>
      </header>

      <dl class="about-detail-grid">
        <div>
          <dt>Release date</dt>
          <dd>{formatDate(about.release_date)}</dd>
        </div>
        <div>
          <dt>Channel</dt>
          <dd>{about.channel}</dd>
        </div>
        <div>
          <dt>Repository</dt>
          <dd>{about.repository}</dd>
        </div>
        <div>
          <dt>Build type</dt>
          <dd>{about.packaged ? 'Packaged desktop app' : 'Development run'}</dd>
        </div>
        {#if about.git_sha}
          <div>
            <dt>Git SHA</dt>
            <dd class="about-mono">{about.git_sha}</dd>
          </div>
        {/if}
      </dl>

      <section class="about-section" aria-label="Application updates">
        <header class="about-section-heading">
          <h3>Updates</h3>
          <p>Stable releases are checked against GitHub Releases.</p>
        </header>

        <dl class="about-detail-grid compact">
          <div>
            <dt>Update channel</dt>
            <dd>{updates?.supported ? 'Supported' : 'Not available'}</dd>
          </div>
          <div>
            <dt>Release access</dt>
            <dd>
              {#if updates?.token_configured}
                Token configured ({describeTokenSource(updates.token_source)})
              {:else}
                No private token configured
              {/if}
            </dd>
          </div>
        </dl>

        {#if !updates?.supported}
          <p class="settings-hint">
            Update checks are enabled only for packaged stable SemVer builds.
          </p>
        {:else}
          {#if checkResult}
            <div class="update-result" data-status={checkResult.status} role="status" aria-live="polite">
              <strong>
                {#if checkResult.status === 'update_available'}
                  Update {checkResult.latest_version} is available
                {:else if checkResult.status === 'up_to_date'}
                  You are up to date
                {:else}
                  Update check failed
                {/if}
              </strong>
              <span>{checkResult.message}</span>
              {#if checkResult.release_url}
                <a href={checkResult.release_url} target="_blank" rel="noreferrer">Open GitHub release</a>
              {/if}
            </div>
          {/if}

          {#if updateError}
            <p class="about-error-text" role="alert">{updateError}</p>
          {/if}

          <div class="modal-actions">
            {#if updateAvailable}
              {#if releaseUrl}
                <a class="primary-action release-action" href={releaseUrl} target="_blank" rel="noreferrer">
                  Open release {latestVersion}
                </a>
              {:else}
                <button type="button" class="primary-action" disabled>Release link unavailable</button>
              {/if}
            {:else}
              <button type="button" class="primary-action" disabled={checkDisabled} on:click={runUpdateCheck}>
                {checking ? 'Checking…' : 'Check for updates'}
              </button>
            {/if}
          </div>

          {#if updateAvailable}
            <p class="settings-hint">
              Download and run the installer from GitHub Releases when you are ready.
            </p>
          {/if}

          {#if !updates?.token_configured && updates?.token_storage_available}
            <div class="token-card">
              <button
                type="button"
                class="link-action"
                aria-expanded={tokenPanelOpen}
                on:click={() => (tokenPanelOpen = !tokenPanelOpen)}
              >
                {tokenPanelOpen ? 'Hide token setup' : 'Configure private GitHub token'}
              </button>
              {#if tokenPanelOpen}
                <form class="token-form" on:submit|preventDefault={saveToken}>
                  <label>
                    <span>Fine-grained PAT with repository Contents: read</span>
                    <input
                      type="password"
                      bind:value={tokenInput}
                      autocomplete="off"
                      spellcheck="false"
                      placeholder="github_pat_…"
                      disabled={tokenBusy}
                    />
                  </label>
                  <button type="submit" class="secondary-action" disabled={!tokenInput.trim() || tokenBusy}>
                    {tokenBusy ? 'Saving…' : 'Save token'}
                  </button>
                </form>
              {/if}
            </div>
          {:else if updates?.token_configured && updates.token_source === 'credential_manager'}
            <button type="button" class="secondary-action about-inline-action" disabled={tokenBusy} on:click={clearToken}>
              {tokenBusy ? 'Removing…' : 'Remove stored token'}
            </button>
          {/if}
        {/if}
      </section>
    {/if}
  </section>
</AppModal>

<style>
  .about-modal {
    display: grid;
    gap: 1rem;
    max-width: 42rem;
    min-width: min(34rem, 78vw);
  }

  .modal-state,
  .about-detail-grid,
  .update-result,
  .token-card {
    background: rgb(255 255 255 / 6%);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.85rem;
  }

  .modal-state {
    color: var(--text-primary);
    display: grid;
    gap: 0.35rem;
    margin: 0;
    padding: 1rem;
  }

  .modal-state-error,
  .about-error-text {
    color: #fecaca;
  }

  .about-title-block {
    align-items: center;
    display: flex;
    justify-content: space-between;
  }

  .about-title-block h3,
  .about-title-block p,
  .about-section-heading h3,
  .about-section-heading p {
    margin: 0;
  }

  .about-title-block h3 {
    color: var(--text-primary);
    font-size: 1.25rem;
  }

  .about-title-block p,
  .about-section-heading p,
  .settings-hint {
    color: var(--text-secondary);
  }

  .about-detail-grid {
    display: grid;
    margin: 0;
    overflow: hidden;
  }

  .about-detail-grid > div {
    align-items: start;
    display: grid;
    gap: 1rem;
    grid-template-columns: minmax(9rem, 0.75fr) minmax(0, 1fr);
    padding: 0.65rem 0.85rem;
  }

  .about-detail-grid > div + div {
    border-top: 1px solid var(--panel-border-muted);
  }

  .about-detail-grid dt {
    color: var(--text-secondary);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .about-detail-grid dd {
    color: var(--text-primary);
    margin: 0;
    overflow-wrap: anywhere;
    text-align: right;
  }

  .about-detail-grid.compact dd {
    font-size: 0.88rem;
  }

  .about-mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  }

  .about-section {
    border-top: 1px solid var(--panel-border-muted);
    display: grid;
    gap: 0.8rem;
    padding-top: 1rem;
  }

  .about-section-heading {
    display: grid;
    gap: 0.2rem;
  }

  .about-section-heading h3 {
    color: var(--text-primary);
    font-size: 1rem;
  }

  .update-result {
    display: grid;
    gap: 0.3rem;
    padding: 0.75rem;
  }

  .update-result[data-status='update_available'] {
    border-color: rgb(34 197 94 / 55%);
  }

  .update-result[data-status='error'],
  .update-result[data-status='not_configured'],
  .update-result[data-status='unsupported'] {
    border-color: rgb(239 68 68 / 55%);
  }

  .update-result strong {
    color: var(--text-primary);
  }

  .update-result span {
    color: var(--text-secondary);
  }

  .update-result a,
  .link-action {
    color: #7dd3fc;
    text-decoration: underline;
    text-underline-offset: 0.16rem;
  }

  .about-error-text {
    margin: 0;
  }

  .about-inline-action {
    justify-self: start;
  }

  .release-action {
    text-decoration: none;
  }

  .token-card {
    display: grid;
    gap: 0.75rem;
    padding: 0.8rem;
  }

  .link-action {
    background: none;
    border: 0;
    cursor: pointer;
    justify-self: start;
    padding: 0;
  }

  .token-form {
    display: grid;
    gap: 0.75rem;
  }

  .token-form label {
    color: var(--text-secondary);
    display: grid;
    gap: 0.35rem;
    font-size: 0.82rem;
  }

  .token-form input {
    background: rgb(24 24 27 / 86%);
    border: 1px solid var(--panel-border-muted);
    border-radius: 0.6rem;
    color: var(--text-primary);
    padding: 0.55rem 0.65rem;
  }

  @media (max-width: 42rem) {
    .about-modal {
      min-width: 0;
    }

    .about-detail-grid > div {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }

    .about-detail-grid dd {
      text-align: left;
    }
  }
</style>
