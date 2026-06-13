import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const appCss = readFileSync(resolve(process.cwd(), 'src/app.css'), 'utf8');
const appSvelte = readFileSync(resolve(process.cwd(), 'src/App.svelte'), 'utf8');

function performanceBadgeColor(classLabel: string): string {
  const escapedClassLabel = classLabel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const selector = String.raw`\.car-info-card__performance\[data-car-performance-class='${escapedClassLabel}'\]`;
  const match = new RegExp(String.raw`${selector}\s*\{[^}]*--car-info-performance-color:\s*(#[0-9a-fA-F]{6})\s*;`, 'm').exec(appCss);
  if (!match) {
    throw new Error(`Missing performance badge color for ${classLabel}`);
  }
  return match[1].toLowerCase();
}

function hexToRgb(hex: string): [number, number, number] {
  return [Number.parseInt(hex.slice(1, 3), 16), Number.parseInt(hex.slice(3, 5), 16), Number.parseInt(hex.slice(5, 7), 16)];
}

describe('performance badge palette', () => {
  it('uses a bright green token for X class', () => {
    const color = performanceBadgeColor('X');
    const [red, green, blue] = hexToRgb(color);

    expect(color).not.toBe('#fea71d');
    expect(green).toBeGreaterThanOrEqual(210);
    expect(green - red).toBeGreaterThanOrEqual(40);
    expect(green - blue).toBeGreaterThanOrEqual(80);
  });
});


describe('global text legibility treatment', () => {
  it('adds a reusable black outline without overriding existing text or icon colors', () => {
    expect(appCss).toMatch(/--text-primary:\s*#f4f4f5\s*;/);
    expect(appCss).toMatch(/--text-secondary:\s*#a1a1aa\s*;/);
    expect(appCss).toMatch(/--text-muted:\s*#71717a\s*;/);
    expect(appCss).toMatch(/--text-outline-shadow:\s*-1px -1px 0 rgb\(0 0 0 \/ 82%\), 1px -1px 0 rgb\(0 0 0 \/ 82%\), -1px 1px 0 rgb\(0 0 0 \/ 82%\), 1px 1px 0 rgb\(0 0 0 \/ 82%\);/);
    expect(appCss).toMatch(/--icon-outline-filter:\s*drop-shadow\(-1px -1px 0 rgb\(0 0 0 \/ 82%\)\)/);
    expect(appCss).toMatch(/#app\s+:where\(:not\(svg, svg \*, canvas\)\)\s*\{\s*text-shadow:\s*var\(--text-outline-shadow\);\s*\}/s);
    expect(appCss).not.toMatch(/#app\s+:where\(:not\(svg, svg \*, canvas\)\)\s*\{[^}]*color:/s);
    expect(appCss).toMatch(/\.app-icon\s*\{[^}]*filter:\s*var\(--icon-outline-filter\);/s);
    expect(appCss).toMatch(/\.app-icon-button-primary\s*\{[^}]*color:\s*#bbf7d0;/s);
  });
});

describe('canvas top controls responsive layout', () => {
  it('stacks the top controls at the right edge below the overlap breakpoint', () => {
    expect(appSvelte).toMatch(/--canvas-top-control-stack-height:\s*2\.85rem;/);
    expect(appSvelte).toMatch(
      /@media\s*\(max-width:\s*1549px\)\s*\{[\s\S]*\.floating-top-center\s*\{[\s\S]*right:\s*var\(--canvas-floating-margin\);[\s\S]*transform:\s*none;[\s\S]*\.floating-top-right\s*\{[\s\S]*flex-direction:\s*column-reverse;[\s\S]*top:\s*calc\(var\(--canvas-floating-margin\) \+ var\(--canvas-top-control-stack-height\) \+ var\(--canvas-top-control-stack-gap\)\);[\s\S]*transform:\s*none;/
    );
  });

  it('keeps live follow before recorder in markup so column-reverse stacks recorder above live follow', () => {
    const topRightMarkup = /<div class="floating-overlays floating-top-right">([\s\S]*?)<\/div>/.exec(appSvelte)?.[1] ?? '';

    expect(topRightMarkup.indexOf('<LiveFollowButton')).toBeGreaterThanOrEqual(0);
    expect(topRightMarkup.indexOf('<FloatingCaptureControls')).toBeGreaterThanOrEqual(0);
    expect(topRightMarkup.indexOf('<LiveFollowButton')).toBeLessThan(topRightMarkup.indexOf('<FloatingCaptureControls'));
  });
});

describe('car info card layout', () => {
  it('allows the chrome title to wrap to two lines', () => {
    expect(appCss).toMatch(/\.car-info-card__chrome-title\s*\{[^}]*-webkit-line-clamp:\s*2\s*;/s);
    expect(appCss).toMatch(/\.car-info-card__chrome-title\s*\{[^}]*overflow:\s*hidden\s*;/s);
  });
});
