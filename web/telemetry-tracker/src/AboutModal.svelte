<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { checkForUpdates, fetchAppAbout } from './api';
  import AppModal from './AppModal.svelte';
  import type {
    AppAboutPayload,
    AppUpdateCheckResponse,
    ToastLevel
  } from './types';

  const dispatch = createEventDispatcher<{
    close: void;
    toast: { level: ToastLevel; message: string; sticky?: boolean };
  }>();
  const KOFI_URL = 'https://ko-fi.com/Z4I021C66X';
  const KOFI_BUTTON_IMAGE_URL = 'https://storage.ko-fi.com/cdn/kofi5.png?v=3';

  let about: AppAboutPayload | null = null;
  let aboutLoading = true;
  let aboutError: string | null = null;
  let checkResult: AppUpdateCheckResponse | null = null;
  let checking = false;
  let updateError: string | null = null;

  $: updates = about?.updates ?? null;
  $: updateAvailable = checkResult?.status === 'update_available';
  $: latestVersion = checkResult?.latest_version ?? null;
  $: releaseUrl = updateAvailable ? checkResult?.release_url ?? null : null;
  $: updateSupported = Boolean(updates?.supported);
  $: checkDisabled = !updateSupported || checking;

  function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error && error.message ? error.message : fallback;
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
        <a class="kofi-link" href={KOFI_URL} target="_blank" rel="noreferrer">
          <img src={KOFI_BUTTON_IMAGE_URL} alt="Support Forza Telemetry Tracker on Ko-fi" />
        </a>
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
            <dd>{updates?.release_access === 'public' ? 'Public GitHub Releases' : 'Unavailable'}</dd>
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
  .update-result {
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
    flex-wrap: wrap;
    gap: 0.75rem;
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

  .kofi-link {
    align-items: center;
    background: #13c3ff;
    border: 1px solid rgb(255 255 255 / 38%);
    border-radius: 0.5rem;
    display: inline-flex;
    flex: 0 0 auto;
    line-height: 1;
    min-height: 2.5rem;
    overflow: hidden;
    padding: 0;
    text-decoration: none;
  }

  .kofi-link:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  .kofi-link img {
    display: block;
    height: 2.5rem;
    width: auto;
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
  .update-result[data-status='unsupported'] {
    border-color: rgb(239 68 68 / 55%);
  }

  .update-result strong {
    color: var(--text-primary);
  }

  .update-result span {
    color: var(--text-secondary);
  }

  .update-result a {
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
