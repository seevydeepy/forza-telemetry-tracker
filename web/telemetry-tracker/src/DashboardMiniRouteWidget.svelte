<script lang="ts">
  import DashboardCard from './DashboardCard.svelte';
  import { iconPaths } from './Icon.svelte';
  import { miniRouteBounds, projectMiniRoutePoint } from './dashboardGeometry';
  import type { LiveSample } from './types';

  export let samples: LiveSample[] = [];
  export let currentSample: LiveSample | null = null;

  const width = 220;
  const height = 130;
  const carIndicatorSize = 24;
  const carIndicatorViewBoxWidth = 960;
  const carIndicatorViewBoxCenterX = 480;
  const carIndicatorViewBoxCenterY = -480;

  function finiteNumber(value: number | null | undefined): number | null {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }

  function currentRouteHeadingDegrees(points: { x: number; y: number }[]): number {
    if (points.length < 2) return 0;
    const latest = points[points.length - 1];
    for (let index = points.length - 2; index >= 0; index -= 1) {
      const candidate = points[index];
      const dx = latest.x - candidate.x;
      const dy = latest.y - candidate.y;
      if (dx * dx + dy * dy > 0.0001) {
        return (Math.atan2(dx, -dy) * 180) / Math.PI;
      }
    }
    return 0;
  }

  $: bounds = miniRouteBounds(samples);
  $: routePoints = bounds ? samples.map((sample) => projectMiniRoutePoint(sample, bounds, width, height)).filter(Boolean) as { x: number; y: number }[] : [];
  $: routePath = routePoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' ');
  $: currentPoint = currentSample && bounds ? projectMiniRoutePoint(currentSample, bounds, width, height) : null;
  $: currentYaw = finiteNumber(currentSample?.yaw);
  $: currentRotationDegrees = currentYaw !== null ? (currentYaw * 180) / Math.PI : currentRouteHeadingDegrees(routePoints);
  $: currentIndicatorTransform = currentPoint
    ? `translate(${currentPoint.x.toFixed(1)} ${currentPoint.y.toFixed(1)}) rotate(${currentRotationDegrees.toFixed(1)}) scale(${(carIndicatorSize / carIndicatorViewBoxWidth).toFixed(4)}) translate(${-carIndicatorViewBoxCenterX} ${-carIndicatorViewBoxCenterY})`
    : '';
</script>

<DashboardCard title="Mini route" subtitle={`${samples.length} samples`}>
  {#if routePoints.length > 1}
    <svg class="mini-route" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Mini route">
      <path d={routePath} />
      <circle cx={routePoints[0].x} cy={routePoints[0].y} r="4" class="start" />
      <circle cx={routePoints[routePoints.length - 1].x} cy={routePoints[routePoints.length - 1].y} r="4" class="finish" />
      {#if currentPoint}
        <g class="current" transform={currentIndicatorTransform} aria-label="Current player position">
          {#each iconPaths.navigation.paths as iconPath}
            <path d={iconPath} />
          {/each}
        </g>
      {/if}
    </svg>
  {:else}
    <p class="empty">Route appears after at least two samples are available.</p>
  {/if}
</DashboardCard>

<style>
  .mini-route {
    background: #050505;
    border: 1px solid #27272a;
    border-radius: 0.75rem;
    display: block;
    height: 100%;
    min-height: 11rem;
    width: 100%;
  }

  path {
    fill: none;
    stroke: #22c55e;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 3;
  }

  circle {
    stroke: #f4f4f5;
    stroke-width: 2;
  }

  .start {
    fill: #22c55e;
  }

  .finish {
    fill: #f59e0b;
  }

  .current {
    color: #e3e3e3;
    fill: currentColor;
    stroke: none;
  }

  .current path {
    fill: currentColor;
    stroke: none;
  }

  .empty {
    color: var(--text-secondary);
    margin: 0;
  }
</style>
