import '@testing-library/jest-dom/vitest';
import { fireEvent, render, waitFor } from '@testing-library/svelte';
import { vi } from 'vitest';
import { iconPaths } from './Icon.svelte';
import { issueIconToneColors } from './issueMetadata';
import TelemetryCanvas from './TelemetryCanvas.svelte';
import type { IssueMarker, LiveSample, WorldMapTileSet } from './types';

function makeSamples(): LiveSample[] {
  return [
    {
      sequence: 1,
      received_at_ms: 1,
      game_timestamp_ms: 1,
      lap_number: 0,
      current_lap: 0,
      current_race_time: 0,
      x: 0,
      y: 0,
      z: 0,
      speed_mps: 10,
      throttle: 0,
      brake: 0,
      steer: 0,
      gear: 2
    },
    {
      sequence: 2,
      received_at_ms: 2,
      game_timestamp_ms: 2,
      lap_number: 0,
      current_lap: 0,
      current_race_time: 1,
      x: 10,
      y: 0,
      z: 5,
      speed_mps: 30,
      throttle: 0,
      brake: 255,
      steer: 0,
      gear: 3
    },
    {
      sequence: 3,
      received_at_ms: 3,
      game_timestamp_ms: 3,
      lap_number: 0,
      current_lap: 0,
      current_race_time: 2,
      x: 20,
      y: 0,
      z: 15,
      speed_mps: 80,
      throttle: 255,
      brake: 0,
      steer: 0,
      gear: 4
    }
  ];
}

function makeOverlaySamples(): LiveSample[] {
  const samples = makeSamples();
  samples[1] = {
    ...samples[1],
    combined_slip: 0,
    tire_temp_front_left: 60,
    suspension_travel_front_left: 0,
    current_rpm: 4000,
    engine_max_rpm: 8000
  };
  samples[2] = {
    ...samples[2],
    combined_slip: 1.2,
    tire_temp_front_left: 120,
    suspension_travel_front_left: 1,
    current_rpm: 8000,
    engine_max_rpm: 8000
  };
  return samples;
}

function makeSquareSamples(): LiveSample[] {
  return makeSamples().map((sample, index) => ({
    ...sample,
    x: index * 10,
    z: index * 10
  }));
}

function makeTinySamples(): LiveSample[] {
  return makeSamples().map((sample, index) => ({
    ...sample,
    x: index * 0.1,
    z: index * 0.1
  }));
}

function makeDenseSamples(): LiveSample[] {
  const base = makeSamples()[0];
  return Array.from({ length: 1001 }, (_, index) => ({
    ...base,
    sequence: index + 1,
    received_at_ms: index + 1,
    game_timestamp_ms: index + 1,
    x: (index / 1000) * 20,
    z: 0,
    speed_mps: 30
  }));
}

function makeWorldMapTileSet(id = 'fh6-brio-summer'): WorldMapTileSet {
  return {
    id,
    game: 'fh6',
    map_name: 'brio',
    season: 'summer',
    source_zip_path: `G:/FH6/media/UI/Textures/Data_Bound/${id}.zip`,
    source_zip_mtime_ms: 1_710_000_000_000,
    source_zip_size_bytes: 1024,
    cache_dir: `C:/cache/${id}`,
    tile_format: 'png',
    tile_size: 1024,
    min_zoom: 0,
    max_zoom: 0,
    world_origin_x: 0,
    world_origin_z: 0,
    world_size: 20,
    status: 'ready',
    error_message: null,
    last_built_at_ms: 1_710_000_000_500,
    updated_at_ms: 1_710_000_000_500,
    tile_url_template: `/api/map/tiles/${id}/{z}/{x}/{y}.png`,
    manifest: {
      game: 'fh6',
      map: 'brio',
      season: 'summer',
      format: 'png',
      tileSize: 1024,
      minZoom: 0,
      maxZoom: 0,
      worldOriginX: 0,
      worldOriginZ: 0,
      worldSize: 20,
      tileUrlTemplate: `/api/map/tiles/${id}/{z}/{x}/{y}.png`,
      tiles: [{ z: 0, x: 0, y: 0, path: '0/0/0.png' }]
    }
  };
}

class MockTileImage {
  static sources: string[] = [];
  onload: (() => void) | null = null;
  complete = false;
  naturalWidth = 0;
  srcValue = '';

  set src(value: string) {
    this.srcValue = value;
    MockTileImage.sources.push(value);
    this.complete = true;
    this.naturalWidth = 1024;
  }

  get src() {
    return this.srcValue;
  }
}

type IssueMarkerDetailFields = Pick<
  IssueMarker,
  'anchor_sequence' | 'issue_kind' | 'actual_value' | 'threshold_value' | 'threshold_operator' | 'value_label' | 'value_unit'
>;

function markerDetails(overrides: Partial<IssueMarkerDetailFields> = {}): IssueMarkerDetailFields {
  return {
    anchor_sequence: null,
    issue_kind: 'Rear combined slip',
    actual_value: 1.28,
    threshold_value: 1.15,
    threshold_operator: 'gte',
    value_label: 'Rear combined slip',
    value_unit: null,
    ...overrides
  };
}

function makeMarkers(): IssueMarker[] {
  return [
    {
      id: 'marker-warning',
      session_id: 'session-a',
      lap_id: 'lap-a',
      start_sequence: 2,
      end_sequence: 2,
      metric: 'brake_instability',
      severity: 'warning',
      reason: 'Brake-heavy instability',
      ruleset_version: 1,
      confidence: 0.8,
      ...markerDetails({
        anchor_sequence: 2,
        issue_kind: 'Braking instability',
        actual_value: 1.2,
        threshold_value: 1.05,
        value_label: 'Combined slip'
      })
    },
    {
      id: 'marker-critical',
      session_id: 'session-a',
      lap_id: 'lap-a',
      start_sequence: 3,
      end_sequence: 3,
      metric: 'combined_slip',
      severity: 'critical',
      reason: 'High slip',
      ruleset_version: 1,
      confidence: 0.95,
      ...markerDetails({ anchor_sequence: 3 })
    }
  ];
}

