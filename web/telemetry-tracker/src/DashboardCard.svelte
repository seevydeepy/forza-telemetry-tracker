<script lang="ts">
  export let title: string;
  export let subtitle = '';
</script>

<section class="dashboard-card" aria-label={title}>
  <header class="dashboard-card__header">
    <h2>{title}</h2>
    {#if subtitle}
      <span>{subtitle}</span>
    {/if}
  </header>
  <div class="dashboard-card__body">
    <slot />
  </div>
</section>

<style>
  .dashboard-card {
    background: var(--canvas-overlay-panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 1rem;
    box-shadow: 0 16px 40px rgb(0 0 0 / 24%);
    color: var(--text-primary);
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 0;
    overflow: hidden;
  }

  .dashboard-card__header {
    align-items: baseline;
    border-bottom: 1px solid var(--panel-border-muted);
    display: flex;
    gap: 0.75rem;
    justify-content: space-between;
    min-width: 0;
    padding: 0.75rem 0.85rem;
  }

  .dashboard-card__header h2 {
    font-size: 0.9rem;
    margin: 0;
  }

  .dashboard-card__header span {
    color: var(--text-secondary);
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dashboard-card__body {
    min-height: 0;
    overflow: auto;
    padding: 0.85rem;
  }
</style>
