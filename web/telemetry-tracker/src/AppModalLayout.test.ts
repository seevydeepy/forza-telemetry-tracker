import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const appCss = readFileSync(join(process.cwd(), 'src', 'app.css'), 'utf8');

function cssBlock(selector: string) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = appCss.match(new RegExp(`${escapedSelector}\\s*\\{(?<body>[^}]*)\\}`, 'm'));
  return match?.groups?.body ?? '';
}

describe('AppModal layout CSS', () => {
  it('keeps overflowing modal content scrollable inside the capped panel', () => {
    expect(cssBlock('.modal-panel')).toContain('display: flex;');
    expect(cssBlock('.modal-panel')).toContain('flex-direction: column;');

    const bodyCss = cssBlock('.modal-body');
    expect(bodyCss).toContain('flex: 1 1 auto;');
    expect(bodyCss).toContain('min-height: 0;');
    expect(bodyCss).toContain('overflow: auto;');
  });
});