function makeOverlappingMarkers(): IssueMarker[] {
  return [
    {
      id: 'marker-info-range',
      session_id: 'session-a',
      lap_id: 'lap-a',
      start_sequence: 2,
      end_sequence: 3,
      metric: 'limiter',
      severity: 'info',
      reason: 'Limiter note',
      ruleset_version: 1,
      confidence: 0.75,
      ...markerDetails({
        anchor_sequence: 2,
        issue_kind: 'Rev limiter',
        actual_value: 0.98,
        threshold_value: 0.95,
        value_label: 'RPM ratio'
      })
    },
    {
      id: 'marker-warning-overlap',
      session_id: 'session-a',
      lap_id: 'lap-a',
      start_sequence: 2,
      end_sequence: 2,
      metric: 'brake_instability',
      severity: 'warning',
      reason: 'Brake-heavy instability',
      ruleset_version: 1,
      confidence: 0.8,
      ...markerDetails({
        anchor_sequence: 2,
        issue_kind: 'Braking instability',
        actual_value: 1.2,
        threshold_value: 1.05,
        value_label: 'Combined slip'
      })
    },
    {
      id: 'marker-critical-overlap',
      session_id: 'session-a',
      lap_id: 'lap-a',
      start_sequence: 3,
      end_sequence: 3,
      metric: 'combined_slip',
      severity: 'critical',
      reason: 'High slip',
      ruleset_version: 1,
      confidence: 0.95,
      ...markerDetails({ anchor_sequence: 2 })
    }
  ];
}

class MockPath2D {
  pathData?: string;
  moveTo = vi.fn();
  lineTo = vi.fn();

  constructor(pathData?: string) {
    this.pathData = pathData;
  }
}

function createCanvasContextMock({ shapes = false }: { shapes?: boolean } = {}) {
  const strokeStyleValues: string[] = [];
  const fillStyleValues: string[] = [];
  const fillCalls: Array<{ shape: unknown; fillStyle: string | undefined }> = [];
  const fillTextCalls: Array<{ text: string; fillStyle: string | undefined }> = [];
  const lineWidthValues: number[] = [];
  let lineWidthValue = 0;

  const context = {
    beginPath: vi.fn(),
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    lineTo: vi.fn(),
    moveTo: vi.fn(),
    restore: vi.fn(),
    rotate: vi.fn(),
    save: vi.fn(),
    scale: vi.fn(),
    stroke: vi.fn(),
    translate: vi.fn(),
    drawImage: vi.fn(),
    ...(shapes
      ? {
          arc: vi.fn(),
          fill: vi.fn((shape?: unknown) => {
            fillCalls.push({ shape, fillStyle: fillStyleValues[fillStyleValues.length - 1] });
          }),
          fillText: vi.fn((text: string) => {
            fillTextCalls.push({ text, fillStyle: fillStyleValues[fillStyleValues.length - 1] });
          }),
          strokeText: vi.fn(),
          font: '',
          textAlign: 'start',
          textBaseline: 'alphabetic'
        }
      : {}),
    globalAlpha: 1,
    lineJoin: 'round',
    lineCap: 'round'
  } as unknown as CanvasRenderingContext2D;

  Object.defineProperty(context, 'strokeStyle', {
    configurable: true,
    get: () => strokeStyleValues[strokeStyleValues.length - 1],
    set: (value: string) => {
      strokeStyleValues.push(String(value));
    }
  });

  Object.defineProperty(context, 'fillStyle', {
    configurable: true,
    get: () => fillStyleValues[fillStyleValues.length - 1],
    set: (value: string) => {
      fillStyleValues.push(String(value));
    }
  });

  Object.defineProperty(context, 'lineWidth', {
    configurable: true,
    get: () => lineWidthValue,
    set: (value: number) => {
      lineWidthValue = Number(value);
      lineWidthValues.push(lineWidthValue);
    }
  });

  return {
    context,
    clearStrokeStyles() {
      strokeStyleValues.length = 0;
    },
    getStrokeStyles() {
      return [...strokeStyleValues];
    },
    clearLineWidths() {
      lineWidthValues.length = 0;
    },
    getLineWidths() {
      return [...lineWidthValues];
    },
    clearFillStyles() {
      fillStyleValues.length = 0;
    },
    getFillCalls() {
      return [...fillCalls];
    },
    clearFillCalls() {
      fillCalls.length = 0;
    },
    getFillTextCalls() {
      return [...fillTextCalls];
    }
  };
}

