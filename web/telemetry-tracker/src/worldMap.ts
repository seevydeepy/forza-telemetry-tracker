import type { WorldMapManifestTile } from './types';

export interface CanvasProjection {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  scale: number;
  offsetX: number;
  offsetY: number;
}

export interface WorldMapCalibration {
  worldOriginX: number;
  worldOriginZ: number;
  worldSize: number;
  tileSize: number;
  maxZoom: number;
}

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface ProjectedWorldMapTile extends WorldMapManifestTile {
  bounds: {
    west: number;
    east: number;
    north: number;
    south: number;
  };
  dest: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export function projectWorldPoint(x: number, z: number, projection: CanvasProjection) {
  return {
    x: projection.offsetX + (x - projection.minX) * projection.scale,
    y: projection.offsetY + (projection.maxZ - z) * projection.scale
  };
}

export function tileWorldBounds(z: number, x: number, y: number, calibration: WorldMapCalibration) {
  const count = 2 ** z;
  const u0 = x / count;
  const u1 = (x + 1) / count;
  const v0 = y / count;
  const v1 = (y + 1) / count;
  const west = calibration.worldOriginX + u0 * calibration.worldSize;
  const east = calibration.worldOriginX + u1 * calibration.worldSize;
  const north = calibration.worldOriginZ + (1 - v0) * calibration.worldSize;
  const south = calibration.worldOriginZ + (1 - v1) * calibration.worldSize;
  return { west, east, north, south };
}

export function parseTilePath(path: string): { z: number; x: number; y: number } {
  const match = /^(\d+)\/(\d+)\/(\d+)\.png$/i.exec(path.trim());
  if (!match) {
    throw new Error(`Invalid world map tile path: ${path}`);
  }
  return {
    z: Number(match[1]),
    x: Number(match[2]),
    y: Number(match[3])
  };
}

export function projectedTileRect(
  tile: WorldMapManifestTile,
  calibration: WorldMapCalibration,
  projection: CanvasProjection
): ProjectedWorldMapTile {
  const bounds = tileWorldBounds(tile.z, tile.x, tile.y, calibration);
  const topLeft = projectWorldPoint(bounds.west, bounds.north, projection);
  const bottomRight = projectWorldPoint(bounds.east, bounds.south, projection);
  return {
    ...tile,
    bounds,
    dest: {
      x: Math.min(topLeft.x, bottomRight.x),
      y: Math.min(topLeft.y, bottomRight.y),
      width: Math.abs(bottomRight.x - topLeft.x),
      height: Math.abs(bottomRight.y - topLeft.y)
    }
  };
}

export function highestZoomTiles(tiles: WorldMapManifestTile[]): WorldMapManifestTile[] {
  const maxZoom = Math.max(...tiles.map((tile) => tile.z), 0);
  return tiles.filter((tile) => tile.z === maxZoom);
}

export function visibleWorldMapTiles(
  tiles: WorldMapManifestTile[],
  calibration: WorldMapCalibration,
  projection: CanvasProjection,
  viewport: Rect
): ProjectedWorldMapTile[] {
  return highestZoomTiles(tiles)
    .map((tile) => projectedTileRect(tile, calibration, projection))
    .filter((tile) =>
      rectsIntersect(
        expandRect(viewport, Math.max(tile.dest.width, tile.dest.height)),
        destRect(tile.dest)
      )
    );
}

export function rectsIntersect(left: Rect, right: Rect): boolean {
  return left.left <= right.right && left.right >= right.left && left.top <= right.bottom && left.bottom >= right.top;
}

function expandRect(rect: Rect, amount: number): Rect {
  return {
    left: rect.left - amount,
    top: rect.top - amount,
    right: rect.right + amount,
    bottom: rect.bottom + amount
  };
}

function destRect(dest: { x: number; y: number; width: number; height: number }): Rect {
  return {
    left: dest.x,
    top: dest.y,
    right: dest.x + dest.width,
    bottom: dest.y + dest.height
  };
}
