import { describe, expect, it } from 'vitest';
import {
  parseTilePath,
  projectWorldPoint,
  tileWorldBounds,
  visibleWorldMapTiles,
  type CanvasProjection,
  type WorldMapCalibration
} from './worldMap';

const calibration: WorldMapCalibration = {
  worldOriginX: -12548,
  worldOriginZ: -11281,
  worldSize: 22035,
  tileSize: 1024,
  maxZoom: 3
};

const projection: CanvasProjection = {
  minX: -12548,
  maxX: 9487,
  minZ: -11281,
  maxZ: 10754,
  scale: 1,
  offsetX: 0,
  offsetY: 0
};

describe('world map projection helpers', () => {
  it('parses manifest tile paths', () => {
    expect(parseTilePath('3/4/4.png')).toEqual({ z: 3, x: 4, y: 4 });
    expect(() => parseTilePath('3-4-4.swatchbin')).toThrow(/Invalid/);
  });

  it('spans the full canonical world extent at zoom zero', () => {
    expect(tileWorldBounds(0, 0, 0, calibration)).toEqual({
      west: -12548,
      east: 9487,
      north: 10754,
      south: -11281
    });
  });

  it('spans one eighth of the world for zoom three tiles', () => {
    const bounds = tileWorldBounds(3, 4, 4, calibration);
    const tileSizeWorld = calibration.worldSize / 8;

    expect(bounds.east - bounds.west).toBeCloseTo(tileSizeWorld);
    expect(bounds.north - bounds.south).toBeCloseTo(tileSizeWorld);
  });

  it('matches the canvas telemetry projection formula', () => {
    expect(projectWorldPoint(0, 0, projection)).toEqual({
      x: 12548,
      y: 10754
    });
  });

  it('returns highest zoom visible tiles with projected destination rectangles', () => {
    const tiles = [
      { z: 0, x: 0, y: 0, path: '0/0/0.png' },
      { z: 1, x: 0, y: 0, path: '1/0/0.png' },
      { z: 1, x: 1, y: 1, path: '1/1/1.png' }
    ];

    const visible = visibleWorldMapTiles(tiles, calibration, projection, {
      left: 0,
      top: 0,
      right: 900,
      bottom: 560
    });

    expect(visible.map((tile) => tile.path)).toEqual(['1/0/0.png', '1/1/1.png']);
    expect(visible[0].dest.width).toBeCloseTo(calibration.worldSize / 2);
    expect(visible[0].dest.height).toBeCloseTo(calibration.worldSize / 2);
  });
});