describe('TelemetryCanvas', () => {
  afterEach(() => {
    MockTileImage.sources = [];
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('clears and repaints the canvas background when samples drop below two', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    mock.context.clearRect.mockClear();
    mock.context.fillRect.mockClear();
    mock.context.stroke.mockClear();

    await view.rerender({ samples: [makeSamples()[0]], overlay: 'issues', markers: [] });
    await waitFor(() => expect(mock.context.clearRect).toHaveBeenCalledTimes(1));
    expect(mock.context.fillRect).toHaveBeenCalledTimes(1);
    expect(mock.context.stroke).not.toHaveBeenCalled();

    await view.rerender({ samples: makeSamples(), overlay: 'issues', markers: [] });
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    mock.context.clearRect.mockClear();
    mock.context.fillRect.mockClear();
    await view.rerender({ samples: [], overlay: 'issues', markers: [] });
    await waitFor(() => expect(mock.context.clearRect).toHaveBeenCalledTimes(1));
    expect(mock.context.fillRect).toHaveBeenCalledTimes(1);
  });

  it('exposes whether a ready world map tile set is active', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });
    const canvas = document.querySelector('canvas');

    expect(canvas).toHaveAttribute('data-world-map-tile-set-id', '');
    await view.rerender({
      samples: makeSamples(),
      overlay: 'issues',
      markers: [],
      worldMapTileSet: makeWorldMapTileSet()
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-world-map-tile-set-id', 'fh6-brio-summer'));
  });

  it('draws loaded world map tiles behind the telemetry route using projected world bounds', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('Image', MockTileImage);

    render(TelemetryCanvas, {
      samples: makeSquareSamples(),
      overlay: 'issues',
      markers: [],
      worldMapTileSet: makeWorldMapTileSet()
    });

    await waitFor(() => expect(mock.context.drawImage).toHaveBeenCalled());
    const [image, x, y, width, height] = mock.context.drawImage.mock.calls[0];
    expect((image as MockTileImage).src).toBe('/api/map/tiles/fh6-brio-summer/0/0/0.png');
    expect(x).toBeCloseTo(440);
    expect(y).toBeCloseTo(270);
    expect(width).toBeCloseTo(20);
    expect(height).toBeCloseTo(20);
    expect(mock.context.drawImage.mock.invocationCallOrder[0]).toBeLessThan(
      mock.context.moveTo.mock.invocationCallOrder[0]
    );
  });

  it('reuses tile images until the world map tile-set id changes', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('Image', MockTileImage);

    const view = render(TelemetryCanvas, {
      samples: makeSquareSamples(),
      overlay: 'issues',
      markers: [],
      worldMapTileSet: makeWorldMapTileSet('fh6-brio-summer')
    });

    await waitFor(() => expect(MockTileImage.sources).toEqual(['/api/map/tiles/fh6-brio-summer/0/0/0.png']));
    await view.rerender({
      samples: makeSquareSamples(),
      overlay: 'issues',
      markers: [],
      worldMapTileSet: makeWorldMapTileSet('fh6-brio-summer')
    });
    expect(MockTileImage.sources).toEqual(['/api/map/tiles/fh6-brio-summer/0/0/0.png']);

    await view.rerender({
      samples: makeSquareSamples(),
      overlay: 'issues',
      markers: [],
      worldMapTileSet: makeWorldMapTileSet('fh6-brio-winter')
    });

    await waitFor(() =>
      expect(MockTileImage.sources).toEqual([
        '/api/map/tiles/fh6-brio-summer/0/0/0.png',
        '/api/map/tiles/fh6-brio-winter/0/0/0.png'
      ])
    );
  });

  it('appends in-bounds live samples without clearing and redrawing the previous path', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    const baseSamples = makeSamples();
    const appendedSample = {
      ...baseSamples[2],
      sequence: 4,
      received_at_ms: 4,
      game_timestamp_ms: 4,
      x: 18,
      z: 10,
      speed_mps: 60
    };

    const view = render(TelemetryCanvas, {
      samples: baseSamples,
      overlay: 'issues',
      markers: [],
      incremental: true,
      sampleVersion: 0
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    mock.context.clearRect.mockClear();
    mock.context.fillRect.mockClear();
    mock.context.stroke.mockClear();
    mock.context.lineTo.mockClear();
    mock.context.moveTo.mockClear();

    await view.rerender({
      samples: [...baseSamples, appendedSample],
      overlay: 'issues',
      markers: [],
      incremental: true,
      sampleVersion: 1
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    expect(mock.context.clearRect).not.toHaveBeenCalled();
    expect(mock.context.fillRect).not.toHaveBeenCalled();
    expect(mock.context.moveTo).toHaveBeenCalledTimes(1);
    expect(mock.context.lineTo).toHaveBeenCalledTimes(1);
    expect(document.querySelector('canvas')).toHaveAttribute('data-sample-count', '4');
    expect(document.querySelector('canvas')).toHaveAttribute('data-last-sequence', '4');
  });

  it('falls back to a full redraw when a live sample exceeds the current projection', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    const baseSamples = makeSamples();
    const outOfBoundsSample = {
      ...baseSamples[2],
      sequence: 4,
      received_at_ms: 4,
      game_timestamp_ms: 4,
      x: 1000,
      z: 1000,
      speed_mps: 60
    };

    const view = render(TelemetryCanvas, {
      samples: baseSamples,
      overlay: 'issues',
      markers: [],
      incremental: true,
      sampleVersion: 0
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    mock.context.clearRect.mockClear();
    mock.context.fillRect.mockClear();
    mock.context.stroke.mockClear();

    await view.rerender({
      samples: [...baseSamples, outOfBoundsSample],
      overlay: 'issues',
      markers: [],
      incremental: true,
      sampleVersion: 1
    });

    await waitFor(() => expect(mock.context.clearRect).toHaveBeenCalledTimes(1));
    expect(mock.context.fillRect).toHaveBeenCalledTimes(1);
    expect(mock.context.stroke).toHaveBeenCalledTimes(1);
    expect(document.querySelector('canvas')).toHaveAttribute('data-sample-count', '4');
    expect(document.querySelector('canvas')).toHaveAttribute('data-last-sequence', '4');
  });

  it('frames the projected telemetry path inside the centered 80% canvas safe area', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    const width = canvas?.width ?? 0;
    const height = canvas?.height ?? 0;
    const minX = width * 0.1;
    const maxX = width * 0.9;
    const minY = height * 0.1;
    const maxY = height * 0.9;
    const drawnPoints = [...mock.context.moveTo.mock.calls, ...mock.context.lineTo.mock.calls].map(([x, y]) => ({
      x: Number(x),
      y: Number(y)
    }));

    expect(drawnPoints).toHaveLength(4);
    for (const point of drawnPoints) {
      expect(point.x).toBeGreaterThanOrEqual(minX);
      expect(point.x).toBeLessThanOrEqual(maxX);
      expect(point.y).toBeGreaterThanOrEqual(minY);
      expect(point.y).toBeLessThanOrEqual(maxY);
    }
  });

  it('caps tiny live telemetry fits and keeps the initial route centered', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeTinySamples(),
      overlay: 'issues',
      markers: [],
      incremental: true
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    const drawnPoints = [...mock.context.moveTo.mock.calls, ...mock.context.lineTo.mock.calls].map(([x, y]) => ({
      x: Number(x),
      y: Number(y)
    }));
    const minX = Math.min(...drawnPoints.map((point) => point.x));
    const maxX = Math.max(...drawnPoints.map((point) => point.x));
    const minY = Math.min(...drawnPoints.map((point) => point.y));
    const maxY = Math.max(...drawnPoints.map((point) => point.y));

    expect(maxX - minX).toBeLessThanOrEqual(2);
    expect(maxY - minY).toBeLessThanOrEqual(2);
    expect((minX + maxX) / 2).toBeCloseTo((canvas as HTMLCanvasElement).width / 2, 0);
    expect((minY + maxY) / 2).toBeCloseTo((canvas as HTMLCanvasElement).height / 2, 0);
  });

  it('updates zoom data and redraws when wheeling over the canvas', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    expect(canvas).toHaveAttribute('data-zoom', '1');
    expect(canvas).toHaveAttribute('data-pan-x', '0');
    expect(canvas).toHaveAttribute('data-pan-y', '0');
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    mock.context.stroke.mockClear();

    const wheelEvent = new WheelEvent('wheel', {
      bubbles: true,
      cancelable: true,
      clientX: 450,
      clientY: 280,
      deltaY: 100
    });
    canvas?.dispatchEvent(wheelEvent);

    expect(wheelEvent.defaultPrevented).toBe(true);
    await waitFor(() => expect(Number(canvas?.getAttribute('data-zoom'))).toBeLessThan(1));
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
  });

  it('caps repeated manual zoom-in at the default maximum zoom level', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    for (let index = 0; index < 24; index += 1) {
      canvas?.dispatchEvent(
        new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          clientX: 450,
          clientY: 280,
          deltaY: -100
        })
      );
    }

    await waitFor(() => expect(canvas).toHaveAttribute('data-zoom', '1'));

    canvas?.dispatchEvent(
      new WheelEvent('wheel', {
        bubbles: true,
        cancelable: true,
        clientX: 450,
        clientY: 280,
        deltaY: -100
      })
    );
    expect(canvas).toHaveAttribute('data-zoom', '1');
  });

  it('coalesces repeated zoom redraws onto one animation frame', async () => {
    const mock = createCanvasContextMock();
    const frameCallbacks: FrameRequestCallback[] = [];
    const requestAnimationFrameMock = vi.fn((callback: FrameRequestCallback) => {
      frameCallbacks.push(callback);
      return frameCallbacks.length;
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('requestAnimationFrame', requestAnimationFrameMock);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    requestAnimationFrameMock.mockClear();
    mock.context.stroke.mockClear();
    frameCallbacks.length = 0;

    for (let index = 0; index < 3; index += 1) {
      canvas?.dispatchEvent(
        new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          clientX: 450,
          clientY: 280,
          deltaY: 100
        })
      );
    }

    expect(requestAnimationFrameMock).toHaveBeenCalledTimes(1);
    expect(mock.context.stroke).not.toHaveBeenCalled();

    frameCallbacks[0]?.(16);
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
  });

  it('smoothly eases rendered zoom toward the wheel zoom target', async () => {
    const mock = createCanvasContextMock();
    const frameCallbacks: FrameRequestCallback[] = [];
    const requestAnimationFrameMock = vi.fn((callback: FrameRequestCallback) => {
      frameCallbacks.push(callback);
      return frameCallbacks.length;
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('requestAnimationFrame', requestAnimationFrameMock);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    requestAnimationFrameMock.mockClear();
    mock.context.stroke.mockClear();
    frameCallbacks.length = 0;

    canvas?.dispatchEvent(
      new WheelEvent('wheel', {
        bubbles: true,
        cancelable: true,
        clientX: 450,
        clientY: 280,
        deltaY: 100
      })
    );

    await waitFor(() => expect(Number(canvas?.getAttribute('data-target-zoom'))).toBeLessThan(1));
    const targetZoom = Number(canvas?.getAttribute('data-target-zoom'));
    expect(targetZoom).toBeGreaterThan(0);
    expect(canvas).toHaveAttribute('data-zoom', '1');
    expect(mock.context.stroke).not.toHaveBeenCalled();

    frameCallbacks[0]?.(16);
    await waitFor(() => expect(Number(canvas?.getAttribute('data-zoom'))).toBeLessThan(1));
    expect(Number(canvas?.getAttribute('data-zoom'))).toBeGreaterThan(targetZoom);
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
  });

  it('cancels a pending zoom redraw when the canvas unmounts', async () => {
    const mock = createCanvasContextMock();
    const frameCallbacks: FrameRequestCallback[] = [];
    const requestAnimationFrameMock = vi.fn((callback: FrameRequestCallback) => {
      frameCallbacks.push(callback);
      return 42;
    });
    const cancelAnimationFrameMock = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('requestAnimationFrame', requestAnimationFrameMock);
    vi.stubGlobal('cancelAnimationFrame', cancelAnimationFrameMock);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    requestAnimationFrameMock.mockClear();
    cancelAnimationFrameMock.mockClear();
    mock.context.stroke.mockClear();

    canvas?.dispatchEvent(
      new WheelEvent('wheel', {
        bubbles: true,
        cancelable: true,
        clientX: 450,
        clientY: 280,
        deltaY: 100
      })
    );

    expect(requestAnimationFrameMock).toHaveBeenCalledTimes(1);
    view.unmount();

    expect(cancelAnimationFrameMock).toHaveBeenCalledWith(42);
    expect(mock.context.stroke).not.toHaveBeenCalled();
  });

  it('ignores zero-delta wheel events without changing zoom or redrawing', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    const initialZoom = canvas?.getAttribute('data-zoom');
    mock.context.stroke.mockClear();

    const wheelEvent = new WheelEvent('wheel', {
      bubbles: true,
      cancelable: true,
      clientX: 450,
      clientY: 280,
      deltaY: 0
    });
    canvas?.dispatchEvent(wheelEvent);

    expect(wheelEvent.defaultPrevented).toBe(true);
    expect(canvas).toHaveAttribute('data-zoom', initialZoom);
    expect(mock.context.stroke).not.toHaveBeenCalled();
  });

  it('updates pan data and redraws while dragging the canvas', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    mock.context.stroke.mockClear();

    await fireEvent.mouseDown(canvas as HTMLCanvasElement, { button: 0, clientX: 20, clientY: 30 });
    await fireEvent.mouseMove(window, { clientX: 65, clientY: 55 });
    await fireEvent.mouseUp(window);

    await waitFor(() => expect(canvas).toHaveAttribute('data-pan-x', '45'));
    expect(canvas).toHaveAttribute('data-pan-y', '25');
    expect(canvas).toHaveAttribute('data-zoom', '1');
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
  });

  it('smoothly eases rendered pan toward the drag pan target', async () => {
    const mock = createCanvasContextMock();
    const frameCallbacks: FrameRequestCallback[] = [];
    const requestAnimationFrameMock = vi.fn((callback: FrameRequestCallback) => {
      frameCallbacks.push(callback);
      return frameCallbacks.length;
    });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('requestAnimationFrame', requestAnimationFrameMock);
    vi.stubGlobal('cancelAnimationFrame', vi.fn());

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    requestAnimationFrameMock.mockClear();
    mock.context.stroke.mockClear();
    frameCallbacks.length = 0;

    await fireEvent.mouseDown(canvas as HTMLCanvasElement, { button: 0, clientX: 20, clientY: 30 });
    await fireEvent.mouseMove(window, { clientX: 65, clientY: 55 });

    await waitFor(() => expect(canvas).toHaveAttribute('data-target-pan-x', '45'));
    expect(canvas).toHaveAttribute('data-target-pan-y', '25');
    expect(canvas).toHaveAttribute('data-pan-x', '0');
    expect(canvas).toHaveAttribute('data-pan-y', '0');
    expect(requestAnimationFrameMock).toHaveBeenCalledTimes(1);

    frameCallbacks[0]?.(16);
    await waitFor(() => expect(Number(canvas?.getAttribute('data-pan-x'))).toBeGreaterThan(0));
    expect(Number(canvas?.getAttribute('data-pan-x'))).toBeLessThan(45);
    expect(Number(canvas?.getAttribute('data-pan-y'))).toBeGreaterThan(0);
    expect(Number(canvas?.getAttribute('data-pan-y'))).toBeLessThan(25);
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));

    await fireEvent.mouseUp(window);
  });

  it('dispatches viewport interaction events for manual zooming and panning', async () => {
    const mock = createCanvasContextMock();
    const viewportInteraction = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: {
        samples: makeSamples(),
        overlay: 'issues',
        markers: []
      },
      events: {
        viewportinteraction: viewportInteraction
      }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    canvas?.dispatchEvent(
      new WheelEvent('wheel', { bubbles: true, cancelable: true, clientX: 450, clientY: 280, deltaY: -100 })
    );
    await waitFor(() => expect(viewportInteraction).toHaveBeenCalledTimes(1));
    expect(viewportInteraction.mock.calls[0][0].detail).toEqual({ kind: 'zoom' });

    await fireEvent.mouseDown(canvas as HTMLCanvasElement, { button: 0, clientX: 20, clientY: 30 });
    await fireEvent.mouseMove(window, { clientX: 65, clientY: 55 });
    await fireEvent.mouseUp(window);

    await waitFor(() => expect(viewportInteraction).toHaveBeenCalledTimes(2));
    expect(viewportInteraction.mock.calls[1][0].detail).toEqual({ kind: 'pan' });
  });

  it('suppresses point selection after cumulative small drag moves exceed the click threshold', async () => {
    const mock = createCanvasContextMock();
    const pointSelect = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: {
        samples: makeSamples(),
        overlay: 'issues',
        markers: []
      },
      events: {
        pointselect: pointSelect
      }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    await fireEvent.mouseDown(canvas as HTMLCanvasElement, { button: 0, clientX: 100, clientY: 100 });
    await fireEvent.mouseMove(window, { clientX: 102, clientY: 100 });
    await fireEvent.mouseMove(window, { clientX: 104, clientY: 100 });
    await fireEvent.mouseMove(window, { clientX: 106, clientY: 100 });
    await fireEvent.mouseUp(window);
    await fireEvent.click(canvas as HTMLCanvasElement, { clientX: 106, clientY: 100 });

    expect(pointSelect).not.toHaveBeenCalled();
  });

  it('resets zoom and pan when a fit zoom command id changes', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    canvas?.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, clientX: 450, clientY: 280, deltaY: 100 }));
    await fireEvent.mouseDown(canvas as HTMLCanvasElement, { button: 0, clientX: 10, clientY: 10 });
    await fireEvent.mouseMove(window, { clientX: 110, clientY: 60 });
    await fireEvent.mouseUp(window);
    await waitFor(() => expect(Number(canvas?.getAttribute('data-zoom'))).toBeLessThan(1));
    expect(canvas).not.toHaveAttribute('data-pan-x', '0');

    await view.rerender({
      samples: makeSamples(),
      overlay: 'issues',
      markers: [],
      zoomCommand: 'fit',
      zoomCommandId: 1
    });

    await waitFor(() => {
      expect(canvas).toHaveAttribute('data-zoom', '1');
      expect(canvas).toHaveAttribute('data-pan-x', '0');
      expect(canvas).toHaveAttribute('data-pan-y', '0');
    });
  });

  it('redraws when a fit zoom command invalidates projection at an already settled viewport', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    expect(canvas).toHaveAttribute('data-zoom', '1');
    expect(canvas).toHaveAttribute('data-pan-x', '0');
    expect(canvas).toHaveAttribute('data-pan-y', '0');

    mock.context.clearRect.mockClear();
    mock.context.stroke.mockClear();
    await view.rerender({
      samples: makeSamples(),
      overlay: 'issues',
      markers: [],
      zoomCommand: 'fit',
      zoomCommandId: 1
    });

    await waitFor(() => expect(mock.context.clearRect).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    expect(canvas).toHaveAttribute('data-zoom', '1');
    expect(canvas).toHaveAttribute('data-pan-x', '0');
    expect(canvas).toHaveAttribute('data-pan-y', '0');
  });

  it('resets zoom and pan when auto fit is enabled', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    expect(canvas).toHaveAttribute('data-auto-fit', 'false');

    canvas?.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, clientX: 450, clientY: 280, deltaY: 100 }));
    await fireEvent.mouseDown(canvas as HTMLCanvasElement, { button: 0, clientX: 10, clientY: 10 });
    await fireEvent.mouseMove(window, { clientX: 110, clientY: 60 });
    await fireEvent.mouseUp(window);
    await waitFor(() => expect(Number(canvas?.getAttribute('data-zoom'))).toBeLessThan(1));
    expect(canvas).not.toHaveAttribute('data-pan-x', '0');

    await view.rerender({
      samples: makeSamples(),
      overlay: 'issues',
      markers: [],
      autoFit: true
    });

    await waitFor(() => {
      expect(canvas).toHaveAttribute('data-auto-fit', 'true');
      expect(canvas).toHaveAttribute('data-zoom', '1');
      expect(canvas).toHaveAttribute('data-pan-x', '0');
      expect(canvas).toHaveAttribute('data-pan-y', '0');
    });
  });

  it('keeps the latest car position inside the centred auto-fit follow zone', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    const baseSamples = makeSamples();
    const farSample = {
      ...baseSamples[2],
      sequence: 4,
      received_at_ms: 4,
      game_timestamp_ms: 4,
      x: 400,
      z: -250
    };

    const view = render(TelemetryCanvas, {
      samples: baseSamples,
      overlay: 'issues',
      markers: [],
      autoFit: true
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    mock.context.lineTo.mockClear();
    await view.rerender({
      samples: [...baseSamples, farSample],
      overlay: 'issues',
      markers: [],
      autoFit: true,
      sampleVersion: 1
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '4'));
    await waitFor(() => expect(Number(canvas?.getAttribute('data-pan-x'))).toBeLessThan(0));
    expect(Number(canvas?.getAttribute('data-pan-y'))).toBeLessThan(0);

    const width = canvas?.width ?? 0;
    const height = canvas?.height ?? 0;

    await waitFor(() => {
      const latestLineTo = mock.context.lineTo.mock.calls.at(-1);
      expect(latestLineTo).toBeDefined();
      const latestViewportX = Number(latestLineTo?.[0]) + Number(canvas?.getAttribute('data-pan-x'));
      const latestViewportY = Number(latestLineTo?.[1]) + Number(canvas?.getAttribute('data-pan-y'));

      expect(latestViewportX).toBeGreaterThanOrEqual(width * 0.4);
      expect(latestViewportX).toBeLessThanOrEqual(width * 0.6);
      expect(latestViewportY).toBeGreaterThanOrEqual(height * 0.4);
      expect(latestViewportY).toBeLessThanOrEqual(height * 0.6);
    });
  });

  it('uses the fresh projection when incremental auto-fit follow falls back to a redraw', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    const baseSamples = makeSamples();
    const farSampleInsideProjection = {
      ...baseSamples[2],
      sequence: 4,
      received_at_ms: 4,
      game_timestamp_ms: 4,
      x: 300,
      z: 15
    };

    const view = render(TelemetryCanvas, {
      samples: baseSamples,
      overlay: 'issues',
      markers: [],
      autoFit: true,
      incremental: true,
      sampleVersion: 0
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    mock.context.clearRect.mockClear();
    mock.context.lineTo.mockClear();
    await view.rerender({
      samples: [...baseSamples, farSampleInsideProjection],
      overlay: 'issues',
      markers: [],
      autoFit: true,
      incremental: true,
      sampleVersion: 1
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '4'));
    await waitFor(() => expect(mock.context.clearRect).toHaveBeenCalledTimes(1));

    const width = canvas?.width ?? 0;

    await waitFor(() => {
      const latestLineTo = mock.context.lineTo.mock.calls.at(-1);
      expect(latestLineTo).toBeDefined();
      const latestViewportX = Number(latestLineTo?.[0]) + Number(canvas?.getAttribute('data-pan-x'));

      expect(Number(canvas?.getAttribute('data-pan-x'))).toBeCloseTo(-60, 3);
      expect(latestViewportX).toBeCloseTo(width * 0.6, 3);
    });
  });

  it('leaves auto-fit pan unchanged while the latest car position stays inside the follow zone', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    const baseSamples = makeSamples();
    const nearbySample = {
      ...baseSamples[2],
      sequence: 4,
      received_at_ms: 4,
      game_timestamp_ms: 4,
      x: 22,
      z: 16
    };

    const view = render(TelemetryCanvas, {
      samples: baseSamples,
      overlay: 'issues',
      markers: [],
      autoFit: true,
      incremental: true,
      sampleVersion: 0
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());

    mock.context.clearRect.mockClear();
    await view.rerender({
      samples: [...baseSamples, nearbySample],
      overlay: 'issues',
      markers: [],
      autoFit: true,
      incremental: true,
      sampleVersion: 1
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '4'));
    expect(mock.context.clearRect).not.toHaveBeenCalled();
    expect(canvas).toHaveAttribute('data-pan-x', '0');
    expect(canvas).toHaveAttribute('data-pan-y', '0');
  });

  it('uses a neutral route color for the issues overlay because issues are discrete events', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, { samples: makeSamples(), overlay: 'issues', markers: makeMarkers() });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    expect(mock.getStrokeStyles()).toEqual(['#d4d4d8']);
  });

  it('prefers the highest severity when issue markers overlap the same sequence', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: makeOverlappingMarkers()
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(1));
    expect(mock.getStrokeStyles()).toEqual(['#d4d4d8']);
  });

  it('draws issue metadata icons only on the issues overlay', async () => {
    vi.stubGlobal('Path2D', MockPath2D);
    const mock = createCanvasContextMock({ shapes: true });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: makeMarkers()
    });
    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();

    const fillText = vi.mocked(mock.context.fillText);
    const strokeText = vi.mocked(mock.context.strokeText);
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '2'));
    const issuePathData = mock
      .getFillCalls()
      .map(({ shape }) => (shape instanceof MockPath2D ? shape.pathData : null))
      .filter(Boolean);
    expect(issuePathData).toContain(iconPaths.grip.paths[0]);
    const gripIconFillStyles = mock
      .getFillCalls()
      .filter(({ shape }) => shape instanceof MockPath2D && shape.pathData === iconPaths.grip.paths[0])
      .map(({ fillStyle }) => fillStyle);
    expect(gripIconFillStyles).toEqual(expect.arrayContaining([issueIconToneColors.red, issueIconToneColors.yellow]));
    expect(mock.getFillCalls().some(({ shape, fillStyle }) => shape === undefined && fillStyle === 'rgba(24, 24, 27, 0.92)')).toBe(true);
    expect(strokeText.mock.calls.some(([text]) => text === '\u00d7')).toBe(false);
    expect(fillText.mock.calls.some(([text]) => text === '\u00d7')).toBe(false);

    mock.clearFillCalls();
    fillText.mockClear();
    strokeText.mockClear();
    await view.rerender({ samples: makeSamples(), overlay: 'speed', markers: makeMarkers() });
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '0'));
    const speedOverlayPathData = mock
      .getFillCalls()
      .map(({ shape }) => (shape instanceof MockPath2D ? shape.pathData : null))
      .filter(Boolean);
    expect(speedOverlayPathData).not.toContain(iconPaths.grip.paths[0]);
    expect(strokeText.mock.calls.some(([text]) => text === '\u00d7')).toBe(false);
    expect(fillText.mock.calls.some(([text]) => text === '\u00d7')).toBe(false);
  });

  it('uses the issue x glyph only as a Path2D fallback', async () => {
    vi.stubGlobal('Path2D', undefined);
    const mock = createCanvasContextMock({ shapes: true });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: makeMarkers()
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    const fillText = vi.mocked(mock.context.fillText);
    const strokeText = vi.mocked(mock.context.strokeText);
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '2'));
    expect(strokeText.mock.calls.some(([text]) => text === '\u00d7')).toBe(true);
    expect(fillText.mock.calls.some(([text]) => text === '\u00d7')).toBe(true);
    expect(mock.getFillTextCalls().filter(({ text }) => text === '\u00d7').map(({ fillStyle }) => fillStyle)).toEqual(
      expect.arrayContaining([issueIconToneColors.red, issueIconToneColors.yellow])
    );
  });

  it('draws rewind and reset issue markers with Material icons', async () => {
    vi.stubGlobal('Path2D', MockPath2D);
    const mock = createCanvasContextMock({ shapes: true });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    const raceControlMarkers: IssueMarker[] = [
      {
        id: 'marker-rewind',
        session_id: 'session-a',
        lap_id: 'lap-a',
        start_sequence: 2,
        end_sequence: 2,
        metric: 'race.rewind',
        severity: 'info',
        reason: 'Rewind',
        ruleset_version: 1,
        confidence: 0.85,
        ...markerDetails({ anchor_sequence: 2, issue_kind: 'Rewind' })
      },
      {
        id: 'marker-reset',
        session_id: 'session-a',
        lap_id: 'lap-a',
        start_sequence: 3,
        end_sequence: 3,
        metric: 'race.reset',
        severity: 'info',
        reason: 'Checkpoint reset',
        ruleset_version: 1,
        confidence: 0.85,
        ...markerDetails({ anchor_sequence: 3, issue_kind: 'Reset' })
      }
    ];

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: raceControlMarkers
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '2'));
    const pathData = mock
      .getFillCalls()
      .map(({ shape }) => (shape instanceof MockPath2D ? shape.pathData : null))
      .filter(Boolean);
    expect(pathData).toContain('M860-240 500-480l360-240v480Zm-400 0L100-480l360-240v480Z');
    expect(pathData).toContain(
      'M480-120q-138 0-240.5-91.5T122-440h82q14 104 92.5 172T480-200q117 0 198.5-81.5T760-480q0-117-81.5-198.5T480-760q-69 0-129 32t-101 88h110v80H120v-240h80v94q51-64 124.5-99T480-840q75 0 140.5 28.5t114 77q48.5 48.5 77 114T840-480q0 75-28.5 140.5t-77 114q-48.5 48.5-114 77T480-120Zm112-192L440-464v-216h80v184l128 128-56 56Z'
    );
    const raceControlIconFillStyles = mock
      .getFillCalls()
      .filter(({ shape }) => shape instanceof MockPath2D)
      .map(({ fillStyle }) => fillStyle);
    expect(raceControlIconFillStyles).toEqual(expect.arrayContaining([issueIconToneColors.blue, issueIconToneColors.neutral]));
  });

  it('only draws the S/F marker for trusted lap boundaries', async () => {
    const mock = createCanvasContextMock({ shapes: true });
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    const view = render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'issues',
      markers: []
    });

    const fillText = vi.mocked(mock.context.fillText);
    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    expect(fillText.mock.calls.some(([text]) => text === 'S/F')).toBe(false);

    fillText.mockClear();
    await view.rerender({
      samples: makeSamples(),
      overlay: 'issues',
      markers: [],
      lapBoundaryConfidence: 'heuristic'
    });
    expect(fillText.mock.calls.some(([text]) => text === 'S/F')).toBe(false);

    fillText.mockClear();
    await view.rerender({
      samples: makeSamples(),
      overlay: 'issues',
      markers: [],
      lapBoundaryConfidence: 'game_field'
    });
    await waitFor(() => expect(fillText.mock.calls.some(([text]) => text === 'S/F')).toBe(true));
  });

  it('trusts explicit game-field start actions for the S/F marker', async () => {
    const mock = createCanvasContextMock({ shapes: true });
    const trustedStartSamples = makeSamples().map((sample, index) =>
      index === 0 ? { ...sample, lap_action: 'start', boundary_confidence: 'game_field' } : sample
    );
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: trustedStartSamples,
      overlay: 'issues',
      markers: []
    });

    const fillText = vi.mocked(mock.context.fillText);
    const strokeText = vi.mocked(mock.context.strokeText);
    await waitFor(() => expect(strokeText.mock.calls.some(([text]) => text === 'S/F')).toBe(true));
    expect(fillText.mock.calls.some(([text]) => text === 'S/F')).toBe(true);
  });

  it('draws the navigation icon at the latest telemetry point using yaw rotation', async () => {
    vi.stubGlobal('Path2D', MockPath2D);
    const mock = createCanvasContextMock({ shapes: true });
    const samples = makeSamples().map((sample, index) =>
      index === 2 ? { ...sample, yaw: Math.PI / 2 } : sample
    );
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples,
      overlay: 'issues',
      markers: []
    });

    const fill = vi.mocked(mock.context.fill);
    await waitFor(() =>
      expect(fill.mock.calls.some(([shape]) => shape instanceof MockPath2D)).toBe(true)
    );
    expect(mock.context.rotate).toHaveBeenCalledWith(Math.PI / 2);
    const iconFill = fill.mock.calls.find(([shape]) => shape instanceof MockPath2D);
    expect((iconFill?.[0] as MockPath2D | undefined)?.pathData).toBe(
      'm200-120-40-40 320-720 320 720-40 40-280-120-280 120Z'
    );
    expect(mock.context.arc).not.toHaveBeenCalledWith(0, 0, expect.any(Number), 0, Math.PI * 2);
    expect(
      mock.getFillCalls().find(({ shape }) => shape instanceof MockPath2D)?.fillStyle
    ).toBe('#e3e3e3');
  });

  it('dispatches issue selection before point selection when clicking an issue icon', async () => {
    const mock = createCanvasContextMock();
    const issueSelect = vi.fn();
    const pointSelect = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: {
        samples: makeSamples(),
        overlay: 'issues',
        markers: makeMarkers()
      },
      events: {
        issueselect: issueSelect,
        pointselect: pointSelect
      }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '2'));

    await fireEvent.click(canvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });

    expect(issueSelect).toHaveBeenCalledTimes(1);
    expect(issueSelect.mock.calls[0][0].detail.marker.id).toBe('marker-critical');
    expect(issueSelect.mock.calls[0][0].detail.markers.length).toBe(2);
    expect(pointSelect).not.toHaveBeenCalled();
  });

  it('keeps issue hit targets at full sample resolution when simplifying the drawn route', async () => {
    const mock = createCanvasContextMock();
    const issueSelect = vi.fn();
    const denseSamples = makeDenseSamples();
    const droppedAnchorSequence = 500;
    const markers: IssueMarker[] = [
      {
        id: 'dense-marker',
        session_id: 'session-a',
        lap_id: 'lap-a',
        start_sequence: droppedAnchorSequence,
        end_sequence: droppedAnchorSequence,
        metric: 'combined_slip',
        severity: 'critical',
        reason: 'Dense sample issue',
        ruleset_version: 1,
        confidence: 0.9,
        ...markerDetails({ anchor_sequence: droppedAnchorSequence })
      }
    ];
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);
    vi.stubGlobal('Path2D', undefined);

    render(TelemetryCanvas, {
      props: {
        samples: denseSamples,
        overlay: 'issues',
        markers
      },
      events: {
        issueselect: issueSelect
      }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '1'));
    expect(mock.context.lineTo.mock.calls.length).toBeLessThan(denseSamples.length / 2);
    expect(mock.getStrokeStyles()).toContain('#d4d4d8');

    await fireEvent.click(canvas as HTMLCanvasElement, { clientX: 450, clientY: 280 });

    expect(issueSelect).toHaveBeenCalledTimes(1);
    expect(issueSelect.mock.calls[0][0].detail.marker.id).toBe('dense-marker');
    expect(issueSelect.mock.calls[0][0].detail.sample.sequence).toBe(droppedAnchorSequence);
  });

  it('does not dispatch issue selection outside the issues overlay', async () => {
    const mock = createCanvasContextMock();
    const issueSelect = vi.fn();
    const pointSelect = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: {
        samples: makeSamples(),
        overlay: 'speed',
        markers: makeMarkers()
      },
      events: {
        issueselect: issueSelect,
        pointselect: pointSelect
      }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '0'));

    await fireEvent.click(canvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });

    expect(issueSelect).not.toHaveBeenCalled();
    expect(pointSelect).toHaveBeenCalledTimes(1);
    expect(pointSelect.mock.calls[0][0].detail.sample.sequence).toBe(2);
  });

  it('uses severity, confidence, and start sequence priority for overlapping issue targets', async () => {
    const mock = createCanvasContextMock();
    const issueSelect = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: {
        samples: makeSamples(),
        overlay: 'issues',
        markers: makeOverlappingMarkers()
      },
      events: {
        issueselect: issueSelect
      }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '3'));

    await fireEvent.click(canvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });
    expect(issueSelect.mock.calls[0][0].detail.marker.id).toBe('marker-critical-overlap');

    issueSelect.mockClear();
    const tiedWarnings: IssueMarker[] = [
      {
        id: 'warning-low-confidence',
        session_id: 'session-a',
        lap_id: 'lap-a',
        start_sequence: 1,
        end_sequence: 1,
        metric: 'combined_slip',
        severity: 'warning',
        reason: 'Low confidence warning',
        ruleset_version: 1,
        confidence: 0.4,
        ...markerDetails({ anchor_sequence: 2 })
      },
      {
        id: 'warning-high-late',
        session_id: 'session-a',
        lap_id: 'lap-a',
        start_sequence: 3,
        end_sequence: 3,
        metric: 'combined_slip',
        severity: 'warning',
        reason: 'High confidence later warning',
        ruleset_version: 1,
        confidence: 0.9,
        ...markerDetails({ anchor_sequence: 2 })
      },
      {
        id: 'warning-high-early',
        session_id: 'session-a',
        lap_id: 'lap-a',
        start_sequence: 2,
        end_sequence: 2,
        metric: 'combined_slip',
        severity: 'warning',
        reason: 'High confidence earlier warning',
        ruleset_version: 1,
        confidence: 0.9,
        ...markerDetails({ anchor_sequence: 2 })
      }
    ];
    await render(TelemetryCanvas, {
      props: { samples: makeSamples(), overlay: 'issues', markers: tiedWarnings },
      events: { issueselect: issueSelect }
    });

    const secondCanvas = document.querySelectorAll('canvas')[1];
    await waitFor(() => expect(secondCanvas).toHaveAttribute('data-issue-target-count', '3'));
    await fireEvent.click(secondCanvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });
    expect(issueSelect.mock.calls[0][0].detail.marker.id).toBe('warning-high-early');
  });

  it('draws telemetry, ghost, and selected range paths with slimmer stroke widths', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      ghostSamples: makeSamples(),
      selectedRange: { startSequence: 1, endSequence: 3 },
      overlay: 'issues',
      markers: []
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalled());
    const lineWidths = mock.getLineWidths();
    expect(lineWidths).toContain(3);
    expect(lineWidths).toContain(2);
    expect(lineWidths).toContain(5);
    expect(lineWidths).not.toContain(4);
    expect(lineWidths).not.toContain(7);
  });

  it('uses combined slip colors for grip overlay instead of issue severity colors', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeOverlaySamples(),
      overlay: 'grip',
      markers: makeMarkers()
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(2));
    const styles = mock.getStrokeStyles();
    expect(styles).toEqual(['rgb(132, 204, 22)', 'rgb(220, 38, 38)']);
    expect(styles).not.toEqual(['#f59e0b', '#ef4444']);
  });

  it('uses tyre temperature colors instead of issue severity colors for the temperature overlay', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeOverlaySamples(),
      overlay: 'temperature',
      markers: makeMarkers()
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(2));
    const styles = mock.getStrokeStyles();
    expect(styles).toEqual(['rgb(0, 255, 0)', 'rgb(255, 0, 0)']);
    expect(styles).not.toEqual(['#f59e0b', '#ef4444']);
  });

  it('uses independent suspension and RPM overlays instead of the old combined overlay', async () => {
    const suspensionMock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(suspensionMock.context);

    const suspensionView = render(TelemetryCanvas, {
      samples: makeOverlaySamples(),
      overlay: 'suspension',
      markers: makeMarkers()
    });

    await waitFor(() => expect(suspensionMock.context.stroke).toHaveBeenCalledTimes(2));
    expect(suspensionMock.getStrokeStyles()).toEqual(['rgb(0, 255, 0)', 'rgb(255, 0, 0)']);
    suspensionView.unmount();

    const rpmMock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(rpmMock.context);
    render(TelemetryCanvas, {
      samples: makeOverlaySamples(),
      overlay: 'rpm',
      markers: makeMarkers()
    });

    await waitFor(() => expect(rpmMock.context.stroke).toHaveBeenCalledTimes(2));
    const styles = rpmMock.getStrokeStyles();
    expect(styles).toEqual(['rgb(255, 255, 0)', 'rgb(255, 0, 0)']);
    expect(styles).not.toEqual(['#f59e0b', '#ef4444']);
  });

  it('uses distinct gradient-like stroke colors for speed overlay segments', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'speed',
      markers: makeMarkers()
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(2));
    const styles = mock.getStrokeStyles();
    expect(styles).toEqual(['rgb(255, 255, 0)', 'rgb(0, 255, 0)']);
  });

  it('uses distinct brake-heavy and throttle-heavy stroke colors for inputs overlay', async () => {
    const mock = createCanvasContextMock();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      samples: makeSamples(),
      overlay: 'inputs',
      markers: makeMarkers()
    });

    await waitFor(() => expect(mock.context.stroke).toHaveBeenCalledTimes(2));
    const styles = mock.getStrokeStyles();
    expect(styles).toEqual(['rgba(239, 68, 68, 1.000)', 'rgba(34, 197, 94, 1.000)']);
  });

  it('dispatches issue hover with all nearby issue markers sorted by priority', async () => {
    const mock = createCanvasContextMock();
    const issueHover = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: { samples: makeSamples(), overlay: 'issues', markers: makeOverlappingMarkers() },
      events: { issuehover: issueHover }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '3'));
    await fireEvent.mouseMove(canvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });

    expect(issueHover).toHaveBeenCalledTimes(1);
    expect(issueHover.mock.calls[0][0].detail.markers.map((marker: IssueMarker) => marker.id)).toEqual([
      'marker-critical-overlap', 'marker-warning-overlap', 'marker-info-range'
    ]);
    expect(issueHover.mock.calls[0][0].detail.marker.id).toBe('marker-critical-overlap');
  });

  it('dispatches issue hover clear when the cursor leaves nearby issue markers', async () => {
    const mock = createCanvasContextMock();
    const issueHoverClear = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: { samples: makeSamples(), overlay: 'issues', markers: makeMarkers() },
      events: { issuehoverclear: issueHoverClear }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '2'));
    await fireEvent.mouseMove(canvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });
    await fireEvent.mouseMove(canvas as HTMLCanvasElement, { clientX: 10, clientY: 10 });

    expect(issueHoverClear).toHaveBeenCalledTimes(1);
  });

  it('uses click to dispatch the same nearby issue cluster for pinning', async () => {
    const mock = createCanvasContextMock();
    const issueSelect = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(mock.context);

    render(TelemetryCanvas, {
      props: { samples: makeSamples(), overlay: 'issues', markers: makeOverlappingMarkers() },
      events: { issueselect: issueSelect }
    });

    const canvas = document.querySelector('canvas');
    expect(canvas).not.toBeNull();
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '3'));
    await fireEvent.click(canvas as HTMLCanvasElement, { clientX: 450, clientY: 283 });

    expect(issueSelect).toHaveBeenCalledTimes(1);
    expect(issueSelect.mock.calls[0][0].detail.markers.map((marker: IssueMarker) => marker.id)).toEqual([
      'marker-critical-overlap', 'marker-warning-overlap', 'marker-info-range'
    ]);
  });
});
