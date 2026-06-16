import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import App from './App.svelte';
import { DASHBOARD_WIDGETS } from './dashboardWidgets';
import type {
  AppAboutPayload,
  AppUpdateCheckResponse,
  CarInfo,
  DiagnosticsPayload,
  IssueMarker,
  LapSummary,
  ListenerStatus,
  LiveSample,
  ReferenceScope,
  SessionPageResponse,
  SessionSummary,
  StatsSummary,
  TelemetryExportDefaults,
  TelemetryExportJob,
  TrackAsset,
  TrackProfile,
  WorldMapStatus
} from './types';

let canvasContext: CanvasRenderingContext2D;
const originalGetContext = HTMLCanvasElement.prototype.getContext;
const originalGetBoundingClientRect = HTMLCanvasElement.prototype.getBoundingClientRect;

const capturePayload = {
  mode: 'auto',
  phase: 'idle',
  packet_receipt: {
    state: 'waiting',
    has_received_packets: false,
    packets_observed: 0,
    last_timestamp_ms: null
  },
  recording: {
    active: false,
    phase: 'idle',
    mode: 'auto',
    total_live_packets_recorded_excluding_prebuffer: 0
  },
  prebuffer: {
    capacity: 300,
    size: 0
  },
  auto_detection: {
    last_signals: {
      race_on: false,
      moving: false,
      valid_vehicle: false,
      race_time_progressing: false
    },
    last_reason: 'waiting_for_packet'
  },
  listener: {
    state: 'waiting',
    udp_host: '127.0.0.1',
    udp_port: 5400,
    packets_received: 0,
    packets_recorded: 0,
    message: 'waiting for telemetry'
  },
  settings: {
    capture_mode: 'auto',
    udp_host: '127.0.0.1',
    udp_port: 5400,
    preferred_overlay: 'issues',
    unit_system: 'imperial'
  }
};

const statusPayload = {
  listener: {
    state: 'waiting',
    udp_host: '127.0.0.1',
    udp_port: 5400,
    packets_received: 0,
    packets_recorded: 0,
    message: 'waiting for telemetry'
  },
  settings: {
    capture_mode: 'auto',
    udp_host: '127.0.0.1',
    udp_port: 5400,
    preferred_overlay: 'issues',
    unit_system: 'imperial'
  },
  capture: capturePayload
};

const receivingStatusPayload = {
  ...statusPayload,
  listener: {
    ...statusPayload.listener,
    state: 'receiving',
    packets_received: 2,
    message: 'receiving replay packets'
  }
};

function statusWithPreferredOverlay(preferredOverlay: string) {
  return {
    ...statusPayload,
    settings: {
      ...statusPayload.settings,
      preferred_overlay: preferredOverlay
    },
    capture: {
      ...statusPayload.capture,
      settings: {
        ...statusPayload.capture.settings,
        preferred_overlay: preferredOverlay
      }
    }
  } as typeof statusPayload;
}

function captureWithPreferredOverlay(preferredOverlay: string) {
  return {
    ...capturePayload,
    settings: {
      ...capturePayload.settings,
      preferred_overlay: preferredOverlay
    }
  } as typeof capturePayload;
}

const defaultStatsSummary: StatsSummary = {
  laps_recorded: 12,
  sessions_created: 4,
  tracks_driven: 3,
  cars_driven: 2,
  max_speed_mps: 44.704,
  favourite_car: {
    value: 'Mazda Furai',
    lap_count: 7,
    session_count: 2,
    last_used_at_ms: 6_000
  },
  favourite_track: {
    value: 'Emerald Circuit',
    detail: 'Full',
    lap_count: 5,
    session_count: 2,
    last_used_at_ms: 6_000
  },
  favourite_pi_class: {
    value: 'S1',
    lap_count: 6,
    session_count: 3,
    last_used_at_ms: 6_000
  },
  favoured_drive: {
    value: 'RWD',
    lap_count: 8,
    session_count: 3,
    last_used_at_ms: 6_000
  },
  time_spent_racing_ms: 3_661_000
};

const defaultDiagnosticsPayload: DiagnosticsPayload = {
  database_path: 'telemetry.sqlite3',
  database_size_bytes: 262_144,
  wal_size_bytes: 32_768,
  row_counts: {
    sessions: 2,
    laps: 4,
    packets: 128,
    issue_markers: 3,
    track_profiles: 2,
    world_map_tile_sets: 0
  },
  world_map: {
    settings: {
      fh6_media_root: null,
      world_map_enabled: false,
      world_map_season: 'summer'
    },
    tile_set_count: 0,
    ready_tile_set_id: null
  },
  listener_status: {
    ...statusPayload.listener,
    packets_recorded: 8
  } as DiagnosticsPayload['listener_status'],
  capture_status: capturePayload as DiagnosticsPayload['capture_status'],
  recent_errors: [],
  app_version: '0.1.0'
};

const defaultAppAboutPayload: AppAboutPayload = {
  name: 'Forza Telemetry Tracker',
  version: '1.0.0',
  release_date: '2026-06-13',
  git_sha: 'abcdef123456',
  channel: 'stable',
  repository: 'owner/repo',
  packaged: true,
  updates: {
    supported: true,
    release_access: 'public'
  }
};

const defaultUpdateCheckPayload: AppUpdateCheckResponse = {
  status: 'up_to_date',
  current_version: '1.0.0',
  latest_version: '1.0.0',
  release_url: null,
  published_at: null,
  asset_name: null,
  message: 'You are up to date.'
};

const defaultWorldMapStatus: WorldMapStatus = {
  status: 'source_missing',
  settings: {
    fh6_media_root: null,
    world_map_enabled: false,
    world_map_season: 'summer'
  },
  source: {
    available: false,
    path: null,
    season: 'summer'
  },
  converter: {
    available: false,
    path: null
  },
  tile_set: null
};

const readyWorldMapTileSet: WorldMapStatus['tile_set'] = {
  id: 'fh6-brio-summer',
  game: 'fh6',
  map_name: 'brio',
  season: 'summer',
  source_zip_path: 'G:/FH6/media/UI/Textures/Data_Bound/Map_Brio_Summer.zip',
  source_zip_mtime_ms: 1_710_000_000_000,
  source_zip_size_bytes: 35_635_086,
  cache_dir: 'C:/Users/example/AppData/Local/Forza Telemetry Tracker/map-cache/fh6/brio/summer',
  tile_format: 'png',
  tile_size: 1024,
  min_zoom: 0,
  max_zoom: 0,
  world_origin_x: -12548,
  world_origin_z: -11281,
  world_size: 22035,
  status: 'ready',
  error_message: null,
  last_built_at_ms: 1_710_000_000_500,
  updated_at_ms: 1_710_000_000_500,
  tile_url_template: '/api/map/tiles/fh6-brio-summer/{z}/{x}/{y}.png',
  manifest: {
    game: 'fh6',
    map: 'brio',
    season: 'summer',
    format: 'png',
    tileSize: 1024,
    minZoom: 0,
    maxZoom: 0,
    worldOriginX: -12548,
    worldOriginZ: -11281,
    worldSize: 22035,
    tileUrlTemplate: '/api/map/tiles/fh6-brio-summer/{z}/{x}/{y}.png',
    tiles: [{ z: 0, x: 0, y: 0, path: '0/0/0.png' }]
  }
};

const readyWorldMapStatus: WorldMapStatus = {
  status: 'ready',
  settings: {
    fh6_media_root: 'G:/FH6',
    world_map_enabled: true,
    world_map_season: 'summer'
  },
  source: {
    available: true,
    path: 'G:/FH6/media/UI/Textures/Data_Bound/Map_Brio_Summer.zip',
    season: 'summer'
  },
  converter: {
    available: true,
    path: 'F:/code/git/forza-telemetry-tracker/bin/map-converter/forza-map-tile-converter.exe'
  },
  tile_set: readyWorldMapTileSet
};

const defaultLaps: LapSummary[] = [
  {
    id: 'older-lap',
    session_id: 'session-a',
    session_label: 'Sunset Sprint',
    lap_number: 1,
    status: 'finalized',
    started_at_ms: 1_000,
    ended_at_ms: 2_000,
    ended_reason: 'lap_boundary',
    boundary_confidence: 'game_field',
    lap_time_ms: 96_234
  },
  {
    id: 'newer-lap',
    session_id: 'session-b',
    session_label: 'Midnight Club',
    lap_number: 2,
    status: 'finalized',
    started_at_ms: 5_000,
    ended_at_ms: 6_000,
    ended_reason: 'lap_boundary',
    boundary_confidence: 'game_field',
    lap_time_ms: 95_000
  }
];

const defaultLoadedSessionLaps: LapSummary[] = defaultLaps.map((lap) => ({
  ...lap,
  session_id: 'session-b'
}));

const defaultSessions: SessionSummary[] = [
  {
    id: 'session-a',
    user_id: 'local-user',
    label: 'Sunset Sprint',
    status: 'finalized',
    started_at_ms: 1_000,
    ended_at_ms: 2_000,
    ended_reason: 'session_boundary',
    last_active_at_ms: 2_000,
    lap_count: 1
  },
  {
    id: 'session-b',
    user_id: 'local-user',
    label: 'Midnight Club',
    status: 'active',
    started_at_ms: 5_000,
    ended_at_ms: null,
    ended_reason: null,
    last_active_at_ms: 6_000,
    lap_count: 1
  }
];

const defaultTrackProfiles: TrackProfile[] = [
  {
    id: 'profile-emerald',
    owner_user_id: 'local-user',
    name: 'Emerald Circuit',
    layout: 'Full',
    source: 'manual',
    confidence: 'user',
    shape_signature: null,
    created_at_ms: 1_000,
    updated_at_ms: 2_000
  },
  {
    id: 'profile-horizon',
    owner_user_id: 'local-user',
    name: 'Horizon Speedway',
    layout: 'Oval',
    source: 'manual',
    confidence: 'user',
    shape_signature: null,
    created_at_ms: 1_500,
    updated_at_ms: 1_500
  }
];

const defaultTrackAssetsByProfile: Record<string, TrackAsset[]> = {
  'profile-emerald': [
    {
      id: 'asset-emerald-map',
      track_profile_id: 'profile-emerald',
      filename: 'emerald-map.svg',
      mime_type: 'image/svg+xml',
      size_bytes: 4096,
      transform: {
        scale: 1.2,
        rotate_deg: 4,
        translate_x: 12,
        translate_y: -8
      },
      created_at_ms: 2_000,
      updated_at_ms: 2_000,
      file_url: '/api/tracks/assets/asset-emerald-map/file'
    }
  ],
  'profile-horizon': [
    {
      id: 'asset-horizon-map',
      track_profile_id: 'profile-horizon',
      filename: 'horizon-map.png',
      mime_type: 'image/png',
      size_bytes: 2048,
      transform: {
        scale: 0.9,
        rotate_deg: -2,
        translate_x: -6,
        translate_y: 14
      },
      created_at_ms: 2_500,
      updated_at_ms: 2_500,
      file_url: '/api/tracks/assets/asset-horizon-map/file'
    }
  ]
};

const recoveredSamples = [
  {
    sequence: 1,
    received_at_ms: 1,
    game_timestamp_ms: 1,
    lap_number: 0,
    current_lap: 0,
    current_race_time: 0,
    x: 1,
    y: 0,
    z: 1,
    speed_mps: 10,
    throttle: 255,
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
    x: 4,
    y: 0,
    z: 5,
    speed_mps: 12,
    throttle: 255,
    brake: 0,
    steer: 0,
    gear: 2
  }
];

function makeLiveSample(sequence: number, overrides: Partial<LiveSample> = {}): LiveSample {
  return {
    sequence,
    received_at_ms: sequence,
    game_timestamp_ms: sequence,
    is_race_on: true,
    lap_number: 1,
    current_lap: sequence / 10,
    current_race_time: sequence / 10,
    x: sequence,
    y: 0,
    z: sequence,
    speed_mps: 10 + (sequence % 20),
    throttle: 255,
    brake: 0,
    steer: 0,
    gear: 2,
    ...overrides
  };
}

const newerLapSamples = [
  { sequence: 10, received_at_ms: 10, game_timestamp_ms: 10, lap_number: 2, current_lap: 2, current_race_time: 10, x: 0, y: 0, z: 0, speed_mps: 20.5, throttle: 200, brake: 0, steer: 0, gear: 2 },
  { sequence: 11, received_at_ms: 11, game_timestamp_ms: 11, lap_number: 2, current_lap: 2, current_race_time: 11, x: 5, y: 0, z: 5, speed_mps: 32.25, throttle: 150, brake: 50, steer: 10, gear: 3 },
  { sequence: 12, received_at_ms: 12, game_timestamp_ms: 12, lap_number: 2, current_lap: 2, current_race_time: 12, x: 10, y: 0, z: 10, speed_mps: 45.678, throttle: 255, brake: 0, steer: 0, gear: 4 }
];

const olderLapSamples = [
  { sequence: 1, received_at_ms: 1, game_timestamp_ms: 1, lap_number: 1, current_lap: 1, current_race_time: 1, x: -2, y: 0, z: -2, speed_mps: 12.111, throttle: 100, brake: 0, steer: -5, gear: 2 },
  { sequence: 2, received_at_ms: 2, game_timestamp_ms: 2, lap_number: 1, current_lap: 1, current_race_time: 2, x: 3, y: 0, z: 3, speed_mps: 22.222, throttle: 180, brake: 10, steer: 5, gear: 3 }
];

const newerFullLapSummary = {
  packet_count: 3,
  top_speed_mps: 45.678,
  average_speed_mps: 32.809,
  peak_combined_slip: 0.4567,
  limiter_samples: 2,
  bottoming_events: 1,
  start_sequence: 10,
  end_sequence: 12,
  lap_time_ms: 95_000
};

const defaultCarInfo: CarInfo = {
  ordinal: 1229,
  name: 'Mazda Furai',
  display_name: 'Furai',
  model_short: 'Mazda Furai',
  year: 2008,
  class_id: 6,
  class_label: 'R',
  performance_index: 998,
  drivetrain_id: 1,
  drivetrain_label: 'RWD',
  catalog_source: 'test',
  catalog: null,
  details: {
    num_cylinders: 3,
    car_group: 26,
    car_group_label: 'Extreme Track Toys',
    engine_max_rpm: 9999.995,
    peak_power_w: 331000,
    average_power_w: 300000,
    peak_torque_nm: 392,
    average_torque_nm: 350,
    peak_boost_bar: 0,
    fuel: 0.75
  }
};

const olderCarInfo: CarInfo = {
  ...defaultCarInfo,
  ordinal: 368,
  name: 'Acura Integra',
  display_name: 'Integra Type R',
  model_short: 'Acura Integra',
  year: 2001,
  class_id: 4,
  class_label: 'S1',
  performance_index: 800,
  drivetrain_id: 0,
  drivetrain_label: 'FWD',
  details: {
    ...defaultCarInfo.details,
    num_cylinders: 4,
    car_group: 12,
    car_group_label: 'Retro Supercars',
    engine_max_rpm: 8400,
    peak_power_w: 220000,
    average_power_w: 190000,
    peak_torque_nm: 240,
    average_torque_nm: 210,
    fuel: 0.5
  }
};

function carInfoForLapId(lapId: string): CarInfo {
  return lapId.includes('older') || lapId === 'completed-lap' ? olderCarInfo : defaultCarInfo;
}

const olderFullLapSummary = {
  packet_count: 2,
  top_speed_mps: 22.222,
  average_speed_mps: 17.167,
  peak_combined_slip: 0.1111,
  limiter_samples: 0,
  bottoming_events: 0,
  start_sequence: 1,
  end_sequence: 2,
  lap_time_ms: 96_234
};

type IssueMarkerDetailFields = Pick<
  IssueMarker,
  'anchor_sequence' | 'issue_kind' | 'actual_value' | 'threshold_value' | 'threshold_operator' | 'value_label' | 'value_unit'
>;

function issueMarkerDetails(overrides: Partial<IssueMarkerDetailFields> = {}): IssueMarkerDetailFields {
  return {
    anchor_sequence: 11,
    issue_kind: 'Rear combined slip',
    actual_value: 1.28,
    threshold_value: 1.15,
    threshold_operator: 'gte',
    value_label: 'Rear combined slip',
    value_unit: null,
    ...overrides
  };
}

const lapFixtures = {
  'newer-lap': {
    sessionId: 'session-b',
    summary: newerFullLapSummary,
    sectionSummaries: {
      '11-12': {
        packet_count: 2,
        top_speed_mps: 45.678,
        average_speed_mps: 38.964,
        peak_combined_slip: 0.321,
        limiter_samples: 1,
        bottoming_events: 0,
        start_sequence: 11,
        end_sequence: 12
      },
      '11-11': {
        packet_count: 1,
        top_speed_mps: 32.25,
        average_speed_mps: 32.25,
        peak_combined_slip: 0.22,
        limiter_samples: 0,
        bottoming_events: 0,
        start_sequence: 11,
        end_sequence: 11
      }
    },
    markers: [
      {
        id: 'marker-critical',
        session_id: 'session-b',
        lap_id: 'newer-lap',
        start_sequence: 11,
        end_sequence: 12,
        metric: 'combined_slip',
        severity: 'critical',
        reason: 'High slip',
        ruleset_version: 1,
        confidence: 0.95,
        ...issueMarkerDetails({ anchor_sequence: 11 })
      }
    ],
    samples: newerLapSamples,
    rawPoint(sequence: number) {
      return {
        session_id: 'session-b',
        sequence,
        point: {
          brake: sequence === 11 ? 50 : 0,
          gear: sequence === 12 ? 4 : sequence === 11 ? 3 : 2,
          nested: { rpm: 7000 + sequence },
          speed_mps: sequence === 12 ? 45.678 : sequence === 11 ? 32.25 : 20.5
        }
      };
    }
  },
  'newer-completed-lap': {
    sessionId: 'session-b',
    summary: newerFullLapSummary,
    sectionSummaries: {
      '11-12': {
        packet_count: 2,
        top_speed_mps: 45.678,
        average_speed_mps: 38.964,
        peak_combined_slip: 0.321,
        limiter_samples: 1,
        bottoming_events: 0,
        start_sequence: 11,
        end_sequence: 12
      },
      '11-11': {
        packet_count: 1,
        top_speed_mps: 32.25,
        average_speed_mps: 32.25,
        peak_combined_slip: 0.22,
        limiter_samples: 0,
        bottoming_events: 0,
        start_sequence: 11,
        end_sequence: 11
      }
    },
    markers: [
      {
        id: 'marker-critical',
        session_id: 'session-b',
        lap_id: 'newer-completed-lap',
        start_sequence: 11,
        end_sequence: 12,
        metric: 'combined_slip',
        severity: 'critical',
        reason: 'High slip',
        ruleset_version: 1,
        confidence: 0.95,
        ...issueMarkerDetails({ anchor_sequence: 11 })
      }
    ],
    samples: newerLapSamples,
    rawPoint(sequence: number) {
      return {
        session_id: 'session-b',
        sequence,
        point: {
          brake: sequence === 11 ? 50 : 0,
          gear: sequence === 12 ? 4 : sequence === 11 ? 3 : 2,
          nested: { rpm: 7000 + sequence },
          speed_mps: sequence === 12 ? 45.678 : sequence === 11 ? 32.25 : 20.5
        }
      };
    }
  },
  'older-lap': {
    sessionId: 'session-a',
    summary: olderFullLapSummary,
    sectionSummaries: {
      '2-2': {
        packet_count: 1,
        top_speed_mps: 22.222,
        average_speed_mps: 22.222,
        peak_combined_slip: 0.0999,
        limiter_samples: 0,
        bottoming_events: 0,
        start_sequence: 2,
        end_sequence: 2
      }
    },
    markers: [
      {
        id: 'marker-info',
        session_id: 'session-a',
        lap_id: 'older-lap',
        start_sequence: 1,
        end_sequence: 2,
        metric: 'speed',
        severity: 'info',
        reason: 'Clean segment',
        ruleset_version: 1,
        confidence: 0.8,
        ...issueMarkerDetails({
          anchor_sequence: 2,
          issue_kind: 'Clean segment',
          actual_value: 22.222,
          threshold_value: 0,
          value_label: 'Speed',
          value_unit: 'mph'
        })
      }
    ],
    samples: olderLapSamples,
    rawPoint(sequence: number) {
      return {
        session_id: 'session-a',
        sequence,
        point: {
          brake: 10,
          gear: sequence === 2 ? 3 : 2,
          speed_mps: sequence === 2 ? 22.222 : 12.111
        }
      };
    }
  },
  'older-completed-lap': {
    sessionId: 'session-a',
    summary: olderFullLapSummary,
    sectionSummaries: {
      '2-2': {
        packet_count: 1,
        top_speed_mps: 22.222,
        average_speed_mps: 22.222,
        peak_combined_slip: 0.0999,
        limiter_samples: 0,
        bottoming_events: 0,
        start_sequence: 2,
        end_sequence: 2
      }
    },
    markers: [
      {
        id: 'marker-info',
        session_id: 'session-a',
        lap_id: 'older-completed-lap',
        start_sequence: 1,
        end_sequence: 2,
        metric: 'speed',
        severity: 'info',
        reason: 'Clean segment',
        ruleset_version: 1,
        confidence: 0.8,
        ...issueMarkerDetails({
          anchor_sequence: 2,
          issue_kind: 'Clean segment',
          actual_value: 22.222,
          threshold_value: 0,
          value_label: 'Speed',
          value_unit: 'mph'
        })
      }
    ],
    samples: olderLapSamples,
    rawPoint(sequence: number) {
      return {
        session_id: 'session-a',
        sequence,
        point: {
          brake: 10,
          gear: sequence === 2 ? 3 : 2,
          speed_mps: sequence === 2 ? 22.222 : 12.111
        }
      };
    }
  },
  'completed-lap': {
    sessionId: 'session-a',
    summary: olderFullLapSummary,
    sectionSummaries: {
      '2-2': {
        packet_count: 1,
        top_speed_mps: 22.222,
        average_speed_mps: 22.222,
        peak_combined_slip: 0.0999,
        limiter_samples: 0,
        bottoming_events: 0,
        start_sequence: 2,
        end_sequence: 2
      }
    },
    markers: [
      {
        id: 'marker-info',
        session_id: 'session-a',
        lap_id: 'completed-lap',
        start_sequence: 1,
        end_sequence: 2,
        metric: 'speed',
        severity: 'info',
        reason: 'Clean segment',
        ruleset_version: 1,
        confidence: 0.8,
        ...issueMarkerDetails({
          anchor_sequence: 2,
          issue_kind: 'Clean segment',
          actual_value: 22.222,
          threshold_value: 0,
          value_label: 'Speed',
          value_unit: 'mph'
        })
      }
    ],
    samples: olderLapSamples,
    rawPoint(sequence: number) {
      return {
        session_id: 'session-a',
        sequence,
        point: {
          brake: 10,
          gear: sequence === 2 ? 3 : 2,
          speed_mps: sequence === 2 ? 22.222 : 12.111
        }
      };
    }
  }
} as const;

const replayCompletedLaps: LapSummary[] = [
  {
    id: 'older-completed-lap',
    session_id: 'session-a',
    session_label: 'Sunset Sprint',
    lap_number: 1,
    status: 'lap_boundary',
    started_at_ms: 1_000,
    ended_at_ms: 2_000,
    ended_reason: 'lap_boundary',
    boundary_confidence: 'game_field'
  },
  {
    id: 'newer-completed-lap',
    session_id: 'session-b',
    session_label: 'Midnight Club',
    lap_number: 2,
    status: 'replay_complete',
    started_at_ms: 5_000,
    ended_at_ms: 6_000,
    ended_reason: 'replay_complete',
    boundary_confidence: 'game_field'
  }
];

const activeRecordingLaps: LapSummary[] = [
  {
    id: 'active-recording-lap',
    session_id: 'session-active',
    session_label: 'Night Drive',
    lap_number: 3,
    status: 'recording',
    started_at_ms: 7_000,
    ended_at_ms: null,
    ended_reason: null,
    boundary_confidence: null
  },
  {
    id: 'completed-lap',
    session_id: 'session-completed',
    session_label: 'Sunset Sprint',
    lap_number: 2,
    status: 'manual_stop',
    started_at_ms: 4_000,
    ended_at_ms: 5_000,
    ended_reason: 'manual_stop',
    boundary_confidence: 'game_field'
  }
];

const defaultTelemetryExportDefaults: TelemetryExportDefaults = {
  output_dir: 'D:/Telemetry Exports',
  filename_prefix: 'telemetry-export',
  estimate: {
    raw_packet_count: 128,
    raw_byte_count: 4096,
    curated_sample_count: 64,
    session_count: 2,
    lap_count: 4
  }
};

const defaultTelemetryExportJobs: TelemetryExportJob[] = [
  {
    id: 'export-job-completed',
    kind: 'curated_csv',
    label: 'Curated CSV',
    status: 'completed',
    status_text: 'Export completed.',
    progress: 1,
    output_dir: 'D:/Telemetry Exports',
    filename_prefix: 'night-run',
    output_files: [
      {
        filename: 'night-run_curated.csv',
        path: 'D:/Telemetry Exports/night-run_curated.csv',
        size_bytes: 2048
      }
    ],
    total_size_bytes: 2048,
    row_count: 64,
    created_at_ms: 9_000,
    started_at_ms: 9_001,
    completed_at_ms: 9_500,
    duration_ms: 499,
    error: null,
    can_cancel: false
  }
];

type FixtureMap = typeof lapFixtures;
type FixtureId = keyof FixtureMap;

type StubOptions = {
  status?: typeof statusPayload;
  capture?: typeof capturePayload;
  diagnostics?: DiagnosticsPayload;
  appAbout?: AppAboutPayload;
  updateCheck?: AppUpdateCheckResponse;
  stats?: StatsSummary;
  listenerRestart?: ListenerStatus;
  worldMapStatus?: WorldMapStatus;
  mapBuildStatus?: WorldMapStatus;
  recent?: { session_id: string | null; samples: LiveSample[]; car?: CarInfo | null };
  laps?: LapSummary[];
  sessions?: SessionSummary[];
  sessionPage?: SessionPageResponse;
  activeSession?: SessionSummary | null;
  trackProfiles?: TrackProfile[];
  trackAssetsByProfile?: Record<string, TrackAsset[]>;
  fixtures?: FixtureMap;
  telemetryExportDefaults?: TelemetryExportDefaults;
  telemetryExportJobs?: TelemetryExportJob[];
};

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status });
}

function deferredResponse() {
  let resolve!: (response: Response) => void;
  let reject!: (error?: unknown) => void;
  const promise = new Promise<Response>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

function contextKeyFor(scope: ReferenceScope) {
  return `${scope}:fixture-context`;
}

function defaultReferenceLapId(lapId: string): FixtureId | null {
  switch (lapId) {
    case 'newer-lap':
      return 'older-lap';
    case 'older-lap':
      return 'newer-lap';
    case 'newer-completed-lap':
      return 'older-completed-lap';
    case 'older-completed-lap':
      return 'newer-completed-lap';
    case 'completed-lap':
      return 'older-lap';
    default:
      return null;
  }
}

function referenceLapPayload(fixtures: FixtureMap, lapId: FixtureId, scope: ReferenceScope) {
  const fixture = fixtures[lapId];
  const lap = [...defaultLaps, ...replayCompletedLaps, ...activeRecordingLaps].find((candidate) => candidate.id === lapId);
  const lapTimeMs = lap?.lap_time_ms ?? fixture.summary.lap_time_ms ?? fixture.summary.lap_duration_ms ?? null;
  return {
    id: lapId,
    lap_id: lapId,
    session_id: fixture.sessionId,
    session_label: lap?.session_label ?? (lapId.includes('older') ? 'Sunset Sprint' : 'Midnight Club'),
    lap_number: lap?.lap_number ?? null,
    status: lap?.status ?? 'finalized',
    started_at_ms: lap?.started_at_ms ?? 1_000,
    ended_at_ms: lap?.ended_at_ms ?? 2_000,
    ended_reason: lap?.ended_reason ?? 'lap_boundary',
    boundary_confidence: lap?.boundary_confidence ?? 'game_field',
    summary: fixture.summary,
    stored_sample_count: fixture.samples.length,
    sample_count: fixture.samples.length,
    lap_time_ms: lapTimeMs,
    lap_duration_ms: lapTimeMs ?? fixture.summary.lap_duration_ms ?? fixture.summary.lap_time_ms ?? null,
    scope,
    context_key: contextKeyFor(scope),
    comparison_context_key: contextKeyFor(scope),
    source: 'session_best',
    pinned_at_ms: null
  };
}

function ghostSamplesFor(fixtures: FixtureMap, referenceLapId: FixtureId) {
  const samples = fixtures[referenceLapId].samples;
  const denominator = Math.max(1, samples.length - 1);
  return samples.map((sample, index) => ({
    ...sample,
    lap_progress: index / denominator,
    elapsed_ms: index * 1_000
  }));
}

function deltaSummaryFor(fixtures: FixtureMap, lapId: FixtureId, referenceLapId: FixtureId | null, start: string | null, end: string | null) {
  const currentSamples = fixtures[lapId].samples.filter((sample) => {
    if (!start || !end) return true;
    return sample.sequence >= Number(start) && sample.sequence <= Number(end);
  });
  const referenceSampleCount = referenceLapId ? fixtures[referenceLapId].samples.length : 0;
  const isSection = !!start && !!end;
  return {
    start_sequence: start ? Number(start) : currentSamples[0]?.sequence ?? null,
    end_sequence: end ? Number(end) : currentSamples[currentSamples.length - 1]?.sequence ?? null,
    sample_count: currentSamples.length,
    current_sample_count: currentSamples.length,
    reference_sample_count: referenceSampleCount,
    time_delta_ms: referenceSampleCount > 0 ? (isSection ? 500 : -1500) : null,
    average_speed_delta_mps: referenceSampleCount > 0 ? (isSection ? 2.5 : 4.25) : null,
    max_gain_ms: referenceSampleCount > 0 ? (isSection ? 250 : 1500) : 0,
    max_loss_ms: referenceSampleCount > 0 ? (isSection ? 500 : 250) : 0,
    points: currentSamples.map((sample, index) => ({
      sequence: sample.sequence,
      lap_progress: currentSamples.length <= 1 ? 0 : index / (currentSamples.length - 1),
      current_elapsed_ms: index * 1_000,
      reference_elapsed_ms: index * 1_000 + (isSection ? -500 : 1500),
      time_delta_ms: referenceSampleCount > 0 ? (isSection ? 500 : -1500) : null,
      current_speed_mps: sample.speed_mps,
      reference_speed_mps: referenceSampleCount > 0 ? sample.speed_mps - (isSection ? 2.5 : 4.25) : null,
      speed_delta_mps: referenceSampleCount > 0 ? (isSection ? 2.5 : 4.25) : null
    }))
  };
}

function lapTimeForAggregate(lap: LapSummary): number | null {
  const status = String(lap.status ?? '').trim().toLowerCase();
  if (['active', 'recording', 'uncertain', 'partial_lap', 'no_lap', 'no_lap_signal', 'event_exit'].includes(status)) {
    return null;
  }
  if (lap.lap_time_ms !== null && lap.lap_time_ms !== undefined && Number.isFinite(lap.lap_time_ms)) {
    return lap.lap_time_ms;
  }
  if (lap.ended_at_ms !== null && lap.ended_at_ms >= lap.started_at_ms) {
    return lap.ended_at_ms - lap.started_at_ms;
  }
  return null;
}

function sessionsWithAggregates(sessions: SessionSummary[], laps: LapSummary[]): SessionSummary[] {
  return sessions.map((session) => {
    const sessionLaps = laps.filter((lap) => lap.session_id === session.id);
    const completedTimes = sessionLaps
      .map(lapTimeForAggregate)
      .filter((value): value is number => value !== null);
    const total = completedTimes.reduce((sum, value) => sum + value, 0);
    return {
      ...session,
      lap_count: sessionLaps.length,
      completed_lap_count: completedTimes.length,
      best_lap_time_ms: completedTimes.length > 0 ? Math.min(...completedTimes) : null,
      average_lap_time_ms: completedTimes.length > 0 ? total / completedTimes.length : null,
      total_lap_time_ms: completedTimes.length > 0 ? total : null
    };
  });
}

function createDefaultFetchHandler(options?: StubOptions) {
  let status = options?.status ?? statusPayload;
  let capture = options?.capture ?? capturePayload;
  let diagnostics = options?.diagnostics ?? defaultDiagnosticsPayload;
  let appAbout = options?.appAbout ?? defaultAppAboutPayload;
  const updateCheck = options?.updateCheck ?? defaultUpdateCheckPayload;
  const stats = options?.stats ?? defaultStatsSummary;
  const listenerRestart = options?.listenerRestart ?? {
    ...status.listener,
    state: 'waiting',
    message: 'waiting for telemetry after restart'
  };
  let worldMapStatus = options?.worldMapStatus ?? defaultWorldMapStatus;
  const mapBuildStatus = options?.mapBuildStatus;
  let recent = options?.recent ?? { session_id: 'session-live', samples: recoveredSamples };
  let laps = (options?.laps ?? defaultLaps).map((lap) => ({ ...lap }));
  let sessions = (options?.sessions ?? defaultSessions).map((session) => ({ ...session }));
  let activeSession = options?.activeSession ?? sessions.find((session) => session.status === 'active') ?? null;
  let sessionPage = options?.sessionPage ?? {
    sessions: sessionsWithAggregates(sessions, laps),
    page: 1,
    page_size: 100,
    total: sessions.length,
    total_pages: sessions.length === 0 ? 0 : 1
  };

  function refreshSessionPageState() {
    const nextSessions = sessionsWithAggregates(sessions, laps);
    const pageSize = sessionPage.page_size || 100;
    sessionPage = {
      ...sessionPage,
      sessions: nextSessions,
      total: nextSessions.length,
      total_pages: nextSessions.length === 0 ? 0 : Math.ceil(nextSessions.length / pageSize)
    };
  }
  const trackProfiles = (options?.trackProfiles ?? defaultTrackProfiles).map((profile) => ({ ...profile }));
  const sourceTrackAssetsByProfile = options?.trackAssetsByProfile ?? {};
  const trackAssetsByProfile: Record<string, TrackAsset[]> = Object.fromEntries(
    Object.entries(sourceTrackAssetsByProfile).map(([profileId, assets]) => [profileId, assets.map((asset) => ({ ...asset, transform: { ...asset.transform } }))])
  );
  const fixtures = options?.fixtures ?? lapFixtures;
  const telemetryExportDefaults = options?.telemetryExportDefaults ?? defaultTelemetryExportDefaults;
  let telemetryExportJobs = (options?.telemetryExportJobs ?? defaultTelemetryExportJobs).map((job) => ({
    ...job,
    output_files: job.output_files.map((file) => ({ ...file }))
  }));

  return async (url: string, init?: RequestInit) => {
    const parsed = new URL(url, 'http://localhost');
    const pathname = parsed.pathname;

    if (pathname === '/api/status') return jsonResponse(status);
    if (pathname === '/api/capture') return jsonResponse(capture);
    if (pathname === '/api/app/about') return jsonResponse(appAbout);
    if (pathname === '/api/app/update/check' && init?.method === 'POST') return jsonResponse(updateCheck);
    if (pathname === '/api/map/status') return jsonResponse(worldMapStatus);
    if (pathname === '/api/map/settings' && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body ?? '{}')) as Partial<WorldMapStatus['settings']>;
      const nextSettings = {
        ...worldMapStatus.settings,
        ...body
      };
      const sourceAvailable = Boolean(nextSettings.fh6_media_root);
      const preservedTileSet = sourceAvailable && worldMapStatus.tile_set?.status === 'ready' ? worldMapStatus.tile_set : null;
      worldMapStatus = {
        ...worldMapStatus,
        status: !nextSettings.world_map_enabled
          ? 'disabled'
          : !sourceAvailable
            ? 'source_missing'
            : preservedTileSet
              ? 'ready'
              : 'cache_missing',
        settings: nextSettings,
        source: {
          available: sourceAvailable,
          path: sourceAvailable
            ? `${nextSettings.fh6_media_root}/media/UI/Textures/Data_Bound/Map_Brio_${nextSettings.world_map_season[0].toUpperCase()}${nextSettings.world_map_season.slice(1)}.zip`
            : null,
          season: nextSettings.world_map_season
        },
        tile_set: preservedTileSet
      };
      return jsonResponse(worldMapStatus);
    }
    if (pathname === '/api/map/cache/build' && init?.method === 'POST') {
      if (mapBuildStatus) {
        worldMapStatus = {
          ...mapBuildStatus,
          settings: {
            ...worldMapStatus.settings,
            ...mapBuildStatus.settings
          }
        };
        return jsonResponse(worldMapStatus);
      }
      worldMapStatus = {
        ...worldMapStatus,
        status: 'ready',
        settings: {
          ...worldMapStatus.settings,
          world_map_enabled: true
        },
        source: {
          ...worldMapStatus.source,
          available: true,
          season: worldMapStatus.settings.world_map_season
        },
        tile_set: readyWorldMapTileSet
      };
      return jsonResponse(worldMapStatus);
    }
    if (pathname === '/api/settings' && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body ?? '{}')) as { unit_system?: string; preferred_overlay?: string };
      const nextSettings = {
        ...status.settings,
        ...body
      };
      status = {
        ...status,
        settings: nextSettings
      };
      capture = {
        ...capture,
        settings: {
          ...(capture.settings ?? status.settings),
          ...nextSettings
        }
      };
      return jsonResponse(nextSettings);
    }
    if (pathname === '/api/listener/restart' && init?.method === 'POST') {
      status = {
        ...status,
        listener: listenerRestart,
        capture: {
          ...status.capture,
          listener: listenerRestart
        }
      };
      capture = {
        ...capture,
        listener: listenerRestart
      };
      return jsonResponse(listenerRestart);
    }
    if (pathname === '/api/telemetry/delete-all' && init?.method === 'DELETE') {
      sessions = [];
      laps = [];
      activeSession = null;
      recent = { session_id: null, samples: [] };
      refreshSessionPageState();
      diagnostics = {
        ...diagnostics,
        row_counts: {
          ...diagnostics.row_counts,
          sessions: 0,
          laps: 0,
          packets: 0,
          issue_markers: 0
        }
      };
      return jsonResponse({
        deleted: true,
        deleted_counts: {
          sessions: 2,
          laps: 4,
          packet_blobs: 128,
          issue_markers: 3,
          lap_samples: 128,
          lap_summaries: 4,
          comparison_refs: 0,
          track_match_candidates: 0,
          lifetime_stat_laps: 4,
          session_counters: 1
        },
        row_counts: diagnostics.row_counts
      });
    }
    if (pathname === '/api/diagnostics') return jsonResponse(diagnostics);
    if (pathname === '/api/replay/import-jobs') return jsonResponse({ jobs: [] });
    if (pathname === '/api/telemetry/export-defaults') return jsonResponse(telemetryExportDefaults);
    if (pathname === '/api/telemetry/export-jobs' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}')) as { kind: TelemetryExportJob['kind']; output_dir: string; filename_prefix?: string };
      const job: TelemetryExportJob = {
        id: `export-job-${telemetryExportJobs.length + 1}`,
        kind: body.kind,
        label: body.kind === 'curated_csv' ? 'Curated CSV' : body.kind === 'raw_csv' ? 'Raw CSV' : 'Raw binary package',
        status: 'queued',
        status_text: 'Queued',
        progress: 0,
        output_dir: body.output_dir,
        filename_prefix: body.filename_prefix ?? null,
        output_files: [],
        total_size_bytes: 0,
        row_count: 0,
        created_at_ms: 10_000 + telemetryExportJobs.length,
        started_at_ms: null,
        completed_at_ms: null,
        duration_ms: null,
        error: null,
        can_cancel: true
      };
      telemetryExportJobs = [job, ...telemetryExportJobs];
      return jsonResponse({ job });
    }
    if (pathname === '/api/telemetry/export-jobs') return jsonResponse({ jobs: telemetryExportJobs });
    const exportCancelMatch = pathname.match(/^\/api\/telemetry\/export-jobs\/([^/]+)\/cancel$/);
    if (exportCancelMatch && init?.method === 'POST') {
      const jobId = decodeURIComponent(exportCancelMatch[1]);
      telemetryExportJobs = telemetryExportJobs.map((job) => job.id === jobId ? { ...job, status: 'cancelled', status_text: 'Cancelled', can_cancel: false } : job);
      return jsonResponse({ job: telemetryExportJobs.find((job) => job.id === jobId) }, telemetryExportJobs.some((job) => job.id === jobId) ? 200 : 404);
    }
    if (pathname === '/api/stats') return jsonResponse({ stats });
    if (pathname === '/api/live/recent' && parsed.searchParams.get('limit') === '200') return jsonResponse(recent);
    if (pathname === '/api/laps') return jsonResponse({ laps });
    if (pathname === '/api/sessions/active') return jsonResponse({ session: activeSession });
    if (pathname === '/api/sessions/start' && init?.method === 'POST') {
      const body = init.body ? JSON.parse(String(init.body)) as { label?: string } : {};
      const session: SessionSummary = {
        id: `session-${sessions.length + 1}`,
        user_id: 'local-user',
        label: body.label ?? `Session ${sessions.length + 1}`,
        status: 'active',
        started_at_ms: 7_000,
        ended_at_ms: null,
        ended_reason: null,
        last_active_at_ms: 7_000,
        lap_count: 0,
        completed_lap_count: 0,
        best_lap_time_ms: null,
        average_lap_time_ms: null,
        total_lap_time_ms: null
      };
      sessions = [{ ...session }, ...sessions.map((candidate) => (
        candidate.status === 'active'
          ? { ...candidate, status: 'user_end', ended_at_ms: 7_000, ended_reason: 'new_session_started', last_active_at_ms: 7_000 }
          : candidate
      ))];
      activeSession = session;
      refreshSessionPageState();
      return jsonResponse({ session });
    }
    const sessionActivateMatch = pathname.match(/^\/api\/sessions\/([^/]+)\/activate$/);
    if (sessionActivateMatch && init?.method === 'POST') {
      const sessionId = sessionActivateMatch[1];
      const activatedAt = 8_000;
      sessions = sessions.map((session) => (
        session.id === sessionId
          ? { ...session, status: 'active', ended_at_ms: null, ended_reason: null, last_active_at_ms: activatedAt }
          : session.status === 'active'
            ? { ...session, status: 'session_activated', ended_at_ms: activatedAt, ended_reason: 'session_activated', last_active_at_ms: activatedAt }
            : session
      ));
      refreshSessionPageState();
      activeSession = sessionsWithAggregates(sessions, laps).find((candidate) => candidate.id === sessionId) ?? null;
      return jsonResponse({ session: activeSession }, activeSession ? 200 : 404);
    }
    const sessionLapsMatch = pathname.match(/^\/api\/sessions\/([^/]+)\/laps$/);
    if (sessionLapsMatch) {
      const sessionId = sessionLapsMatch[1];
      return jsonResponse({ session_id: sessionId, laps: laps.filter((lap) => lap.session_id === sessionId) });
    }
    const sessionMutationMatch = pathname.match(/^\/api\/sessions\/([^/]+)$/);
    if (sessionMutationMatch && init?.method === 'PATCH') {
      const sessionId = sessionMutationMatch[1];
      const body = JSON.parse(String(init.body ?? '{}')) as { label: string };
      sessions = sessions.map((session) => session.id === sessionId ? { ...session, label: body.label } : session);
      if (activeSession?.id === sessionId) activeSession = { ...activeSession, label: body.label };
      refreshSessionPageState();
      const session = sessionsWithAggregates(sessions, laps).find((candidate) => candidate.id === sessionId) ?? null;
      return jsonResponse({ session }, session ? 200 : 404);
    }
    if (sessionMutationMatch && init?.method === 'DELETE') {
      const sessionId = sessionMutationMatch[1];
      const deleted = sessionsWithAggregates(sessions, laps).find((session) => session.id === sessionId) ?? null;
      sessions = sessions.filter((session) => session.id !== sessionId);
      laps = laps.filter((lap) => lap.session_id !== sessionId);
      if (activeSession?.id === sessionId) activeSession = null;
      refreshSessionPageState();
      return jsonResponse({ deleted: Boolean(deleted), session_id: sessionId, session: deleted });
    }
    if (pathname === '/api/sessions') return jsonResponse(sessionPage);
    const trackAssetsForProfileMatch = pathname.match(/^\/api\/tracks\/profiles\/([^/]+)\/assets$/);
    if (trackAssetsForProfileMatch && init?.method === 'POST') {
      const profileId = trackAssetsForProfileMatch[1];
      const body = JSON.parse(String(init.body ?? '{}')) as {
        filename: string;
        sourcePath: string;
        mimeType: string;
        sizeBytes: number;
        transform?: TrackAsset['transform'];
      };
      const asset: TrackAsset = {
        id: `asset-created-${(trackAssetsByProfile[profileId] ?? []).length + 1}`,
        track_profile_id: profileId,
        filename: body.filename,
        mime_type: body.mimeType,
        size_bytes: body.sizeBytes,
        transform: body.transform ?? {
          scale: 1,
          rotate_deg: 0,
          translate_x: 0,
          translate_y: 0
        },
        created_at_ms: 3_000,
        updated_at_ms: 3_000,
        file_url: `/api/tracks/assets/asset-created-${(trackAssetsByProfile[profileId] ?? []).length + 1}/file`
      };
      trackAssetsByProfile[profileId] = [...(trackAssetsByProfile[profileId] ?? []), asset];
      return jsonResponse({ asset });
    }
    if (trackAssetsForProfileMatch) {
      const profileId = trackAssetsForProfileMatch[1];
      return jsonResponse({ assets: trackAssetsByProfile[profileId] ?? [] });
    }
    const assetTransformMatch = pathname.match(/^\/api\/tracks\/assets\/([^/]+)\/transform$/);
    if (assetTransformMatch && init?.method === 'PATCH') {
      const assetId = assetTransformMatch[1];
      const transform = JSON.parse(String(init.body ?? '{}')) as TrackAsset['transform'];
      for (const assets of Object.values(trackAssetsByProfile)) {
        const asset = assets.find((candidate) => candidate.id === assetId);
        if (!asset) continue;
        asset.transform = transform;
        asset.updated_at_ms = 4_000;
        return jsonResponse({ asset });
      }
      return jsonResponse({ detail: 'unknown track_asset_id' }, 404);
    }
    const assetDeleteMatch = pathname.match(/^\/api\/tracks\/assets\/([^/]+)$/);
    if (assetDeleteMatch && init?.method === 'DELETE') {
      const assetId = assetDeleteMatch[1];
      for (const [profileId, assets] of Object.entries(trackAssetsByProfile)) {
        const asset = assets.find((candidate) => candidate.id === assetId);
        if (!asset) continue;
        trackAssetsByProfile[profileId] = assets.filter((candidate) => candidate.id !== assetId);
        return jsonResponse({ deleted: true, asset_id: assetId, asset });
      }
      return jsonResponse({ detail: 'unknown track_asset_id' }, 404);
    }
    if (pathname === '/api/tracks/profiles' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}')) as { name: string; layout: string; source?: string; confidence?: string };
      const profile: TrackProfile = {
        id: `profile-created-${trackProfiles.length + 1}`,
        owner_user_id: 'local-user',
        name: body.name,
        layout: body.layout,
        source: body.source ?? 'manual',
        confidence: body.confidence ?? 'user',
        shape_signature: null,
        created_at_ms: 3_000,
        updated_at_ms: 3_000
      };
      trackProfiles.unshift(profile);
      return jsonResponse({ profile });
    }
    if (pathname === '/api/tracks/profiles') return jsonResponse({ profiles: trackProfiles });
    const updateProfileMatch = pathname.match(/^\/api\/tracks\/profiles\/([^/]+)$/);
    if (updateProfileMatch && init?.method === 'PATCH') {
      const profileId = updateProfileMatch[1];
      const body = JSON.parse(String(init.body ?? '{}')) as { name: string; layout: string };
      const existing = trackProfiles.find((profile) => profile.id === profileId);
      if (!existing) return jsonResponse({ detail: 'unknown track_profile_id' }, 404);
      existing.name = body.name;
      existing.layout = body.layout;
      existing.updated_at_ms = 4_000;
      return jsonResponse({ profile: existing });
    }
    const assignProfileMatch = pathname.match(/^\/api\/tracks\/profiles\/([^/]+)\/assign$/);
    if (assignProfileMatch && init?.method === 'POST') {
      const profileId = assignProfileMatch[1];
      const body = JSON.parse(String(init.body ?? '{}')) as { sessionId: string; lapId?: string };
      const existing = trackProfiles.find((profile) => profile.id === profileId);
      if (!existing) return jsonResponse({ detail: 'unknown track_profile_id' }, 404);
      return jsonResponse({
        assignment: {
          profile_id: profileId,
          session_id: body.sessionId,
          lap_id: body.lapId ?? null
        },
        profile: existing
      });
    }
    if (pathname === '/api/tracks/profiles/merge' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}')) as { keepProfileId: string; mergeProfileId: string };
      const keepProfile = trackProfiles.find((profile) => profile.id === body.keepProfileId);
      if (!keepProfile) return jsonResponse({ detail: 'unknown track_profile_id' }, 404);
      return jsonResponse({ profile: keepProfile, merged_profile_id: body.mergeProfileId });
    }

    const lapDeleteMatch = pathname.match(/^\/api\/laps\/([^/]+)$/);
    if (lapDeleteMatch && init?.method === 'DELETE') {
      const lapId = lapDeleteMatch[1];
      const lap = laps.find((candidate) => candidate.id === lapId);
      if (!lap) return jsonResponse({ detail: 'unknown lap_id' }, 404);
      laps = laps.filter((candidate) => candidate.id !== lapId);
      refreshSessionPageState();
      return jsonResponse({ deleted: true, lap_id: lapId, session_id: lap.session_id, lap });
    }

    const lapSummaryMatch = pathname.match(/^\/api\/laps\/([^/]+)\/summary$/);
    if (lapSummaryMatch) {
      const lapId = lapSummaryMatch[1] as keyof FixtureMap;
      const fixture = fixtures[lapId];
      const start = parsed.searchParams.get('start_sequence');
      const end = parsed.searchParams.get('end_sequence');
      const sectionKey = start && end ? `${start}-${end}` : null;
      return jsonResponse({
        lap_id: lapId,
        session_id: fixture.sessionId,
        summary: sectionKey ? fixture.sectionSummaries[sectionKey as keyof typeof fixture.sectionSummaries] : fixture.summary,
        ...(sectionKey ? {} : { car: carInfoForLapId(lapId) })
      });
    }

    const lapMarkersMatch = pathname.match(/^\/api\/laps\/([^/]+)\/markers$/);
    if (lapMarkersMatch) {
      const lapId = lapMarkersMatch[1] as keyof FixtureMap;
      const fixture = fixtures[lapId];
      return jsonResponse({ lap_id: lapId, session_id: fixture.sessionId, markers: fixture.markers });
    }

    const lapSamplesMatch = pathname.match(/^\/api\/laps\/([^/]+)\/samples$/);
    if (lapSamplesMatch) {
      const lapId = lapSamplesMatch[1] as keyof FixtureMap;
      const fixture = fixtures[lapId];
      return jsonResponse({ lap_id: lapId, samples: fixture.samples });
    }

    const lapTrackMatchMatch = pathname.match(/^\/api\/laps\/([^/]+)\/track-match$/);
    if (lapTrackMatchMatch) {
      const lapId = lapTrackMatchMatch[1] as keyof FixtureMap;
      const fixture = fixtures[lapId];
      return jsonResponse({
        lap_id: lapId,
        session_id: fixture.sessionId,
        candidates: [
          {
            track_profile_id: 'profile-emerald',
            track_profile_name: 'Emerald Circuit',
            track_profile_layout: 'Full',
            score: 0.96,
            confidence: 'suggested'
          }
        ]
      });
    }

    const referenceMatch = pathname.match(/^\/api\/laps\/([^/]+)\/reference$/);
    if (referenceMatch) {
      const lapId = referenceMatch[1] as FixtureId;
      const scope = (parsed.searchParams.get('scope') ?? 'track_car') as ReferenceScope;
      const referenceLapId = defaultReferenceLapId(lapId);
      return jsonResponse({
        lap_id: lapId,
        scope,
        context_key: contextKeyFor(scope),
        reference: referenceLapId ? referenceLapPayload(fixtures, referenceLapId, scope) : null
      });
    }

    const ghostMatch = pathname.match(/^\/api\/laps\/([^/]+)\/ghost$/);
    if (ghostMatch) {
      const lapId = ghostMatch[1] as FixtureId;
      const scope = (parsed.searchParams.get('scope') ?? 'track_car') as ReferenceScope;
      const referenceLapId = defaultReferenceLapId(lapId);
      const reference = referenceLapId ? referenceLapPayload(fixtures, referenceLapId, scope) : null;
      return jsonResponse({
        lap_id: lapId,
        scope,
        context_key: contextKeyFor(scope),
        reference,
        samples: referenceLapId ? ghostSamplesFor(fixtures, referenceLapId) : []
      });
    }

    const deltaMatch = pathname.match(/^\/api\/laps\/([^/]+)\/delta$/);
    if (deltaMatch) {
      const lapId = deltaMatch[1] as FixtureId;
      const scope = (parsed.searchParams.get('scope') ?? 'track_car') as ReferenceScope;
      const referenceLapId = defaultReferenceLapId(lapId);
      const reference = referenceLapId ? referenceLapPayload(fixtures, referenceLapId, scope) : null;
      return jsonResponse({
        lap_id: lapId,
        scope,
        context_key: contextKeyFor(scope),
        reference,
        summary: deltaSummaryFor(
          fixtures,
          lapId,
          referenceLapId,
          parsed.searchParams.get('start_sequence'),
          parsed.searchParams.get('end_sequence')
        )
      });
    }

    const pointMatch = pathname.match(/^\/api\/sessions\/([^/]+)\/points\/(\d+)$/);
    if (pointMatch) {
      const sessionId = pointMatch[1];
      const sequence = Number(pointMatch[2]);
      const fixture = Object.values(fixtures).find((candidate) => candidate.sessionId === sessionId);
      return jsonResponse(fixture?.rawPoint(sequence) ?? { session_id: sessionId, sequence, point: {} });
    }

    if (pathname === '/api/capture/mode' && init?.method === 'POST') {
      return jsonResponse({
        ...capture,
        mode: 'manual',
        phase: 'idle',
        recording: { ...capture.recording, mode: 'manual', phase: 'idle', active: false },
        settings: { ...capture.settings, capture_mode: 'manual' }
      });
    }

    if (pathname === '/api/capture/start' && init?.method === 'POST') {
      return jsonResponse({
        ...capture,
        mode: 'manual',
        phase: 'recording',
        recording: { ...capture.recording, mode: 'manual', phase: 'recording', active: true },
        settings: { ...capture.settings, capture_mode: 'manual' }
      });
    }

    if (pathname === '/api/capture/stop' && init?.method === 'POST') {
      return jsonResponse({
        ...capture,
        mode: 'manual',
        phase: 'idle',
        recording: { ...capture.recording, mode: 'manual', phase: 'idle', active: false },
        settings: { ...capture.settings, capture_mode: 'manual' }
      });
    }

    return jsonResponse({ detail: 'not found' }, 404);
  };
}

function stubApiFetch(options?: StubOptions) {
  const defaultHandler = createDefaultFetchHandler(options);
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => defaultHandler(requestUrl(input), init));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  onerror: (() => void) | null = null;
  closed = false;
  closeCalls = 0;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    this.listeners[type] = [...(this.listeners[type] ?? []), handler];
  }

  emit(type: string, data: unknown) {
    this.emitRaw(type, JSON.stringify(data));
  }

  emitRaw(type: string, data: string) {
    for (const handler of this.listeners[type] ?? []) {
      handler(new MessageEvent(type, { data }));
    }
  }

  close() {
    this.closed = true;
    this.closeCalls += 1;
  }
}

function createCanvasContextMock() {
  return {
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
    globalAlpha: 1,
    lineWidth: 0,
    strokeStyle: '#000'
  } as unknown as CanvasRenderingContext2D;
}

async function openSettingsModal() {
  const menu = screen.getByRole('navigation', { name: 'Main menu' });
  await fireEvent.click(within(menu).getByRole('button', { name: 'Settings' }));
  return screen.findByRole('dialog', { name: 'Forza Telemetry Tracker settings' });
}

async function openImportTelemetryModal() {
  const menu = screen.getByRole('navigation', { name: 'Main menu' });
  await fireEvent.click(within(menu).getByRole('button', { name: 'Import raw telemetry' }));
  return screen.findByRole('dialog', { name: 'Import raw telemetry' });
}

async function openExportTelemetryModal() {
  const menu = screen.getByRole('navigation', { name: 'Main menu' });
  await fireEvent.click(within(menu).getByRole('button', { name: 'Export telemetry' }));
  return screen.findByRole('dialog', { name: 'Export telemetry' });
}

function getVisualisationStage() {
  return screen.getByTestId('visualisation-stage');
}

function getFloatingCaptureControls() {
  return within(getVisualisationStage()).getByRole('group', { name: /Floating capture controls/i });
}

function getCarInfoCard() {
  return within(getVisualisationStage()).getByRole('complementary', { name: /Car info/i });
}

function getSectionSummaryCard() {
  return within(getVisualisationStage()).getByRole('complementary', { name: /Section summary/i });
}

function getSummaryDragHandle() {
  return within(getSectionSummaryCard()).getByRole('button', { name: /Drag section summary/i });
}

function getTelemetryStatus() {
  return screen.getByRole('status', { name: 'Telemetry status' });
}

async function findListenerStatus(accessibleLabel: RegExp) {
  return screen.findByLabelText(accessibleLabel);
}

function getToastStack() {
  return screen.getByLabelText('Status notifications');
}

async function findToast(message: string | RegExp) {
  return within(getToastStack()).findByText(message);
}

function sessionPageCallMatches(url: string, expected: Record<string, string>) {
  const parsed = new URL(url, 'http://localhost');
  if (parsed.pathname !== '/api/sessions') return false;
  return Object.entries(expected).every(([key, value]) => parsed.searchParams.get(key) === value);
}

function hasSessionPageCall(calls: string[], expected: Record<string, string> = { page: '1', page_size: '100' }) {
  return calls.some((url) => sessionPageCallMatches(url, expected));
}

function renderApp(options: { loadedSessionId?: string | null } = {}) {
  if (Object.prototype.hasOwnProperty.call(options, 'loadedSessionId')) {
    return options.loadedSessionId
      ? render(App, { props: { initialLoadedSessionId: options.loadedSessionId } })
      : render(App);
  }
  return render(App, { props: { initialLoadedSessionId: 'session-b' } });
}

async function openSessionBrowser() {
  await waitFor(() => expect(FakeEventSource.instances.length).toBeGreaterThan(0));
  const menu = screen.getByRole('navigation', { name: 'Main menu' });
  await fireEvent.click(within(menu).getByRole('button', { name: 'Session browser' }));
  return screen.findByRole('dialog', { name: 'Sessions' });
}

async function loadSessionFromBrowser(sessionLabel: string) {
  await openSessionBrowser();
  await fireEvent.click(await screen.findByRole('button', { name: `Open ${sessionLabel}` }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Sessions' })).not.toBeInTheDocument());
}

function stubDesktopFolderPicker(selectedPath: string | null) {
  const choose_fh6_install_folder = vi.fn(async (_currentPath: string | null = null) => selectedPath);
  vi.stubGlobal('pywebview', {
    api: {
      choose_fh6_install_folder
    }
  });
  return choose_fh6_install_folder;
}

beforeAll(() => {
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    writable: true,
    value: vi.fn()
  });
  Object.defineProperty(HTMLCanvasElement.prototype, 'getBoundingClientRect', {
    configurable: true,
    writable: true,
    value: vi.fn()
  });
});

afterAll(() => {
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    writable: true,
    value: originalGetContext
  });
  Object.defineProperty(HTMLCanvasElement.prototype, 'getBoundingClientRect', {
    configurable: true,
    writable: true,
    value: originalGetBoundingClientRect
  });
});

describe('App', () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    canvasContext = createCanvasContextMock();
    (HTMLCanvasElement.prototype.getContext as ReturnType<typeof vi.fn>).mockImplementation(() => canvasContext);
    (HTMLCanvasElement.prototype.getBoundingClientRect as ReturnType<typeof vi.fn>).mockReturnValue({
      left: 0,
      top: 0,
      width: 900,
      height: 560,
      right: 900,
      bottom: 560,
      x: 0,
      y: 0,
      toJSON: () => ({})
    } as DOMRect);
    vi.stubGlobal('EventSource', FakeEventSource);
    stubApiFetch();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders the fixed dashboard shell, slide-out menu, floating timeline, and status strip', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderApp();

    expect(await screen.findByText('Forza Telemetry Tracker')).toBeInTheDocument();
    expect(await findListenerStatus(/Listener waiting: waiting for telemetry/i)).toBeInTheDocument();

    const shell = screen.getByTestId('dashboard-shell');
    expect(shell).toHaveClass('dashboard-shell');

    const menu = screen.getByRole('navigation', { name: 'Main menu' });
    expect(menu).toHaveAttribute('data-expanded', 'false');
    const expandMenu = screen.getByRole('button', { name: 'Expand menu' });
    expect(expandMenu).toHaveAttribute('title', 'Expand menu');
    expect(expandMenu).toHaveAttribute('aria-expanded', 'false');
    expect(expandMenu).toHaveAttribute('aria-controls', 'slide-menu-actions');
    expect(expandMenu).not.toHaveAttribute('aria-pressed');
    expect(screen.queryByText('Import raw telemetry')).not.toBeInTheDocument();

    const stage = screen.getByTestId('visualisation-stage');
    expect(stage).toHaveAttribute('data-menu-overlay', 'false');
    await fireEvent.click(expandMenu);
    expect(menu).toHaveAttribute('data-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Collapse menu' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Import raw telemetry')).toBeInTheDocument();
    expect(screen.getByText('Export telemetry')).toBeInTheDocument();
    expect(screen.getByText('About')).toBeInTheDocument();
    expect(screen.getByText('Feedback')).toBeInTheDocument();
    const expandedMenuLabels = within(menu).getAllByRole('button').map((button) => button.textContent?.trim());
    expect(expandedMenuLabels.indexOf('Export telemetry')).toBe(expandedMenuLabels.indexOf('Import raw telemetry') + 1);
    expect(expandedMenuLabels.indexOf('Export telemetry')).toBeLessThan(expandedMenuLabels.indexOf('Session browser'));
    expect(expandedMenuLabels.indexOf('About')).toBeGreaterThan(expandedMenuLabels.indexOf('Settings'));
    const feedbackLink = within(menu).getByRole('link', { name: 'Feedback' });
    expect(feedbackLink).toHaveAttribute('href', 'https://github.com/seevydeepy/forza-telemetry-tracker/issues');
    expect(feedbackLink).toHaveAttribute('target', '_blank');
    expect(feedbackLink).toHaveAttribute('rel', 'noreferrer');
    expect(within(menu).queryByRole('button', { name: 'Track tools' })).not.toBeInTheDocument();
    expect(within(menu).queryByRole('button', { name: 'Open keyboard shortcuts' })).not.toBeInTheDocument();
    expect(stage).toHaveAttribute('data-menu-overlay', 'true');

    expect(screen.getByRole('button', { name: 'Open diagnostics' })).toHaveAttribute('title', 'Open diagnostics');
    expect(screen.getByRole('button', { name: 'Settings' })).toHaveAttribute('title', 'Open telemetry tracker settings');

    const footer = screen.getByTestId('dashboard-footer');
    expect(screen.getAllByRole('region', { name: /Review timeline/i })).toHaveLength(1);
    expect(within(footer).queryByRole('region', { name: 'Review timeline' })).toBeNull();
    expect(within(footer).getByRole('status', { name: 'Telemetry status' })).toHaveTextContent('UDP 127.0.0.1:5400');
    expect(getTelemetryStatus()).toHaveTextContent('Listener waiting');
    expect(within(footer).queryByRole('button', { name: 'Live follow' })).toBeNull();
    expect(within(stage).getByRole('button', { name: 'Live follow' })).toHaveTextContent('Live follow running');
    expect(consoleError).not.toHaveBeenCalled();
  });

  it('starts without auto-loading the active or first session when no session is explicitly loaded', async () => {
    const fetchMock = stubApiFetch();
    renderApp({ loadedSessionId: null });

    await findToast('Tracker ready');

    expect(screen.queryByRole('complementary', { name: /Loaded session laps/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show history drawer' })).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
      expect(calls).not.toContain('/api/sessions/session-a/laps');
      expect(calls).not.toContain('/api/sessions/session-b/laps');
    });
  });

  it('places capture controls on the map and toggles a draggable section summary card', async () => {
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    const stage = getVisualisationStage();
    expect(within(stage).getByRole('group', { name: /Floating capture controls/i })).toBeInTheDocument();

    expect(within(stage).queryByRole('complementary', { name: /Section summary/i })).not.toBeInTheDocument();
    await fireEvent.click(within(stage).getByRole('button', { name: 'Show section summary' }));

    const summary = within(stage).getByRole('complementary', { name: /Section summary/i });
    expect(summary).toHaveTextContent(/Full lap summary/i);

    await fireEvent.click(within(summary).getByRole('button', { name: 'Hide section summary' }));
    expect(within(stage).queryByRole('complementary', { name: /Section summary/i })).toBeNull();
    await waitFor(() => expect(within(stage).getByRole('button', { name: 'Show section summary' })).toHaveFocus());

    await fireEvent.click(within(stage).getByRole('button', { name: 'Show section summary' }));
    expect(within(stage).getByRole('complementary', { name: /Section summary/i })).toBeInTheDocument();
  });

  it('shows the compact car card and expands curated details', async () => {
    renderApp();

    await waitFor(() => expect(getCarInfoCard()).toHaveTextContent('Mazda Furai'));
    const card = getCarInfoCard();
    expect(card).toHaveAttribute('data-car-info-anchor', 'bottom-left');
    expect(card).toHaveAttribute('data-car-info-x', '0');
    expect(card).toHaveAttribute('data-car-info-y', '0');
    const dragHandle = within(card).getByRole('button', { name: /Drag car info/i });
    expect(within(card).queryByText('Car Details')).not.toBeInTheDocument();
    expect(dragHandle).toHaveTextContent('Mazda Furai');
    expect(dragHandle).toHaveTextContent('2008');
    expect(within(card).getByRole('button', { name: 'Dismiss card' })).toBeInTheDocument();
    expect(card).toHaveTextContent('R | 998');
    expect(within(card).getByLabelText('Performance R | 998')).toHaveAttribute('data-car-performance-class', 'R');
    expect(card).toHaveTextContent('RWD');
    expect(within(card).queryByText('Engine max')).not.toBeInTheDocument();

    await fireEvent.click(within(card).getByRole('button', { name: 'Expand car details' }));

    expect(within(card).getByText('Engine max')).toBeInTheDocument();
    expect(within(card).getByText('10,000 rpm')).toBeInTheDocument();
    expect(within(card).getByText('Car group')).toBeInTheDocument();
    expect(within(card).getByText('Extreme Track Toys')).toBeInTheDocument();
    expect(within(card).getByText('Peak power')).toBeInTheDocument();
    expect(within(card).getByText('331 kW')).toBeInTheDocument();
    expect(within(card).queryByText('Catalog')).not.toBeInTheDocument();
    expect(within(card).queryByText('Fuel')).not.toBeInTheDocument();

    await fireEvent.click(within(card).getByRole('button', { name: 'Collapse car details' }));
    expect(within(card).queryByText('Engine max')).not.toBeInTheDocument();
  });

  it('shows the car card from recovered live telemetry when no lap is selected', async () => {
    const liveCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      laps: [],
      capture: liveCapture,
      status: { ...statusPayload, capture: liveCapture },
      recent: { session_id: 'session-live', samples: recoveredSamples, car: defaultCarInfo }
    });
    renderApp();

    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-sample-count', '2'));
    const card = getCarInfoCard();
    expect(card).toHaveTextContent('Mazda Furai');
    expect(card).toHaveTextContent('R | 998');
    expect(card).toHaveTextContent('RWD');
    expect(within(getVisualisationStage()).getAllByRole('button', { name: 'Hide car info' })[0]).toHaveAttribute('aria-pressed', 'true');
  });

  it('recovers only race samples from the latest live lap trace', async () => {
    const liveCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      laps: [],
      capture: liveCapture,
      status: { ...statusPayload, capture: liveCapture },
      recent: {
        session_id: 'session-live',
        samples: [
          makeLiveSample(1, { lap_id: 'lap-a' }),
          makeLiveSample(2, { lap_id: 'lap-a', is_race_on: false }),
          makeLiveSample(3, { lap_id: 'lap-b' }),
          makeLiveSample(4, { lap_id: 'lap-b' })
        ],
        car: defaultCarInfo
      }
    });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(canvas).toHaveAttribute('data-first-sequence', '3');
    expect(canvas).toHaveAttribute('data-last-sequence', '4');
  });

  it('updates the live car card from live sample car payloads', async () => {
    stubApiFetch({ laps: [] });
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];

    expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Car info/i })).toBeNull();
    expect(within(getVisualisationStage()).getByRole('button', { name: 'Show car info' })).toBeDisabled();

    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });
    source.emit('live_sample', {
      type: 'live_sample',
      sample: recoveredSamples[0],
      car: olderCarInfo
    });

    await waitFor(() => expect(getCarInfoCard()).toHaveTextContent('Acura Integra'));
    expect(getCarInfoCard()).toHaveTextContent('S1 | 800');
    expect(within(getCarInfoCard()).getByLabelText('Performance S1 | 800')).toHaveAttribute('data-car-performance-class', 'S1');
    expect(getCarInfoCard()).toHaveTextContent('FWD');
  });

  it('auto-hides live car info while unavailable and restores the prior popover state', async () => {
    const liveCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      laps: [],
      capture: liveCapture,
      status: { ...statusPayload, capture: liveCapture },
      recent: { session_id: 'session-live', samples: recoveredSamples, car: defaultCarInfo }
    });
    renderApp();

    await waitFor(() => expect(getCarInfoCard()).toHaveTextContent('Mazda Furai'));
    await fireEvent.click(within(getCarInfoCard()).getByRole('button', { name: 'Expand car details' }));
    expect(within(getCarInfoCard()).getByText('Engine max')).toBeInTheDocument();

    const source = FakeEventSource.instances[0];
    source.emit('live_sample', {
      type: 'live_sample',
      sample: makeLiveSample(200, { lap_id: 'lap-live', is_race_on: true }),
      car: null
    });

    await waitFor(() => expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Car info/i })).toBeNull());
    const disabledToggle = within(getVisualisationStage()).getByRole('button', { name: 'Show car info' });
    expect(disabledToggle).toBeDisabled();
    expect(disabledToggle).toHaveAttribute('aria-pressed', 'false');

    source.emit('live_sample', {
      type: 'live_sample',
      sample: makeLiveSample(201, { lap_id: 'lap-live', is_race_on: true }),
      car: olderCarInfo
    });

    await waitFor(() => expect(getCarInfoCard()).toHaveTextContent('Acura Integra'));
    expect(within(getCarInfoCard()).getByText('Engine max')).toBeInTheDocument();

    await fireEvent.click(within(getVisualisationStage()).getAllByRole('button', { name: 'Hide car info' })[0]);
    expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Car info/i })).toBeNull();

    source.emit('live_reset', { type: 'live_reset', session_id: 'session-live-reset' });
    await waitFor(() => expect(within(getVisualisationStage()).getByRole('button', { name: 'Show car info' })).toBeDisabled());

    source.emit('live_sample', {
      type: 'live_sample',
      sample: makeLiveSample(202, { lap_id: 'lap-live-reset', is_race_on: true }),
      car: defaultCarInfo
    });

    await waitFor(() => expect(within(getVisualisationStage()).getByRole('button', { name: 'Show car info' })).toBeEnabled());
    expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Car info/i })).toBeNull();

    await fireEvent.click(within(getVisualisationStage()).getByRole('button', { name: 'Show car info' }));
    expect(getCarInfoCard()).toHaveTextContent('Mazda Furai');
  });

  it('toggles and resets car details to compact when another lap is selected', async () => {
    stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();

    await waitFor(() => expect(getCarInfoCard()).toHaveTextContent('Mazda Furai'));
    await fireEvent.click(within(getCarInfoCard()).getByRole('button', { name: 'Expand car details' }));
    expect(within(getCarInfoCard()).getByText('Engine max')).toBeInTheDocument();

    await fireEvent.click(within(getVisualisationStage()).getAllByRole('button', { name: 'Hide car info' })[0]);
    expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Car info/i })).toBeNull();
    await waitFor(() => expect(within(getVisualisationStage()).getByRole('button', { name: 'Show car info' })).toHaveFocus());

    await fireEvent.click(screen.getByRole('button', { name: /^Lap 1/i }));

    await waitFor(() => expect(getCarInfoCard()).toHaveTextContent('Acura Integra'));
    expect(within(getCarInfoCard()).queryByText('Engine max')).not.toBeInTheDocument();

    await fireEvent.click(within(getVisualisationStage()).getAllByRole('button', { name: 'Hide car info' })[0]);
    expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Car info/i })).toBeNull();

    await fireEvent.click(within(getVisualisationStage()).getByRole('button', { name: 'Show car info' }));
    expect(getCarInfoCard()).toHaveTextContent('Acura Integra');
  });

  it('shows floating canvas zoom controls and toggles auto fit to screen', async () => {
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    const stage = getVisualisationStage();
    const zoomIn = within(stage).getByRole('button', { name: 'Zoom in' });
    const zoomOut = within(stage).getByRole('button', { name: 'Zoom out' });
    const fit = within(stage).getByRole('button', { name: 'Disable fit to screen' });
    const canvas = screen.getByLabelText('Live telemetry path');

    expect(zoomIn).toHaveAttribute('title', 'Zoom in');
    expect(zoomIn.querySelector('svg')).not.toBeNull();
    expect(zoomOut).toHaveAttribute('title', 'Zoom out');
    expect(zoomOut.querySelector('svg')).not.toBeNull();
    expect(fit).toHaveAttribute('title', 'Fit to screen is on');
    expect(fit).toHaveAttribute('aria-pressed', 'true');
    expect(fit.querySelector('svg')).not.toBeNull();
    expect(canvas).toHaveAttribute('data-auto-fit', 'true');
    expect(canvas).toHaveAttribute('data-zoom', '1');
    expect(canvas).toHaveAttribute('data-pan-x', '0');
    expect(canvas).toHaveAttribute('data-pan-y', '0');

    await fireEvent.click(fit);
    expect(fit).toHaveAttribute('aria-label', 'Enable fit to screen');
    expect(fit).toHaveAttribute('aria-pressed', 'false');
    await waitFor(() => expect(canvas).toHaveAttribute('data-auto-fit', 'false'));

    await fireEvent.click(zoomIn);
    expect(canvas).toHaveAttribute('data-zoom', '1');
    await fireEvent.click(zoomOut);
    await waitFor(() => expect(Number(canvas.getAttribute('data-zoom'))).toBeLessThan(1));
    await fireEvent.click(fit);
    expect(fit).toHaveAttribute('aria-label', 'Disable fit to screen');
    expect(fit).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(canvas).toHaveAttribute('data-auto-fit', 'true'));
    await waitFor(() => {
      expect(canvas).toHaveAttribute('data-zoom', '1');
      expect(canvas).toHaveAttribute('data-pan-x', '0');
      expect(canvas).toHaveAttribute('data-pan-y', '0');
    });

    await fireEvent.click(fit);
    expect(fit).toHaveAttribute('aria-label', 'Enable fit to screen');
    expect(fit).toHaveAttribute('aria-pressed', 'false');
    await waitFor(() => expect(canvas).toHaveAttribute('data-auto-fit', 'false'));
  });

  it('temporarily pauses auto fit after viewport zoom activity and resumes after inactivity', async () => {
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    const stage = getVisualisationStage();
    const fit = within(stage).getByRole('button', { name: 'Disable fit to screen' });
    const canvas = screen.getByLabelText('Live telemetry path');

    await waitFor(() => expect(canvas).toHaveAttribute('data-auto-fit', 'true'));
    expect(fit).toHaveAttribute('aria-pressed', 'true');

    vi.useFakeTimers();
    await fireEvent.wheel(canvas, { clientX: 450, clientY: 280, deltaY: 100 });

    await waitFor(() => expect(canvas).toHaveAttribute('data-auto-fit', 'false'));
    expect(fit).toHaveAttribute('aria-pressed', 'true');
    expect(fit).toHaveAttribute('title', 'Fit to screen paused; resumes after 10 seconds of no pan or zoom');
    expect(Number(canvas.getAttribute('data-target-zoom'))).toBeLessThan(1);
    await vi.advanceTimersByTimeAsync(16);
    await waitFor(() => expect(Number(canvas.getAttribute('data-zoom'))).toBeLessThan(1));

    await vi.advanceTimersByTimeAsync(9_983);
    expect(canvas).toHaveAttribute('data-auto-fit', 'false');

    await vi.advanceTimersByTimeAsync(1);
    await waitFor(() => expect(canvas).toHaveAttribute('data-auto-fit', 'true'));
    expect(canvas).toHaveAttribute('data-target-zoom', '1');
    expect(canvas).toHaveAttribute('data-target-pan-x', '0');
    expect(canvas).toHaveAttribute('data-target-pan-y', '0');
  });

  it('starts a new session when New session is selected from the menu', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    const menu = screen.getByRole('navigation', { name: 'Main menu' });
    await fireEvent.click(within(menu).getByRole('button', { name: 'New session' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/sessions/start', { method: 'POST' }));
    expect(await findToast('Session 3 started')).toBeInTheDocument();
  });

  it('opens the stats window from the main menu and requests stats window data', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    const menu = screen.getByRole('navigation', { name: 'Main menu' });

    await fireEvent.click(within(menu).getByRole('button', { name: 'Expand menu' }));
    await fireEvent.click(within(menu).getByRole('button', { name: 'Stats' }));

    expect(await screen.findByRole('heading', { name: 'Stats' })).toBeInTheDocument();
    expect(await screen.findByText('Mazda Furai')).toBeInTheDocument();
    const dialog = screen.getByRole('dialog', { name: 'Stats' });
    expect(within(dialog).getByRole('group', { name: 'Tracks driven' })).toHaveTextContent('3');
    expect(within(dialog).getByRole('group', { name: 'Cars driven' })).toHaveTextContent('2');
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/stats'));
  });

  it('opens the About window from the main menu and requests app metadata', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    const menu = screen.getByRole('navigation', { name: 'Main menu' });

    await fireEvent.click(within(menu).getByRole('button', { name: 'Expand menu' }));
    await fireEvent.click(within(menu).getByRole('button', { name: 'About' }));

    const dialog = await screen.findByRole('dialog', { name: 'About' });
    expect(await within(dialog).findByText('Installed version 1.0.0')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Check for updates' })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/app/about'));
  });

  it('opens the session browser from the main menu and requests the first 100-session page', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    const menu = screen.getByRole('navigation', { name: 'Main menu' });

    await fireEvent.click(within(menu).getByRole('button', { name: 'Session browser' }));

    expect(await screen.findByRole('dialog', { name: 'Sessions' })).toBeInTheDocument();
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
      expect(hasSessionPageCall(calls)).toBe(true);
    });
  });

  it('shows car or lap-count context in the session browser instead of session track fields', async () => {
    stubApiFetch({
      sessions: [
        {
          ...defaultSessions[0],
          car_name: 'Mazda Furai',
          car_class_label: 'S1',
          car_performance_index: 900,
          drivetrain_label: 'RWD'
        },
        { ...defaultSessions[1] }
      ]
    });
    renderApp();

    await fireEvent.click(within(screen.getByRole('navigation', { name: 'Main menu' })).getByRole('button', { name: 'Session browser' }));

    const dialog = await screen.findByRole('dialog', { name: 'Sessions' });
    expect(await within(dialog).findByText('Mazda Furai · S1 900 · RWD')).toBeInTheDocument();
    expect(await within(dialog).findByText('1 lap')).toBeInTheDocument();
    expect(within(dialog).queryByText('Unknown track')).not.toBeInTheDocument();
  });

  it('session browser filters, renames, and confirms before deleting sessions', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await fireEvent.click(within(screen.getByRole('navigation', { name: 'Main menu' })).getByRole('button', { name: 'Session browser' }));
    const dialog = await screen.findByRole('dialog', { name: 'Sessions' });
    expect(within(dialog).getByLabelText('Session Name')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Track')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Car')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Min. Laps')).not.toBeInTheDocument();
    const filtersForm = within(dialog).getByRole('form', { name: 'Session filters' });
    const filterActions = filtersForm.querySelector('.filter-actions');
    const showMoreButton = within(dialog).getByRole('button', { name: 'Show more filters' });
    const applyFiltersButton = within(dialog).getByRole('button', { name: 'Apply session filters' });
    expect(filterActions).toContainElement(showMoreButton);
    expect(filterActions).toContainElement(applyFiltersButton);
    expect(Array.from(filterActions?.querySelectorAll('button') ?? [])).toEqual([showMoreButton, applyFiltersButton]);

    await fireEvent.input(within(dialog).getByLabelText('Session Name'), { target: { value: 'Night' } });
    await fireEvent.input(within(dialog).getByLabelText('Car'), { target: { value: 'Furai' } });
    await fireEvent.click(showMoreButton);
    await waitFor(() => expect(within(dialog).getByLabelText('Min. Laps')).toHaveFocus());
    await fireEvent.input(within(dialog).getByLabelText('Min. Laps'), { target: { value: '1' } });
    await fireEvent.click(applyFiltersButton);
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
      expect(hasSessionPageCall(calls, { page: '1', page_size: '100', name: 'Night', lap_count_min: '1', car: 'Furai' })).toBe(true);
    });

    const openButton = await screen.findByRole('button', { name: 'Open Midnight Club' });
    const renameButton = await screen.findByRole('button', { name: 'Rename Midnight Club' });
    const deleteButton = await screen.findByRole('button', { name: 'Delete Midnight Club' });
    expect(openButton).toHaveAttribute('title', 'Open Midnight Club');
    expect(renameButton).toHaveAttribute('title', 'Rename Midnight Club');
    expect(deleteButton).toHaveAttribute('title', 'Delete Midnight Club');
    expect(openButton.querySelector('svg.app-icon')).toBeInTheDocument();
    expect(renameButton.querySelector('svg.app-icon')).toBeInTheDocument();
    expect(deleteButton.querySelector('svg.app-icon')).toBeInTheDocument();

    await fireEvent.click(renameButton);
    await fireEvent.input(screen.getByLabelText('Session name'), { target: { value: 'Night practice' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Save session name' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-b', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: 'Night practice' })
      })
    );
    await fireEvent.click(await screen.findByRole('button', { name: 'Delete Night practice' }));
    expect(screen.getByRole('dialog', { name: 'Delete session' })).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'Confirm delete session' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-b', { method: 'DELETE' }));
  });

  it('selecting a session in the browser loads only that session laps', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await loadSessionFromBrowser('Sunset Sprint');

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
      expect(calls).toContain('/api/sessions/session-a/laps');
    });
    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(within(drawer).getByText('Sunset Sprint')).toBeInTheDocument();
    expect(within(drawer).queryByText('Midnight Club')).not.toBeInTheDocument();
  });

  it('selecting a session in the browser activates it before loading laps', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await loadSessionFromBrowser('Sunset Sprint');

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-a/activate', { method: 'POST' });
      const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
      expect(calls.indexOf('/api/sessions/session-a/activate')).toBeGreaterThanOrEqual(0);
      expect(calls.indexOf('/api/sessions/session-a/activate')).toBeLessThan(calls.indexOf('/api/sessions/session-a/laps'));
    });
  });

  it('shows route loading progress while loading a new session', async () => {
    const deferredSessionLaps = deferredResponse();
    const defaultHandler = createDefaultFetchHandler();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/sessions/session-a/laps') {
        return deferredSessionLaps.promise;
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-sample-count', '3'));
    await openSessionBrowser();
    await fireEvent.click(await screen.findByRole('button', { name: 'Open Sunset Sprint' }));

    const status = await screen.findByRole('status', { name: 'Route visualiser loading' });
    expect(status).toHaveTextContent(/Activating session|Loading session laps|Preparing session view/);
    const progress = within(status).getByRole('progressbar', { name: 'Route visualiser loading progress' });
    expect(Number(progress.getAttribute('aria-valuenow'))).toBeGreaterThan(0);

    deferredSessionLaps.resolve(jsonResponse({ session_id: 'session-a', laps: [defaultLaps[0]] }));

    await waitFor(() => expect(screen.queryByRole('status', { name: 'Route visualiser loading' })).not.toBeInTheDocument());
    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(within(drawer).getByText('Sunset Sprint')).toBeInTheDocument();
  });

  it('clears route loading progress when loading a new session fails', async () => {
    const defaultHandler = createDefaultFetchHandler();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/sessions/session-a/laps') {
        throw new Error('session laps failed');
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-sample-count', '3'));
    await openSessionBrowser();
    await fireEvent.click(await screen.findByRole('button', { name: 'Open Sunset Sprint' }));

    expect(await screen.findByRole('status', { name: 'Route visualiser loading' })).toHaveTextContent(/Activating session|Loading session laps|Preparing session view/);
    expect(await findToast('Unable to load session laps')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('status', { name: 'Route visualiser loading' })).not.toBeInTheDocument());
  });

  it('does not refresh a loaded historical session when the active session receives a lap event', async () => {
    const fetchMock = stubApiFetch({
      activeSession: { ...defaultSessions[1], id: 'session-b', status: 'active' }
    });
    renderApp();
    await loadSessionFromBrowser('Sunset Sprint');
    fetchMock.mockClear();

    FakeEventSource.instances[0].emit('lap_finalized', {
      type: 'lap_finalized',
      session_id: 'session-b',
      lap_id: 'new-active-lap',
      boundary_confidence: 'game_field'
    });

    await Promise.resolve();
    await Promise.resolve();
    const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
    expect(calls).not.toContain('/api/sessions/session-b/laps');
    expect(calls).not.toContain('/api/sessions/session-a/laps');
    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(within(drawer).getByText('Sunset Sprint')).toBeInTheDocument();
  });

  it('moves the section summary with keyboard and mouse while clamping extreme drag positions', async () => {
    renderApp();

    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('Full lap summary'));
    const summary = getSectionSummaryCard();
    const dragHandle = getSummaryDragHandle();
    expect(summary).toHaveAttribute('data-summary-x', '0');
    expect(summary).toHaveAttribute('data-summary-y', '0');

    await fireEvent.keyDown(dragHandle, { key: 'ArrowRight' });
    await waitFor(() => expect(getSectionSummaryCard()).toHaveAttribute('data-summary-x', '16'));
    expect(getSectionSummaryCard()).toHaveAttribute('data-summary-y', '0');

    await fireEvent.keyDown(dragHandle, { key: 'ArrowDown', shiftKey: true });
    await waitFor(() => expect(getSectionSummaryCard()).toHaveAttribute('data-summary-y', '48'));

    await fireEvent.mouseDown(dragHandle, { button: 0, clientX: 0, clientY: 0 });
    await fireEvent.mouseMove(window, { clientX: 10000, clientY: 10000 });
    await fireEvent.mouseUp(window);
    await waitFor(() => expect(getSectionSummaryCard()).toHaveAttribute('data-summary-x', '600'));
    expect(getSectionSummaryCard()).toHaveAttribute('data-summary-y', '600');

    await fireEvent.keyDown(dragHandle, { key: 'Home' });
    await waitFor(() => expect(getSectionSummaryCard()).toHaveAttribute('data-summary-x', '0'));
    expect(getSectionSummaryCard()).toHaveAttribute('data-summary-y', '0');
  });

  it('opens telemetry tracker settings from the slide-out menu', async () => {
    renderApp();

    const dialog = await openSettingsModal();

    expect(within(dialog).getByLabelText('UDP host')).toHaveValue('127.0.0.1');
    expect(within(dialog).getByLabelText('UDP port')).toHaveValue('5400');
    expect(within(dialog).getByRole('combobox', { name: 'Speed units' })).toHaveValue('imperial');
    const defaultOverlaySelect = within(dialog).getByRole('combobox', { name: 'Default overlay' });
    expect(defaultOverlaySelect).toHaveValue('issues');
    expect(defaultOverlaySelect).toBeEnabled();
    const mapSettings = within(dialog).getByLabelText('FH6 world map settings');
    expect(mapSettings).toBeInTheDocument();
    expect(mapSettings).toHaveClass('settings-section');
    const mapSettingsHelpButton = within(mapSettings).getByRole('button', { name: 'How to find the FH6 install folder' });
    expect(mapSettingsHelpButton).toHaveClass('world-map-install-location-help');
    expect(mapSettingsHelpButton).not.toHaveClass('app-icon-button');
    expect(within(mapSettings).queryByRole('button', { name: 'Browse for FH6 install folder' })).not.toBeInTheDocument();
    expect(within(mapSettings).getAllByRole('button').map((button) => button.textContent?.trim()).filter(Boolean)).toEqual([
      'Build local map cache',
      'Save map settings'
    ]);
    expect(within(dialog).getByText('FH6 install location is not configured.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('FH6 Local Install Location')).toHaveAttribute(
      'placeholder',
      'e.g. C:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6'
    );
    expect(dialog).not.toHaveTextContent('For desktop v1');
    expect(dialog).not.toHaveTextContent('New site loads start with this overlay');
    expect(dialog).not.toHaveTextContent('Status summary');
    expect(within(dialog).getByRole('button', { name: 'Reset floating panels and layout' })).toBeInTheDocument();
  });

  it('uses the desktop folder picker for FH6 world map settings when the bridge is available', async () => {
    const chooseInstallFolder = stubDesktopFolderPicker('D:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6');
    stubApiFetch({ worldMapStatus: readyWorldMapStatus });
    renderApp();

    const dialog = await openSettingsModal();
    const mapSettings = within(dialog).getByLabelText('FH6 world map settings');
    const installLocationInput = within(mapSettings).getByLabelText('FH6 Local Install Location');
    await waitFor(() => expect(installLocationInput).toHaveValue('G:/FH6'));

    await fireEvent.click(within(mapSettings).getByRole('button', { name: 'Browse for FH6 install folder' }));

    await waitFor(() => expect(chooseInstallFolder).toHaveBeenCalledWith('G:/FH6'));
    await waitFor(() => expect(installLocationInput).toHaveValue('D:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6'));
  });

  it('shows the FH6 install folder browse button when the desktop bridge becomes ready after mount', async () => {
    stubApiFetch({ worldMapStatus: readyWorldMapStatus });
    renderApp();

    const dialog = await openSettingsModal();
    const mapSettings = within(dialog).getByLabelText('FH6 world map settings');
    expect(within(mapSettings).queryByRole('button', { name: 'Browse for FH6 install folder' })).not.toBeInTheDocument();

    stubDesktopFolderPicker('D:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6');
    window.dispatchEvent(new Event('pywebviewready'));

    expect(await within(mapSettings).findByRole('button', { name: 'Browse for FH6 install folder' })).toBeInTheDocument();
  });

  it('leaves the current FH6 install location unchanged when the desktop folder picker is cancelled', async () => {
    const chooseInstallFolder = stubDesktopFolderPicker(null);
    stubApiFetch({ worldMapStatus: readyWorldMapStatus });
    renderApp();

    const dialog = await openSettingsModal();
    const mapSettings = within(dialog).getByLabelText('FH6 world map settings');
    const installLocationInput = within(mapSettings).getByLabelText('FH6 Local Install Location');
    await waitFor(() => expect(installLocationInput).toHaveValue('G:/FH6'));

    await fireEvent.click(within(mapSettings).getByRole('button', { name: 'Browse for FH6 install folder' }));

    await waitFor(() => expect(chooseInstallFolder).toHaveBeenCalledWith('G:/FH6'));
    expect(installLocationInput).toHaveValue('G:/FH6');
  });

  it('saves FH6 world map settings and builds the local map cache from settings', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    const dialog = await openSettingsModal();
    expect(within(dialog).getByText(/Link the tracker to your FH6 game install folder/i)).toBeInTheDocument();

    await fireEvent.click(within(dialog).getByRole('button', { name: 'How to find the FH6 install folder' }));
    expect(within(dialog).getByText('Start the game.')).toBeInTheDocument();
    expect(within(dialog).getByText(/The folder that opens is the folder the tracker needs/i)).toBeInTheDocument();
    await fireEvent.pointerDown(within(dialog).getByLabelText('FH6 Local Install Location'));
    expect(within(dialog).queryByText('Start the game.')).toBeNull();

    await fireEvent.input(within(dialog).getByLabelText('FH6 Local Install Location'), {
      target: { value: 'G:/FH6' }
    });
    await fireEvent.click(within(dialog).getByLabelText('Enable world map overlay'));
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Build local map cache' }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/map/settings' &&
            init?.method === 'PATCH' &&
            init.body === JSON.stringify({
              fh6_media_root: 'G:/FH6',
              world_map_enabled: true,
              world_map_season: 'summer'
            })
        )
      ).toBe(true)
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/map/cache/build' &&
            init?.method === 'POST' &&
            init.body === JSON.stringify({ season: 'summer' })
        )
      ).toBe(true)
    );
    await waitFor(() => expect(within(dialog).getByText('Cache ready: fh6-brio-summer.')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-world-map-tile-set-id', 'fh6-brio-summer'));
    expect(await findToast('World map cache ready')).toBeInTheDocument();
  });

  it('toggles a ready world map overlay from the floating map button', async () => {
    const fetchMock = stubApiFetch({ worldMapStatus: readyWorldMapStatus });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-world-map-tile-set-id', 'fh6-brio-summer'));

    const stage = getVisualisationStage();
    const mapToggle = within(stage).getByRole('button', { name: 'Hide map overlay' });
    expect(mapToggle).toHaveAttribute('aria-pressed', 'true');
    expect(mapToggle.querySelector('svg')).not.toBeNull();

    await fireEvent.click(mapToggle);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/map/settings' &&
            init?.method === 'PATCH' &&
            init.body === JSON.stringify({
              fh6_media_root: 'G:/FH6',
              world_map_enabled: false,
              world_map_season: 'summer'
            })
        )
      ).toBe(true)
    );
    await waitFor(() => expect(canvas).toHaveAttribute('data-world-map-tile-set-id', ''));
    expect(within(stage).getByRole('button', { name: 'Show map overlay' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('opens first-run map setup from the floating map button and enables the overlay after building the cache', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    const stage = getVisualisationStage();
    const canvas = screen.getByLabelText('Live telemetry path');
    const setupToggle = within(stage).getByRole('button', { name: 'Set up map overlay' });
    expect(setupToggle).toHaveAttribute('aria-pressed', 'false');
    expect(canvas).toHaveAttribute('data-world-map-tile-set-id', '');

    await fireEvent.click(setupToggle);

    const panel = screen.getByRole('dialog', { name: 'World Map Setup' });
    expect(panel).toHaveTextContent('Link the tracker to your FH6 game install folder.');
    const mediaRootInput = within(panel).getByLabelText('FH6 Local Install Location');
    expect(mediaRootInput).toHaveAttribute('placeholder', 'e.g. C:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6');
    await waitFor(() => expect(mediaRootInput).toHaveFocus());
    const setupHelpButton = within(panel).getByRole('button', { name: 'How to find the FH6 install folder' });
    expect(setupHelpButton).toHaveClass('world-map-install-location-help');
    expect(setupHelpButton).not.toHaveClass('app-icon-button');
    await fireEvent.click(setupHelpButton);
    expect(within(panel).getByText('Open Task Manager.')).toBeInTheDocument();
    expect(within(panel).getByText('Right click the FH6 process.')).toBeInTheDocument();
    await fireEvent.input(mediaRootInput, {
      target: { value: 'G:/FH6' }
    });
    await fireEvent.click(within(panel).getByRole('button', { name: 'Build local map cache' }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/map/settings' &&
            init?.method === 'PATCH' &&
            init.body === JSON.stringify({
              fh6_media_root: 'G:/FH6',
              world_map_enabled: true,
              world_map_season: 'summer'
            })
        )
      ).toBe(true)
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/map/cache/build' &&
            init?.method === 'POST' &&
            init.body === JSON.stringify({ season: 'summer' })
        )
      ).toBe(true)
    );
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'World Map Setup' })).toBeNull());
    await waitFor(() => expect(canvas).toHaveAttribute('data-world-map-tile-set-id', 'fh6-brio-summer'));
    expect(within(stage).getByRole('button', { name: 'Hide map overlay' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps first-run map setup open and shows an error when cache build does not become ready', async () => {
    const failedStatus: WorldMapStatus = {
      ...defaultWorldMapStatus,
      status: 'source_missing',
      settings: {
        fh6_media_root: 'G:/Wrong',
        world_map_enabled: true,
        world_map_season: 'summer'
      },
      source: {
        available: false,
        path: 'G:/Wrong/media/UI/Textures/Data_Bound/Map_Brio_Summer.zip',
        season: 'summer'
      },
      converter: {
        available: true,
        path: 'F:/code/git/forza-telemetry-tracker/bin/map-converter/forza-map-tile-converter.exe'
      },
      tile_set: null,
      error_message: 'Seasonal map archive was not found.'
    };
    stubApiFetch({ mapBuildStatus: failedStatus });
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    const stage = getVisualisationStage();
    await fireEvent.click(within(stage).getByRole('button', { name: 'Set up map overlay' }));

    const panel = screen.getByRole('dialog', { name: 'World Map Setup' });
    await fireEvent.input(within(panel).getByLabelText('FH6 Local Install Location'), {
      target: { value: 'G:/Wrong' }
    });
    await fireEvent.click(within(panel).getByRole('button', { name: 'Build local map cache' }));

    await waitFor(() => expect(screen.getByRole('dialog', { name: 'World Map Setup' })).toBeInTheDocument());
    await waitFor(() => expect(within(panel).getByText('Seasonal map archive was not found.')).toBeInTheDocument());
    expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-world-map-tile-set-id', '');
  });

  it('persists metric speed units from settings and updates the lap summary', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await waitFor(() => expect(within(getSectionSummaryCard()).getByText('Top speed (MPH)')).toBeInTheDocument());
    expect(within(getSectionSummaryCard()).getByText('102.2')).toBeInTheDocument();

    const dialog = await openSettingsModal();
    await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Speed units' }), { target: { value: 'metric' } });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/settings' &&
            init?.method === 'PATCH' &&
            init.body === JSON.stringify({ unit_system: 'metric' })
        )
      ).toBe(true)
    );
    await waitFor(() => expect(within(getSectionSummaryCard()).getByText('Top speed (KPH)')).toBeInTheDocument());
    expect(within(getSectionSummaryCard()).getByText('164.4')).toBeInTheDocument();
    expect(await findToast('Settings saved')).toBeInTheDocument();
  });

  it('persists the default overlay from settings and switches the active overlay immediately', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    const dialog = await openSettingsModal();
    await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Default overlay' }), { target: { value: 'grip' } });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/settings' &&
            init?.method === 'PATCH' &&
            init.body === JSON.stringify({ preferred_overlay: 'grip' })
        )
      ).toBe(true)
    );
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'grip'));
    expect(screen.getByRole('button', { name: 'Grip' })).toHaveAttribute('aria-pressed', 'true');
    expect(await findToast('Settings saved')).toBeInTheDocument();
  });

  it('keeps Issues unavailable when settings change the live default to Issues during recording', async () => {
    const capture = captureWithPreferredOverlay('grip');
    const fetchMock = stubApiFetch({
      status: statusWithPreferredOverlay('grip'),
      capture
    });
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'grip'));

    FakeEventSource.instances[0].emit('capture', {
      ...capture,
      phase: 'recording',
      recording: { ...capture.recording, active: true, phase: 'recording', mode: 'auto' }
    });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled());

    const dialog = await openSettingsModal();
    await fireEvent.change(within(dialog).getByRole('combobox', { name: 'Default overlay' }), { target: { value: 'issues' } });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            requestUrl(input as RequestInfo | URL) === '/api/settings' &&
            init?.method === 'PATCH' &&
            init.body === JSON.stringify({ preferred_overlay: 'issues' })
        )
      ).toBe(true)
    );
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'speed'));
    expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Issues' })).toHaveAttribute('title', 'Issues overlay is only available for completed laps.');
  });

  it('restores the default overlay dropdown when saving the overlay preference fails', async () => {
    const defaultHandler = createDefaultFetchHandler();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (requestUrl(input) === '/api/settings' && init?.method === 'PATCH') {
          return new Response(JSON.stringify({ detail: 'settings unavailable' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return defaultHandler(requestUrl(input), init);
      })
    );
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    const dialog = await openSettingsModal();
    const defaultOverlaySelect = within(dialog).getByRole('combobox', { name: 'Default overlay' });

    await fireEvent.change(defaultOverlaySelect, { target: { value: 'rpm' } });

    await waitFor(() =>
      expect(within(dialog).getByRole('alert')).toHaveTextContent('Unable to save default overlay preference.')
    );
    expect(defaultOverlaySelect).toHaveValue('issues');
    expect(canvas).toHaveAttribute('data-overlay', 'issues');
  });

  it('opens telemetry tracker settings when live listener status omits recorded packet count', async () => {
    const captureAtLivePort = {
      ...capturePayload,
      settings: { ...capturePayload.settings, udp_port: 5401 }
    };
    const statusWithoutRecordedPacketCount = {
      ...statusPayload,
      settings: { ...statusPayload.settings, udp_port: 5401 },
      listener: {
        state: 'receiving',
        udp_host: '127.0.0.1',
        udp_port: 5401,
        packets_received: 1_234,
        message: 'receiving UDP telemetry on 127.0.0.1:5401'
      }
    } as unknown as typeof statusPayload;
    stubApiFetch({ status: statusWithoutRecordedPacketCount, capture: captureAtLivePort });
    renderApp();
    await findListenerStatus(/Listener receiving: receiving UDP telemetry on 127\.0\.0\.1:5401/i);

    const dialog = await openSettingsModal();

    expect(within(dialog).getByLabelText('UDP port')).toHaveValue('5401');
    expect(dialog).not.toHaveTextContent('1,234 received / 0 recorded');
    expect(dialog).not.toHaveTextContent('Listener packets');
  });

  it('resets history drawer layout from telemetry tracker settings', async () => {
    renderApp();

    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(drawer).toHaveAttribute('data-width', '400');
    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('Full lap summary'));
    await fireEvent.click(screen.getByRole('button', { name: 'Hide history drawer' }));
    await waitFor(() => expect(screen.queryByRole('complementary', { name: /Loaded session laps/i })).not.toBeInTheDocument());
    await fireEvent.click(within(getSectionSummaryCard()).getByRole('button', { name: 'Hide section summary' }));
    expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Section summary/i })).toBeNull();

    const dialog = await openSettingsModal();
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Reset floating panels and layout' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Forza Telemetry Tracker settings' })).not.toBeInTheDocument());
    const resetDrawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(resetDrawer).toHaveAttribute('data-width', '400');
    expect(getSectionSummaryCard()).toHaveTextContent(/Full lap summary/i);
    expect(await findToast('Layout reset')).toBeInTheDocument();
  });

  it('shows concise Data Out setup in settings', async () => {
    renderApp();
    const dialog = await openSettingsModal();
    expect(dialog).not.toHaveTextContent('For desktop v1');
    expect(within(dialog).getByText('Set Forza Data Out to IP 127.0.0.1 and port 5400.')).toBeInTheDocument();
  });

  it('uses desktop-safe converter wording for missing world-map converter', async () => {
    const worldMapStatus: WorldMapStatus = {
      ...defaultWorldMapStatus,
      status: 'converter_missing',
      converter: { available: false, path: null },
      settings: { ...defaultWorldMapStatus.settings, fh6_media_root: 'G:\\SteamLibrary\\steamapps\\common\\ForzaHorizon6', world_map_enabled: true },
      source: { ...defaultWorldMapStatus.source, available: true }
    };
    stubApiFetch({ worldMapStatus });
    renderApp();
    const dialog = await openSettingsModal();
    await waitFor(() => {
      expect(within(dialog).getByText('Map converter is missing from this installation. Reinstall the tracker or install a repaired build.')).toBeInTheDocument();
      expect(within(dialog).getByText('Map converter unavailable in this installation.')).toBeInTheDocument();
      expect(dialog).not.toHaveTextContent('run the .NET converter build first');
      expect(dialog).not.toHaveTextContent('build the converter before generating tiles');
    });
  });

  it('opens raw telemetry import from the slide-out menu with a browser file picker', async () => {
    renderApp();

    const dialog = await openImportTelemetryModal();

    expect(within(dialog).getByText(/file, several files, or a whole folder/i)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Raw telemetry file or files')).toHaveAttribute('type', 'file');
    expect(within(dialog).getByLabelText('Raw telemetry folder')).toHaveAttribute('webkitdirectory');
    expect(within(dialog).getByRole('button', { name: 'Start background import' })).toBeDisabled();
    expect(within(dialog).getByRole('region', { name: 'Raw telemetry import jobs' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Replay raw telemetry' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Replay raw telemetry' })).not.toBeInTheDocument();
  });

  it('opens telemetry export from the slide-out menu and loads defaults plus existing jobs', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    const dialog = await openExportTelemetryModal();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/telemetry/export-defaults'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/telemetry/export-jobs'));
    expect(within(dialog).getByLabelText('Output folder')).toHaveValue('D:/Telemetry Exports');
    expect(within(dialog).getByLabelText('File name prefix')).toHaveValue('telemetry-export');
    expect(within(dialog).getByText('night-run_curated.csv')).toBeInTheDocument();
  });

  it('starts a curated telemetry export job with export headers and reports the started job', async () => {
    const fetchMock = stubApiFetch({ telemetryExportJobs: [] });
    renderApp();

    const dialog = await openExportTelemetryModal();
    await waitFor(() => expect(within(dialog).getByLabelText('Output folder')).toHaveValue('D:/Telemetry Exports'));
    await fireEvent.input(within(dialog).getByLabelText('File name prefix'), { target: { value: 'my-export' } });
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Export curated CSV' }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(([input, init]) => (
        requestUrl(input as RequestInfo | URL) === '/api/telemetry/export-jobs' && (init as RequestInit | undefined)?.method === 'POST'
      ));
      expect(createCall).toBeDefined();
      const init = createCall?.[1] as RequestInit;
      expect(JSON.parse(String(init.body))).toEqual({
        kind: 'curated_csv',
        output_dir: 'D:/Telemetry Exports',
        filename_prefix: 'my-export'
      });
      expect(init.headers).toMatchObject({
        'Content-Type': 'application/json',
        'X-Forza-Telemetry-Export': '1'
      });
    });
    expect(await findToast('Started Curated CSV export job.')).toBeInTheDocument();
  });

  it('continues telemetry export polling after close without duplicate poll timers', async () => {
    const runningJob: TelemetryExportJob = {
      ...defaultTelemetryExportJobs[0],
      id: 'export-job-running',
      status: 'running',
      status_text: 'Running',
      progress: 0.5,
      output_files: [],
      total_size_bytes: 0,
      completed_at_ms: null,
      duration_ms: null,
      can_cancel: true
    };
    const fetchMock = stubApiFetch({ telemetryExportJobs: [runningJob] });
    vi.useFakeTimers();
    renderApp();

    const menu = screen.getByRole('navigation', { name: 'Main menu' });
    await fireEvent.click(within(menu).getByRole('button', { name: 'Export telemetry' }));
    await vi.advanceTimersByTimeAsync(0);
    const firstDialog = screen.getByRole('dialog', { name: 'Export telemetry' });
    expect(within(firstDialog).getAllByText('Running').length).toBeGreaterThan(0);
    await fireEvent.click(within(firstDialog).getByRole('button', { name: 'Close Export telemetry' }));
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.queryByRole('dialog', { name: 'Export telemetry' })).not.toBeInTheDocument();

    await fireEvent.click(within(menu).getByRole('button', { name: 'Export telemetry' }));
    await vi.advanceTimersByTimeAsync(0);
    const secondDialog = screen.getByRole('dialog', { name: 'Export telemetry' });
    expect(within(secondDialog).getAllByText('Running').length).toBeGreaterThan(0);
    await fireEvent.click(within(secondDialog).getByRole('button', { name: 'Close Export telemetry' }));
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.queryByRole('dialog', { name: 'Export telemetry' })).not.toBeInTheDocument();

    fetchMock.mockClear();
    await vi.advanceTimersByTimeAsync(1000);
    const exportJobPolls = fetchMock.mock.calls.filter(
      ([input]) => requestUrl(input as RequestInfo | URL) === '/api/telemetry/export-jobs'
    );
    expect(exportJobPolls).toHaveLength(1);
  });

  it('ignores stale telemetry export job refreshes after starting a job so completion toasts still appear', async () => {
    const defaultHandler = createDefaultFetchHandler({ telemetryExportJobs: [] });
    const staleJobsResponse = deferredResponse();
    let exportJobsGetCount = 0;
    const queuedJob: TelemetryExportJob = {
      ...defaultTelemetryExportJobs[0],
      id: 'export-job-stale-race',
      label: 'Curated CSV',
      status: 'queued',
      status_text: 'Queued',
      progress: 0,
      output_files: [],
      total_size_bytes: 0,
      row_count: 0,
      created_at_ms: 10_000,
      started_at_ms: null,
      completed_at_ms: null,
      duration_ms: null,
      can_cancel: true
    };
    const completedJob: TelemetryExportJob = {
      ...queuedJob,
      status: 'completed',
      status_text: 'Export completed.',
      progress: 1,
      output_files: [
        {
          filename: 'my-export_curated.csv',
          path: 'D:/Telemetry Exports/my-export_curated.csv',
          size_bytes: 12_345
        }
      ],
      total_size_bytes: 12_345,
      row_count: 64,
      started_at_ms: 10_001,
      completed_at_ms: 10_500,
      duration_ms: 499,
      can_cancel: false
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const parsed = new URL(url, 'http://localhost');
      if (parsed.pathname === '/api/telemetry/export-jobs' && init?.method === 'POST') {
        return jsonResponse({ job: queuedJob });
      }
      if (parsed.pathname === '/api/telemetry/export-jobs') {
        exportJobsGetCount += 1;
        return exportJobsGetCount === 1 ? staleJobsResponse.promise : jsonResponse({ jobs: [completedJob] });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.useFakeTimers();
    renderApp();

    const menu = screen.getByRole('navigation', { name: 'Main menu' });
    await fireEvent.click(within(menu).getByRole('button', { name: 'Export telemetry' }));
    await vi.advanceTimersByTimeAsync(0);
    const dialog = screen.getByRole('dialog', { name: 'Export telemetry' });
    await fireEvent.input(within(dialog).getByLabelText('File name prefix'), { target: { value: 'my-export' } });
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Export curated CSV' }));
    await vi.advanceTimersByTimeAsync(0);

    staleJobsResponse.resolve(jsonResponse({ jobs: [] }));
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(250);

    expect(await findToast('Curated CSV export completed: 12,345 bytes.')).toBeInTheDocument();
  });

  it('starts a raw telemetry background import job and reports completion', async () => {
    const defaultHandler = createDefaultFetchHandler();
    const uploadedSession: SessionSummary = {
      id: 'uploaded-session',
      user_id: 'local-user',
      label: 'Uploaded sprint',
      status: 'replay_complete',
      started_at_ms: 9_000,
      ended_at_ms: 10_000,
      ended_reason: 'replay_complete',
      last_active_at_ms: 10_000,
      lap_count: 1,
      completed_lap_count: 1,
      best_lap_time_ms: 1_000,
      average_lap_time_ms: 1_000,
      total_lap_time_ms: 1_000
    };
    let jobStarted = false;
    let sessionsRefreshed = false;
    const queuedJob = {
      id: 'import-job-1',
      label: 'Uploaded sprint',
      source_type: 'file',
      status: 'queued',
      status_text: 'Queued',
      progress: 0,
      created_at_ms: 9_000,
      started_at_ms: null,
      completed_at_ms: null,
      total_files: 1,
      processed_files: 0,
      failed_files: 0,
      total_bytes: 4,
      packet_count: 0,
      session_ids: [] as string[],
      lap_ids: [] as string[],
      current_file: null,
      current_file_index: null,
      current_file_packets: 0,
      current_file_packets_processed: 0,
      errors: [],
      error_count: 0,
      can_cancel: true
    };
    const completedJob = {
      ...queuedJob,
      status: 'completed',
      status_text: 'Imported 2 packets from 1 of 1 files.',
      progress: 1,
      started_at_ms: 9_001,
      completed_at_ms: 9_500,
      processed_files: 1,
      packet_count: 2,
      session_ids: ['uploaded-session'],
      lap_ids: ['uploaded-lap'],
      can_cancel: false
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const parsed = new URL(url, 'http://localhost');
      if (parsed.pathname === '/api/replay/import-jobs/upload' && init?.method === 'POST') {
        expect(init.body).toBeInstanceOf(FormData);
        const body = init.body as FormData;
        expect(body.get('label')).toBe('Uploaded sprint');
        expect(body.get('source_type')).toBe('file');
        expect(body.get('files')).toBeInstanceOf(File);
        jobStarted = true;
        return jsonResponse({ job: queuedJob });
      }
      if (parsed.pathname === '/api/replay/import-jobs') {
        return jsonResponse({ jobs: jobStarted ? [completedJob] : [] });
      }
      if (parsed.pathname === '/api/sessions' && jobStarted) {
        const sessions = [uploadedSession, ...defaultSessions];
        sessionsRefreshed = true;
        return jsonResponse({ sessions, page: 1, page_size: 100, total: sessions.length, total_pages: 1 });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();
    await findToast('Tracker ready');

    const dialog = await openImportTelemetryModal();
    await fireEvent.change(within(dialog).getByLabelText('Raw telemetry file or files'), {
      target: {
        files: [new File([new Uint8Array([1, 2, 3, 4])], 'uploaded.bin', { type: 'application/octet-stream' })]
      }
    });
    await fireEvent.input(within(dialog).getByLabelText('Import label'), { target: { value: 'Uploaded sprint' } });
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Start background import' }));

    expect(await findToast(/Started raw telemetry import job for 1 file/i)).toBeInTheDocument();
    expect(await within(dialog).findByText('Uploaded sprint')).toBeInTheDocument();
    await waitFor(() => expect(sessionsRefreshed).toBe(true));
    expect(await findToast(/Import job finished: 2 packets/i)).toBeInTheDocument();
  });

  it('starts a raw telemetry import job from native file paths', async () => {
    const choose_raw_telemetry_files = vi.fn(async () => ['D:\\captures\\native-a.bin', 'D:\\captures\\native-b.bin']);
    const choose_raw_telemetry_folder = vi.fn(async () => 'D:\\captures');
    vi.stubGlobal('pywebview', {
      api: {
        choose_raw_telemetry_files,
        choose_raw_telemetry_folder
      }
    });
    const defaultHandler = createDefaultFetchHandler();
    let jobStarted = false;
    const queuedJob = {
      id: 'native-import-job',
      label: 'Native sprint',
      source_type: 'files',
      status: 'queued',
      status_text: 'Queued',
      progress: 0,
      created_at_ms: 9_000,
      started_at_ms: null,
      completed_at_ms: null,
      total_files: 2,
      processed_files: 0,
      failed_files: 0,
      total_bytes: 2_000,
      packet_count: 0,
      session_ids: [] as string[],
      lap_ids: [] as string[],
      current_file: null,
      current_file_index: null,
      current_file_packets: 0,
      current_file_packets_processed: 0,
      errors: [],
      error_count: 0,
      can_cancel: true
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const parsed = new URL(url, 'http://localhost');
      if (parsed.pathname === '/api/replay/import-jobs/paths' && init?.method === 'POST') {
        expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
        expect(init.body).toBe(JSON.stringify({
          file_paths: ['D:\\captures\\native-a.bin', 'D:\\captures\\native-b.bin'],
          label: 'Native sprint',
          source_type: 'files'
        }));
        jobStarted = true;
        return jsonResponse({ job: queuedJob });
      }
      if (parsed.pathname === '/api/replay/import-jobs') {
        return jsonResponse({ jobs: jobStarted ? [queuedJob] : [] });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();
    await findToast('Tracker ready');

    const dialog = await openImportTelemetryModal();
    const fileInput = within(dialog).getByLabelText('Raw telemetry file or files');
    const browseFilesButton = within(dialog).getByRole('button', { name: 'Browse files' });
    const folderInput = within(dialog).getByLabelText('Raw telemetry folder');
    const browseFolderButton = within(dialog).getByRole('button', { name: 'Browse folder' });
    expect(fileInput.closest('.file-picker-row')).toContainElement(browseFilesButton);
    expect(folderInput.closest('.file-picker-row')).toContainElement(browseFolderButton);

    await fireEvent.click(browseFilesButton);
    await waitFor(() => expect(choose_raw_telemetry_files).toHaveBeenCalled());
    expect(within(dialog).getByText(/Selected 2 native files/i)).toBeInTheDocument();
    await fireEvent.input(within(dialog).getByLabelText('Import label'), { target: { value: 'Native sprint' } });
    await fireEvent.click(within(dialog).getByRole('button', { name: 'Start background import' }));

    expect(await findToast(/Started raw telemetry import job for 2 files/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL) === '/api/replay/import-jobs/upload')).toBe(false);
  });

  it('renders lap history in a toggleable fixed-width right drawer without capture controls', async () => {
    stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();

    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(within(drawer).queryByRole('heading', { name: /Loaded session laps/i })).not.toBeInTheDocument();
    expect(within(drawer).queryByText('Laps saved in the loaded session')).not.toBeInTheDocument();
    expect(await within(drawer).findByRole('heading', { name: /^Midnight Club$/i })).toBeInTheDocument();
    expect(within(drawer).getByRole('button', { name: 'Laps' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(drawer).getByRole('button', { name: 'Session' })).toHaveAttribute('aria-pressed', 'false');
    expect(within(drawer).queryByRole('button', { name: /Pin history drawer/i })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole('button', { name: 'Close history drawer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resize history drawer' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide history drawer' })).toHaveAttribute('aria-expanded', 'true');
    expect(drawer).toHaveAttribute('data-width', '400');
    expect(within(drawer).queryByRole('region', { name: 'Capture controls' })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole('slider', { name: 'History drawer width' })).toBeNull();

    await fireEvent.click(screen.getByRole('button', { name: 'Hide history drawer' }));
    await waitFor(() => expect(screen.queryByRole('complementary', { name: /Loaded session laps/i })).not.toBeInTheDocument());
    const openHandle = screen.getByRole('button', { name: 'Show history drawer' });
    expect(openHandle).toHaveAttribute('aria-expanded', 'false');

    await fireEvent.click(openHandle);
    expect(await screen.findByRole('complementary', { name: /Loaded session laps/i })).toBeInTheDocument();
  });

  it('opens diagnostics from the main menu and renders database, status, count, and version details', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    const diagnosticsButton = await screen.findByRole('button', { name: 'Open diagnostics' });
    expect(diagnosticsButton).toHaveAttribute('title', 'Open diagnostics');
    fetchMock.mockClear();
    await fireEvent.click(diagnosticsButton);

    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/diagnostics'));
    expect(await within(dialog).findByText('0.1.0')).toBeInTheDocument();
    expect(within(dialog).getByText('telemetry.sqlite3')).toBeInTheDocument();
    expect(within(dialog).getByText(/262,144 bytes/)).toBeInTheDocument();
    expect(within(dialog).getByText(/32,768 bytes/)).toBeInTheDocument();

    const rowCounts = within(dialog).getByRole('region', { name: 'Diagnostics row counts' });
    expect(within(rowCounts).getByText('Sessions')).toBeInTheDocument();
    expect(within(rowCounts).getByText('Laps')).toBeInTheDocument();
    expect(within(rowCounts).getByText('4')).toBeInTheDocument();
    expect(within(rowCounts).getByText('Packets')).toBeInTheDocument();
    expect(within(rowCounts).getByText('128')).toBeInTheDocument();
    expect(within(rowCounts).getByText('Issue markers')).toBeInTheDocument();
    expect(within(rowCounts).getByText('3')).toBeInTheDocument();
    expect(within(rowCounts).getByText('Track profiles')).toBeInTheDocument();
    expect(within(rowCounts).getAllByText('2')).toHaveLength(2);

    const listenerDiagnostics = within(dialog).getByRole('region', { name: 'Listener diagnostics' });
    expect(within(listenerDiagnostics).getByRole('button', { name: 'Restart Listener' })).toBeEnabled();
    expect(within(listenerDiagnostics).getByText('waiting')).toBeInTheDocument();
    expect(within(listenerDiagnostics).getByText('8')).toBeInTheDocument();

    const captureDiagnostics = within(dialog).getByRole('region', { name: 'Capture diagnostics' });
    expect(within(captureDiagnostics).getByText('auto')).toBeInTheDocument();
    expect(within(captureDiagnostics).getByText('idle')).toBeInTheDocument();
    expect(within(dialog).getByText('No recent errors.')).toBeInTheDocument();
  });

  it('restarts the listener from diagnostics and refreshes diagnostics', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Restart Listener' })).toBeEnabled());

    await fireEvent.click(within(dialog).getByRole('button', { name: 'Restart Listener' }));

    await waitFor(() => expect(screen.getByText('Listener restarted')).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith('/api/listener/restart', { method: 'POST' });
    const diagnosticsCalls = fetchMock.mock.calls.filter(([input]) => requestUrl(input as RequestInfo | URL) === '/api/diagnostics');
    expect(diagnosticsCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('dismisses diagnostics on backdrop click without activating underlying controls', async () => {
    const { container } = renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));
    expect(await screen.findByRole('dialog', { name: 'Telemetry diagnostics' })).toBeInTheDocument();

    const backdrop = container.querySelector('.modal-backdrop');
    expect(backdrop).not.toBeNull();
    await fireEvent.click(backdrop as HTMLElement);

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Telemetry diagnostics' })).not.toBeInTheDocument());
    expect(screen.queryByRole('dialog', { name: 'Forza Telemetry Tracker settings' })).not.toBeInTheDocument();
  });

  it('asks for confirmation before deleting all telemetry from diagnostics', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    const rowCounts = await within(dialog).findByRole('region', { name: 'Diagnostics row counts' });
    fetchMock.mockClear();

    await fireEvent.click(within(rowCounts).getByRole('button', { name: 'Delete All Telemetry' }));

    const confirmDialog = await screen.findByRole('dialog', { name: 'Delete all telemetry?' });
    expect(within(confirmDialog).getByText(/permanently erase all recorded telemetry captured by this system/i)).toBeInTheDocument();
    expect(within(confirmDialog).getByText('This cannot be undone.')).toBeInTheDocument();

    await fireEvent.click(within(confirmDialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Delete all telemetry?' })).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL) === '/api/telemetry/delete-all')).toBe(false);
  });

  it('deletes all telemetry after confirmation and refreshes diagnostics', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    const rowCounts = await within(dialog).findByRole('region', { name: 'Diagnostics row counts' });
    await waitFor(() => expect(within(rowCounts).getByRole('button', { name: 'Delete All Telemetry' })).toBeEnabled());
    fetchMock.mockClear();

    await fireEvent.click(within(rowCounts).getByRole('button', { name: 'Delete All Telemetry' }));
    const confirmDialog = await screen.findByRole('dialog', { name: 'Delete all telemetry?' });
    await fireEvent.click(within(confirmDialog).getByRole('button', { name: 'Delete All Telemetry' }));

    await waitFor(() => {
      expect(within(screen.getByLabelText('Status notifications')).getByText('Deleted all recorded telemetry')).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/telemetry/delete-all', { method: 'DELETE' });
    const diagnosticsCalls = fetchMock.mock.calls.filter(([input]) => requestUrl(input as RequestInfo | URL) === '/api/diagnostics');
    expect(diagnosticsCalls.length).toBeGreaterThanOrEqual(1);
    await waitFor(() => {
      expect(within(rowCounts).getByText('Sessions').parentElement!.querySelector('strong')).toHaveTextContent('0');
      expect(within(rowCounts).getByText('Laps').parentElement!.querySelector('strong')).toHaveTextContent('0');
      expect(within(rowCounts).getByText('Packets').parentElement!.querySelector('strong')).toHaveTextContent('0');
      expect(within(rowCounts).getByText('Issue markers').parentElement!.querySelector('strong')).toHaveTextContent('0');
    });
    expect(within(rowCounts).getByText('Track profiles').parentElement!.querySelector('strong')).toHaveTextContent('2');
  });

  it('disables the restart listener button while the request is pending', async () => {
    const defaultHandler = createDefaultFetchHandler();
    const restartResponse = deferredResponse();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/listener/restart') {
        return restartResponse.promise;
      }
      return defaultHandler(url, init);
    }));
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    await fireEvent.click(await within(dialog).findByRole('button', { name: 'Restart Listener' }));

    expect(within(dialog).getByRole('button', { name: 'Restarting…' })).toBeDisabled();
    restartResponse.resolve(jsonResponse(statusPayload.listener));
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Restart Listener' })).toBeEnabled());
  });

  it('surfaces listener restart failures through the shared toast system', async () => {
    const defaultHandler = createDefaultFetchHandler();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/listener/restart') {
        return jsonResponse({ detail: 'address already in use' }, 500);
      }
      return defaultHandler(url, init);
    }));
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    await fireEvent.click(await within(dialog).findByRole('button', { name: 'Restart Listener' }));

    expect(await screen.findByText('Unable to restart listener')).toBeInTheDocument();
    expect(screen.getByLabelText('Status notifications')).toHaveAttribute('aria-live', 'polite');
  });

  it('surfaces diagnostics load failures through the shared toast system', async () => {
    const defaultHandler = createDefaultFetchHandler();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/diagnostics') {
        throw new Error('offline');
      }
      return defaultHandler(url, init);
    }));
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: 'Open diagnostics' }));

    expect(await screen.findByText('Unable to load diagnostics')).toBeInTheDocument();
    expect(screen.getByLabelText('Status notifications')).toHaveAttribute('aria-live', 'polite');
  });

  it('moves focus into diagnostics and contains keyboard focus while open', async () => {
    renderApp();

    const diagnosticsButton = await screen.findByRole('button', { name: 'Open diagnostics' });
    await fireEvent.click(diagnosticsButton);

    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    const closeButton = within(dialog).getByRole('button', { name: 'Close diagnostics' });
    await waitFor(() => expect(dialog).toHaveFocus());

    const refreshButton = within(dialog).getByRole('button', { name: 'Refresh diagnostics' });
    const restartButton = await within(dialog).findByRole('button', { name: 'Restart Listener' });
    await waitFor(() => expect(refreshButton).toBeEnabled());
    restartButton.focus();

    await fireEvent.keyDown(window, { key: 'Tab' });
    expect(closeButton).toHaveFocus();

    await fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(restartButton).toHaveFocus();
  });

  it('closes diagnostics on Escape and restores focus to the opener', async () => {
    renderApp();

    const diagnosticsButton = await screen.findByRole('button', { name: 'Open diagnostics' });
    await fireEvent.click(diagnosticsButton);
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    await waitFor(() => expect(dialog).toHaveFocus());

    await fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Telemetry diagnostics' })).not.toBeInTheDocument());
    await waitFor(() => expect(diagnosticsButton).toHaveFocus());
  });

  it('does not run dashboard shortcuts while diagnostics is open', async () => {
    renderApp();

    const liveFollowButton = await screen.findByRole('button', { name: 'Live follow' });
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '1'));
    expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false');
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    await fireEvent.click(screen.getByRole('button', { name: 'Open diagnostics' }));
    const dialog = await screen.findByRole('dialog', { name: 'Telemetry diagnostics' });
    await waitFor(() => expect(dialog).toHaveFocus());

    const spaceEvent = new KeyboardEvent('keydown', { key: ' ', code: 'Space', bubbles: true, cancelable: true });
    window.dispatchEvent(spaceEvent);

    expect(spaceEvent.defaultPrevented).toBe(false);
    expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false');

    const overlayEvent = new KeyboardEvent('keydown', { key: 'O', bubbles: true, cancelable: true });
    window.dispatchEvent(overlayEvent);

    expect(overlayEvent.defaultPrevented).toBe(false);
    expect(canvas).toHaveAttribute('data-overlay', 'issues');
    expect(screen.getByRole('dialog', { name: 'Telemetry diagnostics' })).toBeInTheDocument();
  });

  it('defaults to the Issues overlay and renders overlay icon buttons with labels and tooltips', async () => {
    renderApp();

    const issuesButton = await screen.findByRole('button', { name: 'Issues' });
    const issuesIcon = issuesButton.querySelector('svg');
    const inputsIcon = screen.getByRole('button', { name: 'Inputs' }).querySelector('svg');
    expect(issuesIcon).not.toBeNull();
    expect(inputsIcon).not.toBeNull();
    expect(issuesButton).toHaveAttribute('aria-pressed', 'true');
    expect(issuesButton).toHaveAttribute('title', 'Show issue markers overlay');
    expect(screen.getByRole('button', { name: 'Speed' })).toHaveAttribute('title', 'Show speed overlay');
    expect(screen.getByRole('button', { name: 'Inputs' })).toHaveAttribute('title', 'Show throttle and brake overlay');
    expect(screen.getByRole('button', { name: 'Grip' })).toHaveAttribute('title', 'Show grip overlay');
    expect(screen.getByRole('button', { name: 'Temperature' })).toHaveAttribute('title', 'Show tyre temperature overlay');
    expect(screen.getByRole('button', { name: 'Suspension' })).toHaveAttribute('title', 'Show suspension travel overlay');
    expect(screen.getByRole('button', { name: 'RPM' })).toHaveAttribute('title', 'Show engine RPM overlay');
  });

  it('cycles overlay mode with the O shortcut', async () => {
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    await fireEvent.keyDown(window, { key: 'O' });
    expect(canvas).toHaveAttribute('data-overlay', 'speed');
    expect(screen.getByRole('button', { name: 'Speed' })).toHaveAttribute('aria-pressed', 'true');

    await fireEvent.keyDown(window, { key: 'o' });
    expect(canvas).toHaveAttribute('data-overlay', 'inputs');
    expect(screen.getByRole('button', { name: 'Inputs' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('switches from Issues to the preferred non-issues overlay when recording starts', async () => {
    const capture = captureWithPreferredOverlay('grip');
    stubApiFetch({
      status: statusWithPreferredOverlay('grip'),
      capture
    });
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'grip'));
    await fireEvent.click(screen.getByRole('button', { name: 'Issues' }));
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    FakeEventSource.instances[0].emit('capture', {
      ...capture,
      phase: 'recording',
      recording: { ...capture.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'grip'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Issues' })).toHaveAttribute('title', 'Issues overlay is only available for completed laps.');
  });

  it('switches from Issues to Speed when recording starts and Issues is the preferred default', async () => {
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const canvas = await screen.findByLabelText('Live telemetry path');
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    FakeEventSource.instances[0].emit('capture', {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'speed'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled());
  });

  it('enables Issues when a completed lap is selected during active recording', async () => {
    const activeCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      capture: activeCapture,
      status: { ...statusPayload, capture: activeCapture },
      laps: defaultLoadedSessionLaps,
      recent: { session_id: 'session-live', samples: [makeLiveSample(1), makeLiveSample(2)] }
    });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled());

    const history = await screen.findByRole('region', { name: 'Session laps' });
    await fireEvent.click(await within(history).findByRole('button', { name: /^Lap 2/i }));

    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '1'));
    expect(screen.getByRole('button', { name: 'Issues' })).not.toBeDisabled();
    await fireEvent.click(screen.getByRole('button', { name: 'Issues' }));
    expect(canvas).toHaveAttribute('data-overlay', 'issues');
  });

  it('enables the review timeline for a selected completed lap during active recording', async () => {
    const activeCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    const fetchMock = stubApiFetch({
      capture: activeCapture,
      status: { ...statusPayload, capture: activeCapture },
      laps: defaultLoadedSessionLaps,
      recent: { session_id: 'session-live', samples: [makeLiveSample(1), makeLiveSample(2)] }
    });
    renderApp();

    await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled());

    const history = await screen.findByRole('region', { name: 'Session laps' });
    await fireEvent.click(await within(history).findByRole('button', { name: /^Lap 2/i }));

    const timeline = screen.getByRole('region', { name: /Review timeline/i });
    const start = await within(timeline).findByRole('slider', { name: 'Section start sequence' });
    const end = within(timeline).getByRole('slider', { name: 'Section end sequence' });
    const reset = within(timeline).getByRole('button', { name: 'Reset timeline to full lap' });
    expect(start).not.toBeDisabled();
    expect(end).not.toBeDisabled();
    expect(reset).not.toBeDisabled();

    vi.useFakeTimers();
    fetchMock.mockClear();
    await fireEvent.input(start, { target: { value: '11' } });
    await vi.advanceTimersByTimeAsync(150);

    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL) === '/api/laps/newer-lap/summary?start_sequence=11&end_sequence=12')).toBe(true);
  });

  it('skips disabled Issues when cycling overlays during recording', async () => {
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    FakeEventSource.instances[0].emit('capture', {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'speed'));

    await fireEvent.click(screen.getByRole('button', { name: 'RPM' }));
    expect(canvas).toHaveAttribute('data-overlay', 'rpm');

    await fireEvent.keyDown(window, { key: 'O' });

    expect(canvas).toHaveAttribute('data-overlay', 'speed');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issues' })).toBeDisabled());
  });

  it('changes selected overlay state when Speed is chosen', async () => {
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    await fireEvent.click(screen.getByRole('button', { name: 'Speed' }));

    expect(screen.getByRole('button', { name: 'Speed' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Issues' })).toHaveAttribute('aria-pressed', 'false');
    expect(canvas).toHaveAttribute('data-overlay', 'speed');
  });

  it('preserves the user-selected overlay across reconnect recovery', async () => {
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    await fireEvent.click(await screen.findByRole('button', { name: 'Speed' }));

    vi.useFakeTimers();
    FakeEventSource.instances[0].onerror?.();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(500);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2));

    expect(screen.getByRole('button', { name: 'Speed' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-overlay', 'speed');
  });

  it('passes overlay and loaded marker props to the canvas without crashing', async () => {
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '1'));
    await waitFor(() => expect(canvasContext.stroke).toHaveBeenCalled());
  });

  it('renders full-lap summary by default for the newest finalized lap', async () => {
    renderApp();

    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));
    const summary = getSectionSummaryCard();
    expect(summary).toHaveTextContent('Full lap summary');
    expect(within(summary).getByText('102.2')).toBeInTheDocument();
    expect(within(summary).getByText('10–12')).toBeInTheDocument();
  });

  it('renders automatic reference split labels for the full-lap summary', async () => {
    stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    await fireEvent.click(await within(history).findByRole('button', { name: /^Lap 1/i }));
    const summary = getSectionSummaryCard();

    await waitFor(() => expect(within(summary).getByLabelText('Lap time split: +1.234')).toBeInTheDocument());
    expect(within(summary).getByLabelText('Lap time split: +1.234')).toHaveClass('worse');
    expect(within(summary).getByLabelText('Top speed split: -52.5')).toHaveClass('worse');
    expect(within(summary).getByLabelText('Peak slip split: -0.3456')).toHaveClass('better');
  });

  it.each([
    [
      'lap_finalized',
      {
        type: 'lap_finalized',
        session_id: 'session-b',
        lap_id: 'newer-lap',
        boundary_confidence: 'game_field'
      }
    ],
    [
      'lap_track_matched',
      {
        type: 'lap_track_matched',
        session_id: 'session-b',
        lap_id: 'newer-lap',
        reason: 'race_off',
        track_match: {
          assignment: {
            assigned: true,
            track_profile_id: 'profile-emerald'
          }
        }
      }
    ]
  ])('refreshes the selected lap comparison when %s makes a same-session lap the reference', async (eventName, eventPayload) => {
    const trackedOlderLap = {
      ...defaultLoadedSessionLaps[0],
      track_profile_id: 'profile-emerald',
      track_profile_name: 'Emerald Circuit',
      track_profile_layout: 'Full'
    };
    const trackedNewerLap = {
      ...defaultLoadedSessionLaps[1],
      track_profile_id: 'profile-emerald',
      track_profile_name: 'Emerald Circuit',
      track_profile_layout: 'Full'
    };
    const initialLaps = [trackedOlderLap];
    const finalizedLaps = [trackedNewerLap, trackedOlderLap];
    const fixtures = {
      ...lapFixtures,
      'older-lap': {
        ...lapFixtures['older-lap'],
        sessionId: 'session-b'
      }
    };
    let finalized = false;
    const defaultHandler = createDefaultFetchHandler({ laps: initialLaps, fixtures });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      const parsed = new URL(url, 'http://localhost');
      const lapComparisonMatch = parsed.pathname.match(/^\/api\/laps\/([^/]+)\/(reference|ghost|delta)$/);
      if (url === '/api/sessions/session-b/laps') {
        return jsonResponse({ session_id: 'session-b', laps: finalized ? finalizedLaps : initialLaps });
      }
      if (lapComparisonMatch?.[1] === 'older-lap') {
        const lapId = lapComparisonMatch[1] as FixtureId;
        const endpoint = lapComparisonMatch[2];
        const scope = (parsed.searchParams.get('scope') ?? 'track_car') as ReferenceScope;
        const referenceLapId: FixtureId = finalized ? 'newer-lap' : 'older-lap';
        const reference = referenceLapPayload(fixtures, referenceLapId, scope);
        if (endpoint === 'reference') {
          return jsonResponse({
            lap_id: lapId,
            scope,
            context_key: contextKeyFor(scope),
            reference
          });
        }
        if (endpoint === 'ghost') {
          return jsonResponse({
            lap_id: lapId,
            scope,
            context_key: contextKeyFor(scope),
            reference,
            samples: ghostSamplesFor(fixtures, referenceLapId)
          });
        }
        return jsonResponse({
          lap_id: lapId,
          scope,
          context_key: contextKeyFor(scope),
          reference,
          summary: deltaSummaryFor(
            fixtures,
            lapId,
            referenceLapId,
            parsed.searchParams.get('start_sequence'),
            parsed.searchParams.get('end_sequence')
          )
        });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    expect(await screen.findByLabelText('Lap time split: 0.000')).toHaveTextContent('0.000');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    fetchMock.mockClear();
    finalized = true;

    FakeEventSource.instances[0].emit(eventName, eventPayload);

    expect(await screen.findByLabelText('Lap time split: +1.234')).toHaveClass('worse');
    const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
    expect(calls).toContain('/api/sessions/session-b/laps');
    expect(calls).toContain('/api/laps/older-lap/reference?scope=track_car');
  });

  it('does not pin a reference when the R key is pressed', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-ghost-sample-count', '2'));

    fetchMock.mockClear();
    const event = new KeyboardEvent('keydown', { key: 'R', bubbles: true, cancelable: true });
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    await waitFor(() => {
      const postCalls = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === 'POST');
      const referenceCalls = postCalls.filter(([input]) => requestUrl(input as RequestInfo | URL).includes('/reference'));
      expect(referenceCalls).toHaveLength(0);
    });
    expect(screen.queryByText('Reference lap pinned')).not.toBeInTheDocument();
  });

  it('passes ghost samples to the canvas and reports them via data attributes', async () => {
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-ghost-sample-count', '2'));
    await waitFor(() => expect(canvasContext.stroke).toHaveBeenCalled());
  });

  it('reuses cached selected lap samples when switching back to a loaded lap', async () => {
    const fetchMock = stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();

    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-sample-count', '3'));
    const history = await screen.findByRole('region', { name: 'Session laps' });
    await fireEvent.click(within(history).getByRole('button', { name: /^Lap 1/i }));
    await waitFor(() => expect(screen.getByText('49.7')).toBeInTheDocument());
    await fireEvent.click(within(history).getByRole('button', { name: /^Lap 2/i }));
    await waitFor(() => expect(screen.getByText('102.2')).toBeInTheDocument());

    const newerSampleCalls = fetchMock.mock.calls.filter(
      ([input]) => requestUrl(input as RequestInfo | URL) === '/api/laps/newer-lap/samples'
    );
    expect(newerSampleCalls).toHaveLength(1);
  });

  it('shows route loading progress while switching laps within a session', async () => {
    const deferredOlderSamples = deferredResponse();
    const defaultHandler = createDefaultFetchHandler({ laps: defaultLoadedSessionLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/older-lap/samples') {
        return deferredOlderSamples.promise;
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));
    const history = await screen.findByRole('region', { name: 'Session laps' });

    await fireEvent.click(within(history).getByRole('button', { name: /^Lap 1/i }));

    const status = await screen.findByRole('status', { name: 'Route visualiser loading' });
    expect(status).toHaveTextContent(/Loading lap summary|Loaded lap summary|Loaded .*issue/);
    const progress = within(status).getByRole('progressbar', { name: 'Route visualiser loading progress' });
    expect(Number(progress.getAttribute('aria-valuenow'))).toBeGreaterThan(0);

    deferredOlderSamples.resolve(jsonResponse({ lap_id: 'older-lap', samples: olderLapSamples }));

    await waitFor(() => expect(screen.queryByRole('status', { name: 'Route visualiser loading' })).not.toBeInTheDocument());
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(screen.getByText('49.7')).toBeInTheDocument();
  });

  it('finishes an explicit lap switch after route data loads without waiting for comparison responses', async () => {
    const deferredReference = deferredResponse();
    const deferredGhost = deferredResponse();
    const deferredDelta = deferredResponse();
    const defaultHandler = createDefaultFetchHandler({ laps: defaultLoadedSessionLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/older-lap/reference?scope=track_car') {
        return deferredReference.promise;
      }
      if (url === '/api/laps/older-lap/ghost?scope=track_car') {
        return deferredGhost.promise;
      }
      if (url === '/api/laps/older-lap/delta?scope=track_car') {
        return deferredDelta.promise;
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));
    const history = await screen.findByRole('region', { name: 'Session laps' });

    await fireEvent.click(within(history).getByRole('button', { name: /^Lap 1/i }));

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(screen.getByText('49.7')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('status', { name: 'Route visualiser loading' })).not.toBeInTheDocument());
    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL) === '/api/laps/older-lap/delta?scope=track_car')).toBe(true);

    deferredReference.resolve(jsonResponse({
      lap_id: 'older-lap',
      scope: 'track_car',
      context_key: contextKeyFor('track_car'),
      reference: referenceLapPayload(lapFixtures, 'newer-lap', 'track_car')
    }));
    deferredGhost.resolve(jsonResponse({
      lap_id: 'older-lap',
      scope: 'track_car',
      context_key: contextKeyFor('track_car'),
      reference: referenceLapPayload(lapFixtures, 'newer-lap', 'track_car'),
      samples: ghostSamplesFor(lapFixtures, 'newer-lap')
    }));
    deferredDelta.resolve(jsonResponse({
      lap_id: 'older-lap',
      scope: 'track_car',
      context_key: contextKeyFor('track_car'),
      reference: referenceLapPayload(lapFixtures, 'newer-lap', 'track_car'),
      summary: deltaSummaryFor(lapFixtures, 'older-lap', 'newer-lap', null, null)
    }));
    await waitFor(() => expect(canvas).toHaveAttribute('data-ghost-sample-count', '3'));
  });

  it('clears route loading progress and reports a toast when reference comparison fails during a lap switch', async () => {
    const defaultHandler = createDefaultFetchHandler({ laps: defaultLoadedSessionLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/older-lap/reference?scope=track_car') {
        throw new Error('reference comparison failed');
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));
    const history = await screen.findByRole('region', { name: 'Session laps' });

    await fireEvent.click(within(history).getByRole('button', { name: /^Lap 1/i }));

    expect(await screen.findByRole('status', { name: 'Route visualiser loading' })).toHaveTextContent(/Loading lap summary|Loaded lap summary|Loaded .*issue/);
    expect(await findToast('Unable to load reference comparison')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('status', { name: 'Route visualiser loading' })).not.toBeInTheDocument());
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(screen.getByText('49.7')).toBeInTheDocument();
  });

  it('renders the full-lap delta summary in the floating section summary', async () => {
    renderApp();

    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('3/2 samples'));
    const summary = getSectionSummaryCard();
    expect(within(summary).getByText('3/2 samples')).toBeInTheDocument();
    expect(within(summary).getAllByText('-1.500s')).toHaveLength(2);
    expect(within(summary).getByText('+9.5')).toBeInTheDocument();
    expect(within(summary).getByText('+0.250s')).toBeInTheDocument();
  });

  it('does not reopen the section summary after the user hides it', async () => {
    renderApp();

    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('Full lap summary'));
    await fireEvent.click(within(getSectionSummaryCard()).getByRole('button', { name: 'Hide section summary' }));
    await waitFor(() => expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Section summary/i })).not.toBeInTheDocument());

    vi.useFakeTimers();
    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '11' } });
    await vi.advanceTimersByTimeAsync(150);

    await waitFor(() => expect(within(getVisualisationStage()).queryByRole('complementary', { name: /Section summary/i })).not.toBeInTheDocument());
    await fireEvent.click(within(getVisualisationStage()).getByRole('button', { name: 'Show section summary' }));
    expect(getSectionSummaryCard()).toHaveTextContent('Selected section summary');
  });

  it('auto-selects the newest completed lap when lap statuses are replay-complete or lap-boundary', async () => {
    stubApiFetch({ laps: replayCompletedLaps });
    renderApp();

    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));
    const summary = getSectionSummaryCard();
    expect(summary).toHaveTextContent('Full lap summary');
    expect(screen.getByText('Midnight Club')).toBeInTheDocument();
    expect(within(summary).getByText('102.2')).toBeInTheDocument();
    expect(within(summary).getByText('10–12')).toBeInTheDocument();
  });

  it('counts a lap with a computed lap time as completed even when ended_at_ms is absent', async () => {
    stubApiFetch({
      laps: [
        {
          ...defaultLoadedSessionLaps[1],
          ended_at_ms: null,
          ended_reason: null,
          lap_time_ms: 1_000
        }
      ]
    });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '1'));
    expect(screen.getByRole('button', { name: 'Issues' })).not.toBeDisabled();
    expect(canvas).toHaveAttribute('data-overlay', 'issues');
  });

  it('does not auto-select an active recording lap ahead of a completed lap', async () => {
    const activeLoadedSessionLaps: LapSummary[] = activeRecordingLaps.map((lap) => ({ ...lap, session_id: 'session-b' }));
    stubApiFetch({ laps: activeLoadedSessionLaps });
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    await waitFor(() => expect(screen.getByText('49.7')).toBeInTheDocument());
    const summary = getSectionSummaryCard();
    expect(summary).toHaveTextContent('Full lap summary');
    expect(within(summary).queryByText('No lap summary is available yet.')).not.toBeInTheDocument();
    expect(within(summary).getByText('49.7')).toBeInTheDocument();
    expect(within(history).getByRole('button', { name: /^Lap 2/i })).toHaveAttribute('aria-pressed', 'true');
    expect(within(history).getByRole('button', { name: /^Lap 3/i })).toHaveAttribute('aria-pressed', 'false');
  });

  it('coalesces quick timeline changes into one section-summary request for the final range', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));

    vi.useFakeTimers();
    fetchMock.mockClear();
    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '11' } });
    await fireEvent.input(screen.getByRole('slider', { name: 'Section end sequence' }), { target: { value: '11' } });

    expect(fetchMock.mock.calls.filter(([input]) => requestUrl(input as RequestInfo | URL).includes('/api/laps/newer-lap/summary'))).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(149);
    expect(fetchMock.mock.calls.filter(([input]) => requestUrl(input as RequestInfo | URL).includes('/api/laps/newer-lap/summary'))).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);

    const summaryCalls = fetchMock.mock.calls.filter(([input]) => requestUrl(input as RequestInfo | URL).includes('/api/laps/newer-lap/summary'));
    expect(summaryCalls).toHaveLength(1);
    expect(requestUrl(summaryCalls[0][0] as RequestInfo | URL)).toBe('/api/laps/newer-lap/summary?start_sequence=11&end_sequence=11');
  });

  it('passes selected route segment state to the canvas', async () => {
    renderApp();
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));

    vi.useFakeTimers();
    const canvas = screen.getByLabelText('Live telemetry path');
    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '11' } });
    await waitFor(() => expect(canvas).toHaveAttribute('data-selected-start', '11'));
    expect(canvas).toHaveAttribute('data-selected-end', '12');
    await vi.advanceTimersByTimeAsync(150);
    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('Selected section summary'));
  });

  it('fetches selected-section delta and updates the displayed delta summary', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));

    vi.useFakeTimers();
    fetchMock.mockClear();
    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '11' } });
    await vi.advanceTimersByTimeAsync(150);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL) === '/api/laps/newer-lap/delta?scope=track_car&start_sequence=11&end_sequence=12')).toBe(true);
    });
    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('Selected section delta'));
    const summary = getSectionSummaryCard();
    expect(within(summary).getAllByText('+0.500s')).toHaveLength(2);
    expect(within(summary).getByText('+5.6')).toBeInTheDocument();
    expect(within(summary).getByText('2/2 samples')).toBeInTheDocument();
  });

  it('keeps the selected-section delta when a delayed full-lap comparison resolves afterwards', async () => {
    const deferredFullLapDelta = deferredResponse();
    const defaultHandler = createDefaultFetchHandler();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/newer-lap/delta?scope=track_car') {
        return deferredFullLapDelta.promise;
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderApp();
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));

    vi.useFakeTimers();
    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '11' } });
    await vi.advanceTimersByTimeAsync(150);
    vi.useRealTimers();

    await waitFor(() => expect(getSectionSummaryCard()).toHaveTextContent('Selected section delta'));
    let summary = getSectionSummaryCard();
    expect(within(summary).getAllByText('+0.500s')).toHaveLength(2);
    expect(within(summary).getByText('+5.6')).toBeInTheDocument();
    expect(within(summary).getByText('2/2 samples')).toBeInTheDocument();

    deferredFullLapDelta.resolve(jsonResponse({
      lap_id: 'newer-lap',
      scope: 'track_car',
      context_key: contextKeyFor('track_car'),
      reference: referenceLapPayload(lapFixtures, 'older-lap', 'track_car'),
      summary: deltaSummaryFor(lapFixtures, 'newer-lap', 'older-lap', null, null)
    }));
    await Promise.resolve();
    await Promise.resolve();

    summary = getSectionSummaryCard();
    expect(summary).toHaveTextContent('Selected section delta');
    expect(within(summary).queryByText('Full lap delta')).not.toBeInTheDocument();
    expect(within(summary).getAllByText('+0.500s')).toHaveLength(2);
    expect(within(summary).getByText('+5.6')).toBeInTheDocument();
    expect(within(summary).getByText('2/2 samples')).toBeInTheDocument();
    expect(within(summary).queryByText('-1.500s')).not.toBeInTheDocument();
    expect(within(summary).queryByText('+9.5')).not.toBeInTheDocument();
    expect(within(summary).queryByText('3/2 samples')).not.toBeInTheDocument();
  });

  it('ignores stale section-summary responses after switching laps', async () => {
    const deferredOlderSection = deferredResponse();
    const defaultHandler = createDefaultFetchHandler({ laps: defaultLoadedSessionLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/older-lap/summary?start_sequence=2&end_sequence=2') {
        return deferredOlderSection.promise;
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderApp();
    await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(screen.getByText('102.2')).toBeInTheDocument());

    await fireEvent.click(screen.getByRole('button', { name: /^Lap 1/i }));
    await waitFor(() => expect(screen.getByText('49.7')).toBeInTheDocument());

    vi.useFakeTimers();
    fetchMock.mockClear();
    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '2' } });
    await vi.advanceTimersByTimeAsync(150);
    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL) === '/api/laps/older-lap/summary?start_sequence=2&end_sequence=2')).toBe(true);
    vi.useRealTimers();

    await fireEvent.click(screen.getByRole('button', { name: /^Lap 2/i }));
    await waitFor(() => expect(screen.getByText('102.2')).toBeInTheDocument());

    deferredOlderSection.resolve(jsonResponse({ lap_id: 'older-lap', session_id: 'session-a', summary: lapFixtures['older-lap'].sectionSummaries['2-2'] }));
    await Promise.resolve();
    await Promise.resolve();

    const summary = getSectionSummaryCard();
    expect(summary).toHaveTextContent('Full lap summary');
    expect(within(summary).getByText('102.2')).toBeInTheDocument();
    expect(within(summary).queryByText('Selected section summary')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-selected-start', '');
    expect(screen.queryByText('49.7')).not.toBeInTheDocument();
  });

  it('clears prior lap drilldown state immediately when a newly selected lap load fails', async () => {
    const defaultHandler = createDefaultFetchHandler({ laps: defaultLoadedSessionLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/older-lap/summary' || url === '/api/laps/older-lap/markers' || url === '/api/laps/older-lap/samples') {
        throw new Error('older lap failed');
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(screen.getByText('102.2')).toBeInTheDocument());
    expect(canvas).toHaveAttribute('data-marker-count', '1');

    await fireEvent.click(screen.getByRole('button', { name: /^Lap 1/i }));

    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '0'));
    expect(within(getSectionSummaryCard()).queryByText('102.2')).not.toBeInTheDocument();
    expect(within(getSectionSummaryCard()).getByText('No lap summary is available yet.')).toBeInTheDocument();
    expect(await findToast('Unable to load lap drilldown data')).toBeInTheDocument();
  });

  it('clicking a lap route sample opens the dashboard scrubbed to that sample', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '1'));

    await fireEvent.click(screen.getByRole('button', { name: 'Speed' }));
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'speed'));
    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });

    expect(await screen.findByRole('region', { name: 'Telemetry dashboard canvas' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Dashboard playback' })).toHaveTextContent('Sample 2 of 3');
    expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument();
  });

  it('does not drill into the dashboard when the selected lap is still recording', async () => {
    const recordingLap: LapSummary = {
      ...defaultLoadedSessionLaps[1],
      status: 'recording',
      ended_at_ms: null,
      ended_reason: null,
      boundary_confidence: null
    };
    stubApiFetch({ laps: [defaultLoadedSessionLaps[0], recordingLap] });
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    await fireEvent.click(await within(history).findByRole('button', { name: /^Lap 2/i }));
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));

    await fireEvent.click(screen.getByRole('button', { name: 'Speed' }));
    await waitFor(() => expect(canvas).toHaveAttribute('data-overlay', 'speed'));
    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });

    expect(screen.queryByRole('region', { name: 'Telemetry dashboard canvas' })).toBeNull();
    expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument();
  });

  it('clicking an issue marker opens the issue popover without switching to dashboard', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '1'));

    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });

    expect(await screen.findByRole('dialog', { name: 'Issue details' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Rear combined slip at 0:00.001' })).toBeInTheDocument();
    expect(screen.getByText('Rear combined slip: 1.28 ≥ 1.15')).toBeInTheDocument();
    expect(screen.queryByText('High slip')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Telemetry dashboard canvas' })).toBeNull();
  });

  it('opens the issue popover on hover and closes it when hover clears', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '1'));

    await fireEvent.mouseMove(canvas, { clientX: 450, clientY: 280 });

    expect(await screen.findByRole('dialog', { name: 'Issue details' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Rear combined slip at 0:00.001' })).toBeInTheDocument();
    expect(screen.getByText('Hover issue details · click an issue marker to pin')).toBeInTheDocument();
    expect(document.querySelector('.popover-backdrop')).not.toBeInTheDocument();

    await fireEvent.mouseMove(canvas, { clientX: 10, clientY: 10 });

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument());
  });

  it('pins the issue popover on click so mouse leave does not close it', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '1'));

    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });

    expect(await screen.findByRole('dialog', { name: 'Issue details' })).toBeInTheDocument();
    expect(screen.getByText('Pinned issue details')).toBeInTheDocument();

    await fireEvent.mouseLeave(canvas);

    expect(screen.getByRole('dialog', { name: 'Issue details' })).toBeInTheDocument();
    expect(screen.getByText('Pinned issue details')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Close issue popover' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument());
  });

  it('clears the section selection and closes the issue popover with Escape', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '1'));

    await fireEvent.input(screen.getByRole('slider', { name: 'Section start sequence' }), { target: { value: '11' } });
    expect(canvas).toHaveAttribute('data-selected-start', '11');
    expect(canvas).toHaveAttribute('data-selected-end', '12');

    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });
    expect(await screen.findByRole('dialog', { name: 'Issue details' })).toBeInTheDocument();

    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument());
    expect(canvas).toHaveAttribute('data-selected-start', '');
    expect(canvas).toHaveAttribute('data-selected-end', '');
  });

  it('does not fetch raw point details when clicking a live route without a selected lap', async () => {
    const liveCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    const liveSamples = [makeLiveSample(1), makeLiveSample(2), makeLiveSample(3)];
    const fetchMock = stubApiFetch({
      laps: [],
      capture: liveCapture,
      status: { ...statusPayload, capture: liveCapture },
      recent: { session_id: 'session-live', samples: liveSamples }
    });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));
    fetchMock.mockClear();

    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });

    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL).includes('/points/'))).toBe(false);
    expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Point packet details' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Telemetry dashboard canvas' })).toBeNull();
  });

  it('issue popover close button has tooltip and accessibility label', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-issue-target-count', '1'));

    await fireEvent.click(canvas, { clientX: 450, clientY: 280 });

    const closeButton = await screen.findByRole('button', { name: 'Close issue popover' });
    expect(closeButton).toHaveAttribute('title', 'Close issue popover');
    expect(closeButton).toHaveAccessibleName('Close issue popover');
    await fireEvent.click(closeButton);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Issue details' })).not.toBeInTheDocument());
  });

  it('shows each lap track name in the session sidebar lap card', async () => {
    const lapsWithTracks = defaultLoadedSessionLaps.map((lap, index) =>
      index === 0
        ? {
            ...lap,
            track_profile_id: 'profile-emerald',
            track_profile_name: 'Emerald Circuit',
            track_profile_layout: 'Full'
          }
        : {
            ...lap,
            track_profile_id: null,
            track_profile_name: null,
            track_profile_layout: null
          }
    );
    stubApiFetch({ laps: lapsWithTracks });
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    expect(await within(history).findByText('Emerald Circuit — Full')).toBeInTheDocument();
    expect(within(history).getByText('Unknown track')).toBeInTheDocument();
  });

  it('shows selected lap track in the floating lap summary as a button', async () => {
    const lapsWithTrack = defaultLaps.map((lap) =>
      lap.id === 'newer-lap'
        ? {
            ...lap,
            track_profile_id: 'profile-emerald',
            track_profile_name: 'Emerald Circuit',
            track_profile_layout: 'Full'
          }
        : lap
    );
    stubApiFetch({ laps: lapsWithTrack });
    renderApp();

    expect(await screen.findByRole('button', { name: 'Change track assignment: Emerald Circuit — Full' })).toBeInTheDocument();
  });

  it('opens track picker from lap summary and orders suggested tracks first', async () => {
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: /Change track assignment:/ }));

    const picker = await screen.findByRole('dialog', { name: 'Change lap track' });
    expect(within(picker).getByRole('heading', { name: 'Suggested' })).toBeInTheDocument();
    expect(within(picker).getByRole('heading', { name: 'All known tracks' })).toBeInTheDocument();
    const firstAssignButton = within(picker).getAllByRole('button', { name: /Assign/ })[0];
    expect(firstAssignButton).toHaveAccessibleName('Assign Emerald Circuit — Full');
    expect(firstAssignButton).toHaveTextContent(/^Assign$/);
  });

  it('track picker filters known tracks and assigns selected lap only', async () => {
    const fetchMock = stubApiFetch();
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: /Change track assignment:/ }));
    const picker = await screen.findByRole('dialog', { name: 'Change lap track' });
    await fireEvent.input(within(picker).getByLabelText('Search known tracks'), { target: { value: 'emerald' } });
    await fireEvent.click(within(picker).getByRole('button', { name: 'Assign Emerald Circuit — Full' }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/tracks/profiles/profile-emerald/assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: 'session-b', lapId: 'newer-lap' })
      })
    );
  });

  it('refreshes lap history when a finalized lap is auto-assigned by the matcher', async () => {
    const initialLaps = defaultLoadedSessionLaps.map((lap) => ({
      ...lap,
      track_profile_id: null,
      track_profile_name: null,
      track_profile_layout: null
    }));
    const assignedLaps = initialLaps.map((lap) =>
      lap.id === 'newer-lap'
        ? {
            ...lap,
            track_profile_id: 'profile-emerald',
            track_profile_name: 'Emerald Circuit',
            track_profile_layout: 'Full'
          }
        : lap
    );
    let assigned = false;
    const defaultHandler = createDefaultFetchHandler({ laps: initialLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/sessions/session-b/laps' && assigned) {
        return jsonResponse({ session_id: 'session-b', laps: assignedLaps });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    expect((await within(history).findAllByText('Unknown track')).length).toBeGreaterThan(0);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    fetchMock.mockClear();
    assigned = true;

    FakeEventSource.instances[0].emit('lap_finalized', {
      type: 'lap_finalized',
      session_id: 'session-b',
      lap_id: 'newer-lap',
      boundary_confidence: 'game_field',
      track_match: {
        assignment: {
          assigned: true,
          track_profile_id: 'profile-emerald'
        }
      }
    });

    await waitFor(() => expect(within(history).getByText('Emerald Circuit — Full')).toBeInTheDocument());
    const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
    expect(calls).toContain('/api/tracks/profiles');
    expect(calls).toContain('/api/sessions/session-b/laps');
  });

  it('refreshes lap history when a race-off track match event assigns an open lap', async () => {
    const initialLaps = defaultLoadedSessionLaps.map((lap) => ({
      ...lap,
      track_profile_id: null,
      track_profile_name: null,
      track_profile_layout: null
    }));
    const assignedLaps = initialLaps.map((lap) =>
      lap.id === 'newer-lap'
        ? {
            ...lap,
            track_profile_id: 'profile-emerald',
            track_profile_name: 'Emerald Circuit',
            track_profile_layout: 'Full'
          }
        : lap
    );
    let assigned = false;
    const defaultHandler = createDefaultFetchHandler({ laps: initialLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/sessions/session-b/laps' && assigned) {
        return jsonResponse({ session_id: 'session-b', laps: assignedLaps });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    expect((await within(history).findAllByText('Unknown track')).length).toBeGreaterThan(0);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    fetchMock.mockClear();
    assigned = true;

    FakeEventSource.instances[0].emit('lap_track_matched', {
      type: 'lap_track_matched',
      session_id: 'session-b',
      lap_id: 'newer-lap',
      reason: 'race_off',
      track_match: {
        assignment: {
          assigned: true,
          track_profile_id: 'profile-emerald'
        }
      }
    });

    await waitFor(() => expect(within(history).getByText('Emerald Circuit — Full')).toBeInTheDocument());
    const calls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
    expect(calls).toContain('/api/tracks/profiles');
    expect(calls).toContain('/api/sessions/session-b/laps');
  });

  it('refreshes lap history when opening suggested tracks auto-assigns the selected lap', async () => {
    const initialLaps = defaultLoadedSessionLaps.map((lap) => ({
      ...lap,
      track_profile_id: null,
      track_profile_name: null,
      track_profile_layout: null
    }));
    const assignedLaps = initialLaps.map((lap) =>
      lap.id === 'newer-lap'
        ? {
            ...lap,
            track_profile_id: 'profile-emerald',
            track_profile_name: 'Emerald Circuit',
            track_profile_layout: 'Full'
          }
        : lap
    );
    let assigned = false;
    const defaultHandler = createDefaultFetchHandler({ laps: initialLaps });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/laps/newer-lap/track-match' && init?.method === 'POST') {
        assigned = true;
        return jsonResponse({
          lap_id: 'newer-lap',
          session_id: 'session-b',
          candidates: [
            {
              track_profile_id: 'profile-emerald',
              track_profile_name: 'Emerald Circuit',
              track_profile_layout: 'Full',
              confidence: 0.99
            }
          ],
          assignment: {
            assigned: true,
            track_profile_id: 'profile-emerald',
            confidence: 0.99
          }
        });
      }
      if (url === '/api/sessions/session-b/laps' && assigned) {
        return jsonResponse({ session_id: 'session-b', laps: assignedLaps });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();

    await fireEvent.click(await screen.findByRole('button', { name: /Change track assignment:/ }));

    const history = await screen.findByRole('region', { name: 'Session laps' });
    await waitFor(() => expect(within(history).getByText('Emerald Circuit — Full')).toBeInTheDocument());
    expect(screen.queryByRole('dialog', { name: 'Change lap track' })).not.toBeInTheDocument();
  });

  it('renders Auto/Manual controls, newest-first loaded-session laps, and selectable lap buttons', async () => {
    stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();

    const captureControls = getFloatingCaptureControls();
    expect(within(captureControls).getByRole('button', { name: 'Auto capture' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(captureControls).getByRole('button', { name: 'Manual capture' })).toHaveAttribute('aria-pressed', 'false');
    const manualAction = within(captureControls).getByRole('button', { name: 'Start manual capture' });
    expect(manualAction).toHaveAttribute('title', 'Manual start/stop is disabled in auto mode');
    expect(manualAction).toBeDisabled();
    expect(within(captureControls).queryByRole('button', { name: 'Stop manual capture' })).toBeNull();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    expect(await within(history).findByRole('heading', { name: 'Midnight Club' })).toBeInTheDocument();
    const lapItems = within(history).getAllByRole('listitem');
    expect(lapItems[0]).toHaveTextContent('Lap 2');
    expect(lapItems[0]).not.toHaveTextContent('Midnight Club');
    expect(lapItems[1]).toHaveTextContent('Lap 1');
    expect(lapItems[1]).not.toHaveTextContent('Sunset Sprint');
    expect(within(history).getByRole('button', { name: /^Lap 2/i })).toHaveAttribute('aria-pressed', 'true');
  });

  it('switches the history drawer to the loaded session aggregate summary', async () => {
    stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();

    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    expect(within(drawer).getByRole('button', { name: 'Laps' })).toHaveAttribute('aria-pressed', 'true');

    await fireEvent.click(within(drawer).getByRole('button', { name: 'Session' }));

    expect(within(drawer).getByRole('button', { name: 'Laps' })).toHaveAttribute('aria-pressed', 'false');
    expect(within(drawer).getByRole('button', { name: 'Session' })).toHaveAttribute('aria-pressed', 'true');
    const summary = await within(drawer).findByRole('region', { name: 'Midnight Club lap aggregate summary' });
    expect(summary).toHaveTextContent('Midnight Club');
    expect(summary).not.toHaveTextContent('Horizon Speedway — Oval');
    expect(summary).not.toHaveTextContent('Unknown track');
    expect(summary).toHaveTextContent('active');
    expect(summary).toHaveTextContent('Laps');
    expect(summary).toHaveTextContent('2/2');
    expect(summary).toHaveTextContent('Best');
    expect(summary).toHaveTextContent('1:35.000');
    expect(summary).toHaveTextContent('Average');
    expect(summary).toHaveTextContent('1:35.617');
    expect(summary).toHaveTextContent('Total');
    expect(summary).toHaveTextContent('3:11.234');
  });

  it('keeps sidebar Session mode scoped to the loaded session instead of listing all sessions', async () => {
    const laps = defaultLaps.map((lap) => ({ ...lap, session_id: lap.id === 'newer-lap' ? 'session-b' : 'session-a' }));
    stubApiFetch({ laps });
    renderApp();

    const drawer = await screen.findByRole('complementary', { name: /Loaded session laps/i });
    await fireEvent.click(within(drawer).getByRole('button', { name: 'Session' }));

    const summary = await within(drawer).findByRole('region', { name: 'Midnight Club lap aggregate summary' });
    expect(summary).toHaveTextContent('Midnight Club');
    expect(summary).not.toHaveTextContent('Sunset Sprint');
    expect(within(drawer).queryByRole('region', { name: 'Sunset Sprint lap aggregate summary' })).not.toBeInTheDocument();
  });

  it('deletes an individual completed lap from history without confirmation and refreshes selection', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const fetchMock = stubApiFetch({ laps: defaultLoadedSessionLaps });
    try {
      renderApp();

      const history = await screen.findByRole('region', { name: 'Session laps' });
      expect(await within(history).findByRole('button', { name: /^Lap 2/i })).toHaveAttribute('aria-pressed', 'true');

      const deleteButton = within(history).getByRole('button', { name: 'Delete Midnight Club lap 2' });
      expect(deleteButton.querySelector('svg')).toBeInTheDocument();

      await fireEvent.click(deleteButton);

      expect(confirmSpy).not.toHaveBeenCalled();
      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith('/api/laps/newer-lap', { method: 'DELETE' })
      );
      expect(await findToast('Deleted Midnight Club lap 2')).toBeInTheDocument();
      await waitFor(() => expect(within(history).queryByRole('button', { name: /^Lap 2/i })).not.toBeInTheDocument());
      expect(within(history).getByRole('button', { name: /^Lap 1/i })).toHaveAttribute('aria-pressed', 'true');
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it('removes an auto-discarded lap from the loaded history immediately', async () => {
    stubApiFetch({ laps: defaultLoadedSessionLaps });
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const history = await screen.findByRole('region', { name: 'Session laps' });
    expect(await within(history).findByRole('button', { name: /^Lap 2/i })).toHaveAttribute('aria-pressed', 'true');

    FakeEventSource.instances[0].emit('auto_lap_discarded', {
      type: 'auto_lap_discarded',
      lap_id: 'newer-lap',
      session_id: 'session-b',
      reason: 'no_current_lap_progress'
    });

    await waitFor(() => expect(within(history).queryByRole('button', { name: /^Lap 2/i })).not.toBeInTheDocument());
    expect(within(history).getByRole('button', { name: /^Lap 1/i })).toHaveAttribute('aria-pressed', 'true');
  });

  it('allows deleting a TBD in-progress lap from history', async () => {
    const inProgressLap: LapSummary = {
      ...defaultLoadedSessionLaps[1],
      id: 'tbd-lap',
      lap_number: 3,
      status: 'recording',
      started_at_ms: 7_000,
      ended_at_ms: null,
      ended_reason: null,
      boundary_confidence: 'unknown',
      lap_time_ms: null
    };
    const fetchMock = stubApiFetch({ laps: [defaultLoadedSessionLaps[0], inProgressLap] });
    renderApp();

    const history = await screen.findByRole('region', { name: 'Session laps' });
    expect(await within(history).findByText('TBD')).toBeInTheDocument();

    const deleteButton = within(history).getByRole('button', { name: 'Delete Midnight Club lap 3' });
    expect(deleteButton).toBeEnabled();

    await fireEvent.click(deleteButton);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/laps/tbd-lap', { method: 'DELETE' })
    );
    expect(await findToast('Deleted Midnight Club lap 3')).toBeInTheDocument();
    await waitFor(() => expect(within(history).queryByRole('button', { name: 'Delete Midnight Club lap 3' })).not.toBeInTheDocument());
  });

  it('shows top-centre toast region and accepts live samples', async () => {
    renderApp();
    await findToast('Tracker ready');

    FakeEventSource.instances[0].emit('live_sample', {
      type: 'live_sample',
      sample: { sequence: 3, received_at_ms: 3, game_timestamp_ms: 3, lap_number: 0, current_lap: 0, current_race_time: 0, x: 8, y: 0, z: 8, speed_mps: 14, throttle: 255, brake: 0, steer: 0, gear: 2 }
    });

    expect(screen.getByLabelText('Status notifications')).toHaveAttribute('aria-live', 'polite');
  });

  it('keeps the live canvas blank for recovered and incoming idle telemetry', async () => {
    stubApiFetch({ laps: [] });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '0'));
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    FakeEventSource.instances[0].emit('live_sample', {
      type: 'live_sample',
      sample: { sequence: 9, received_at_ms: 9, game_timestamp_ms: 9, lap_number: 0, current_lap: 0, current_race_time: 0, x: 18, y: 0, z: 18, speed_mps: 14, throttle: 255, brake: 0, steer: 0, gear: 2 }
    });

    expect(canvas).toHaveAttribute('data-sample-count', '0');
  });

  it('pauses and resumes live follow with the Space shortcut outside form controls', async () => {
    renderApp();

    const liveFollowButton = await screen.findByRole('button', { name: 'Live follow' });
    expect(liveFollowButton).toHaveAttribute('title', 'Pause live follow');
    expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Live follow running')).toBeInTheDocument();

    const pauseEvent = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
    window.dispatchEvent(pauseEvent);

    expect(pauseEvent.defaultPrevented).toBe(true);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Live follow' })).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.getByRole('button', { name: 'Live follow' })).toHaveAttribute('title', 'Resume live follow');
    expect(screen.getByText('Live follow paused')).toBeInTheDocument();

    const resumeEvent = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
    window.dispatchEvent(resumeEvent);

    expect(resumeEvent.defaultPrevented).toBe(true);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Live follow' })).toHaveAttribute('aria-pressed', 'false'));
    expect(screen.getByRole('button', { name: 'Live follow' })).toHaveAttribute('title', 'Pause live follow');
    expect(screen.getByText('Live follow running')).toBeInTheDocument();
  });

  it('pauses and resumes live follow from the floating canvas button', async () => {
    renderApp();

    const stage = getVisualisationStage();
    const liveFollowButton = await within(stage).findByRole('button', { name: 'Live follow' });
    expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false');

    await fireEvent.click(liveFollowButton);

    await waitFor(() => expect(liveFollowButton).toHaveAttribute('aria-pressed', 'true'));
    expect(liveFollowButton).toHaveTextContent('Live follow paused');

    await fireEvent.click(liveFollowButton);

    await waitFor(() => expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false'));
    expect(liveFollowButton).toHaveTextContent('Live follow running');
  });

  it('does not toggle live follow with the Space shortcut while a utility modal is open', async () => {
    renderApp();

    const liveFollowButton = await screen.findByRole('button', { name: 'Live follow' });
    expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false');
    await openSettingsModal();

    const modalShortcutEvent = new KeyboardEvent('keydown', { key: ' ', code: 'Space', bubbles: true, cancelable: true });
    window.dispatchEvent(modalShortcutEvent);

    expect(modalShortcutEvent.defaultPrevented).toBe(false);
    expect(liveFollowButton).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Live follow running')).toBeInTheDocument();
  });

  it('does not fire shortcuts while typing in input, textarea, or select controls', async () => {
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-marker-count', '1'));
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    await fireEvent.keyDown(screen.getByRole('slider', { name: 'Section start sequence' }), { key: 'O' });
    expect(canvas).toHaveAttribute('data-overlay', 'issues');

    const textarea = document.createElement('textarea');
    document.body.append(textarea);
    try {
      await fireEvent.keyDown(textarea, { key: 'O' });
      expect(canvas).toHaveAttribute('data-overlay', 'issues');
    } finally {
      textarea.remove();
    }

    const select = document.createElement('select');
    document.body.append(select);
    try {
      await fireEvent.keyDown(select, { key: 'R' });
      expect(canvas).toHaveAttribute('data-overlay', 'issues');
    } finally {
      select.remove();
    }

    await fireEvent.keyDown(screen.getByRole('slider', { name: 'Section start sequence' }), { key: ' ' });
    expect(screen.getByRole('button', { name: 'Live follow' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows a warning toast when lap boundary confidence is uncertain', async () => {
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    FakeEventSource.instances[0].emit('lap_finalized', {
      type: 'lap_finalized',
      lap_id: 'lap-uncertain',
      boundary_confidence: 'uncertain',
      uncertainty: 'partial_lap'
    });

    expect(await findToast('Lap boundary uncertain: partial_lap')).toBeInTheDocument();
  });

  it('disables manual start while auto idle and does not call capture start', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    const captureControls = getFloatingCaptureControls();
    const startButton = within(captureControls).getByRole('button', { name: 'Start manual capture' });
    await waitFor(() => expect(within(captureControls).getByRole('button', { name: 'Auto capture' })).toHaveAttribute('aria-pressed', 'true'));
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-marker-count', '1'));

    fetchMock.mockClear();
    await fireEvent.click(startButton);

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('disables manual stop while auto recording and does not call capture stop', async () => {
    const autoRecordingCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: {
        ...capturePayload.recording,
        active: true,
        phase: 'recording'
      }
    };
    const fetchMock = stubApiFetch({ capture: autoRecordingCapture, status: { ...statusPayload, capture: autoRecordingCapture } });
    renderApp();
    const captureControls = getFloatingCaptureControls();
    await waitFor(() => expect(within(captureControls).getByRole('button', { name: 'Stop manual capture' })).toBeInTheDocument());
    const stopButton = within(captureControls).getByRole('button', { name: 'Stop manual capture' });
    await waitFor(() => expect(stopButton).toBeDisabled());
    const timeline = screen.getByRole('region', { name: /Review timeline/i });
    expect(within(timeline).queryByRole('slider', { name: 'Section start sequence' })).toBeNull();
    expect(within(timeline).queryByRole('button', { name: 'Reset timeline to full lap' })).toBeNull();

    fetchMock.mockClear();
    await fireEvent.click(stopButton);

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('manual mode permits start when idle', async () => {
    const manualCapture = {
      ...capturePayload,
      mode: 'manual',
      recording: { ...capturePayload.recording, mode: 'manual' },
      settings: { ...capturePayload.settings, capture_mode: 'manual' }
    };
    const fetchMock = stubApiFetch({
      capture: manualCapture,
      status: { ...statusPayload, settings: { ...statusPayload.settings, capture_mode: 'manual' }, capture: manualCapture }
    });
    renderApp();

    const captureControls = getFloatingCaptureControls();
    await waitFor(() => expect(within(captureControls).getByRole('button', { name: 'Manual capture' })).toHaveAttribute('aria-pressed', 'true'));
    const startButton = within(captureControls).getByRole('button', { name: 'Start manual capture' });
    expect(startButton).toBeEnabled();
    expect(startButton).toHaveAttribute('title', 'Start manual capture');
    expect(within(captureControls).queryByRole('button', { name: 'Stop manual capture' })).toBeNull();
    await fireEvent.click(startButton);
    expect(fetchMock).toHaveBeenCalledWith('/api/capture/start', { method: 'POST' });
  });

  it('manual mode permits stop when actively recording', async () => {
    const manualRecordingCapture = {
      ...capturePayload,
      mode: 'manual',
      phase: 'recording',
      recording: { ...capturePayload.recording, mode: 'manual', active: true, phase: 'recording' },
      settings: { ...capturePayload.settings, capture_mode: 'manual' }
    };
    const fetchMock = stubApiFetch({
      capture: manualRecordingCapture,
      status: { ...statusPayload, settings: { ...statusPayload.settings, capture_mode: 'manual' }, capture: manualRecordingCapture }
    });
    renderApp();

    const captureControls = getFloatingCaptureControls();
    await waitFor(() => expect(within(captureControls).getByRole('button', { name: 'Manual capture' })).toHaveAttribute('aria-pressed', 'true'));
    const stopButton = within(captureControls).getByRole('button', { name: 'Stop manual capture' });
    expect(stopButton).toBeEnabled();
    expect(stopButton).toHaveAttribute('title', 'Stop manual capture');
    expect(within(captureControls).queryByRole('button', { name: 'Start manual capture' })).toBeNull();
    await fireEvent.click(stopButton);
    expect(fetchMock).toHaveBeenCalledWith('/api/capture/stop', { method: 'POST' });
  });

  it('keeps the recovered live listener status when the SSE stream sends its initial placeholder status', async () => {
    stubApiFetch({ status: receivingStatusPayload });
    renderApp();

    expect(await findListenerStatus(/Listener receiving: receiving replay packets/i)).toBeInTheDocument();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    FakeEventSource.instances[0].emit('status', { state: 'waiting', message: 'waiting for telemetry' });

    expect(screen.getByLabelText(/Listener receiving: receiving replay packets/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Listener waiting: waiting for telemetry/i)).not.toBeInTheDocument();
  });

  it('ignores malformed SSE payloads without closing the stream and warns once', async () => {
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];

    expect(() => source.emitRaw('status', '{bad json')).not.toThrow();
    expect(() => source.emitRaw('toast', 'nope')).not.toThrow();
    expect(() => source.emitRaw('live_sample', 'still nope')).not.toThrow();
    expect(source.closed).toBe(false);
    expect(await within(getToastStack()).findAllByText('Malformed telemetry event data received')).toHaveLength(1);
  });

  it('redraws the telemetry path when live samples update', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps });
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    FakeEventSource.instances[0].emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    FakeEventSource.instances[0].emit('live_sample', {
      type: 'live_sample',
      sample: { sequence: 1, received_at_ms: 1, game_timestamp_ms: 1, lap_number: 0, current_lap: 0, current_race_time: 0, x: 1, y: 0, z: 1, speed_mps: 10, throttle: 255, brake: 0, steer: 0, gear: 2 }
    });
    FakeEventSource.instances[0].emit('live_sample', {
      type: 'live_sample',
      sample: { sequence: 2, received_at_ms: 2, game_timestamp_ms: 2, lap_number: 0, current_lap: 0, current_race_time: 1, x: 4, y: 0, z: 5, speed_mps: 12, throttle: 255, brake: 0, steer: 0, gear: 2 }
    });

    await waitFor(() => expect(canvasContext.lineTo).toHaveBeenCalled());
  });

  it('does not draw non-race live samples while live follow is active', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2, { is_race_on: false }) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3) });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(canvas).toHaveAttribute('data-first-sequence', '1');
    expect(canvas).toHaveAttribute('data-last-sequence', '3');
  });

  it('starts a new live trace when a resumed race sample marks a lap split', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1, { lap_id: 'lap-a' }) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2, { lap_id: 'lap-a' }) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));

    source.emit('live_sample', {
      type: 'live_sample',
      sample: makeLiveSample(3, {
        lap_id: 'lap-b',
        lap_action: 'finalize_and_start',
        uncertainty: 'teleport'
      })
    });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '3');
    expect(canvas).toHaveAttribute('data-last-sequence', '3');
  });

  it('starts a fresh live trace when an impossible live jump arrives', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1, { x: 0, z: 0 }) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2, { x: 1, z: 1 }) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3, { x: 1500, z: 0, uncertainty: 'teleport' }) });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '3');
    expect(canvas).toHaveAttribute('data-last-sequence', '3');
  });

  it('resets stale live trace when live follow resumes after a teleport', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1, { x: 0, z: 0 }) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2, { x: 1, z: 1 }) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));

    await fireEvent.click(screen.getByRole('button', { name: 'Live follow' }));
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3, { x: 1500, z: 0 }) });
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(canvas).toHaveAttribute('data-sample-count', '2');

    await fireEvent.click(screen.getByRole('button', { name: 'Live follow' }));
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(4, { x: 1501, z: 0 }) });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '4');
    expect(canvas).toHaveAttribute('data-last-sequence', '4');
  });

  it('clears the live canvas on an auto race-on reset before drawing the new lap', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));

    source.emit('live_reset', { type: 'live_reset', reason: 'race_on_started' });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '0'));

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
  });

  it('filters legacy non-race zero packets missing race flags from recovered live history', async () => {
    const activeCapture = {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    const legacyPauseSample = makeLiveSample(3, {
      lap_number: 0,
      current_lap: 0,
      current_race_time: 0,
      x: 0,
      y: 0,
      z: 0,
      speed_mps: 0,
      throttle: 0,
      brake: 0,
      steer: 0,
      gear: 0
    });
    delete legacyPauseSample.is_race_on;
    stubApiFetch({
      status: { ...statusPayload, capture: activeCapture },
      capture: activeCapture,
      laps: [] as typeof defaultLaps,
      recent: { session_id: 'session-live', samples: [makeLiveSample(1), makeLiveSample(2), legacyPauseSample] }
    });

    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(canvas).toHaveAttribute('data-first-sequence', '1');
    expect(canvas).toHaveAttribute('data-last-sequence', '2');
  });

  it('ignores legacy non-race zero packets missing race flags during live follow', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));

    const legacyPauseSample = makeLiveSample(2, {
      lap_number: 0,
      current_lap: 0,
      current_race_time: 0,
      x: 0,
      y: 0,
      z: 0,
      speed_mps: 0,
      throttle: 0,
      brake: 0,
      steer: 0,
      gear: 0
    });
    delete legacyPauseSample.is_race_on;
    source.emit('live_sample', { type: 'live_sample', sample: legacyPauseSample });
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(canvas).toHaveAttribute('data-sample-count', '1');
    expect(canvas).toHaveAttribute('data-last-sequence', '1');
  });

  it('splits implausible live points immediately and keeps the fresh trace on non-race capture', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3, { x: 5000, z: 5000 }) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '3');
    expect(canvas).toHaveAttribute('data-last-sequence', '3');

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(4, { x: 5001, z: 5001 }) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
    expect(canvas).toHaveAttribute('data-first-sequence', '3');
    expect(canvas).toHaveAttribute('data-last-sequence', '4');

    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      packet_receipt: {
        ...capturePayload.packet_receipt,
        state: 'receiving',
        has_received_packets: true,
        packets_observed: 3,
        last_timestamp_ms: 3,
        last_is_race_on: false,
        last_packet_type: 'non_race'
      },
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(canvas).toHaveAttribute('data-sample-count', '2');
    expect(canvas).toHaveAttribute('data-first-sequence', '3');
    expect(canvas).toHaveAttribute('data-last-sequence', '4');
  });

  it('keeps the last race point on non-race capture when the pause edge is continuous', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));

    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      packet_receipt: {
        ...capturePayload.packet_receipt,
        state: 'receiving',
        has_received_packets: true,
        packets_observed: 3,
        last_timestamp_ms: 3,
        last_is_race_on: false,
        last_packet_type: 'non_race'
      },
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(canvas).toHaveAttribute('data-sample-count', '2');
    expect(canvas).toHaveAttribute('data-last-sequence', '2');
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3, { x: 2.2, z: 2.2 }) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));
    expect(canvas).toHaveAttribute('data-last-sequence', '3');
  });

  it('keeps the whole active live lap in the browser sample history', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    for (let sequence = 1; sequence <= 601; sequence += 1) {
      source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(sequence) });
    }

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '601'));
    expect(canvas).toHaveAttribute('data-first-sequence', '1');
    expect(canvas).toHaveAttribute('data-last-sequence', '601');
  });

  it('caps live browser sample history during long recording runs', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    for (let sequence = 1; sequence <= 2005; sequence += 1) {
      source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(sequence) });
    }

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2000'));
    expect(canvas).toHaveAttribute('data-first-sequence', '6');
    expect(canvas).toHaveAttribute('data-last-sequence', '2005');
  });

  it('starts a fresh live sample history when a lap finalizes during recording', async () => {
    stubApiFetch({ laps: [] as typeof defaultLaps, recent: { session_id: 'session-live', samples: [] } });
    renderApp();
    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(1) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(2) });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(3) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));

    source.emit('lap_finalized', { type: 'lap_finalized', lap_id: 'completed-lap', boundary_confidence: 'game_field' });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '0'));

    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(4) });
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '4');
    expect(canvas).toHaveAttribute('data-last-sequence', '4');
  });

  it('reconnects after SSE error and recovers status plus lap drilldown state first', async () => {
    let statusCalls = 0;
    let recentCalls = 0;
    const defaultHandler = createDefaultFetchHandler();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      if (url === '/api/status') {
        statusCalls += 1;
        return jsonResponse(statusCalls === 1 ? statusPayload : receivingStatusPayload);
      }
      if (url === '/api/live/recent?limit=200') {
        recentCalls += 1;
        return jsonResponse({ session_id: recentCalls === 1 ? 'session-live' : 'latest-session', samples: recoveredSamples });
      }
      return defaultHandler(url, init);
    });
    vi.stubGlobal('fetch', fetchMock);
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    fetchMock.mockClear();
    vi.useFakeTimers();

    const source = FakeEventSource.instances[0];
    source.onerror?.();
    await Promise.resolve();

    expect(source.closed).toBe(true);
    expect(within(getToastStack()).getAllByText('Telemetry stream disconnected')).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(500);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2));

    const recoveryCalls = fetchMock.mock.calls.map(([input]) => requestUrl(input as RequestInfo | URL));
    const recoveryCoreCalls = recoveryCalls.filter((url) => {
      if (['/api/status', '/api/capture', '/api/live/recent?limit=200', '/api/sessions/active', '/api/tracks/profiles', '/api/sessions/session-b/laps'].includes(url)) {
        return true;
      }
      return sessionPageCallMatches(url, { page: '1', page_size: '100' });
    });
    expect(recoveryCoreCalls).toEqual([
      '/api/status',
      '/api/capture',
      '/api/live/recent?limit=200',
      '/api/sessions/active',
      '/api/sessions?page=1&page_size=100',
      '/api/tracks/profiles',
      '/api/sessions/session-b/laps'
    ]);
    expect(screen.getByLabelText(/Listener receiving: receiving replay packets/i)).toBeInTheDocument();
    expect(within(getToastStack()).queryByText('Telemetry stream disconnected')).not.toBeInTheDocument();
  });

  it('does not add duplicate sticky disconnect toasts during repeated recovery failures', async () => {
    const fetchMock = stubApiFetch();
    renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    fetchMock.mockImplementation(async () => {
      throw new Error('offline');
    });
    vi.useFakeTimers();

    FakeEventSource.instances[0].onerror?.();
    await Promise.resolve();
    expect(within(getToastStack()).getAllByText('Telemetry stream disconnected')).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(500);
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(500);
    await Promise.resolve();

    expect(within(getToastStack()).getAllByText('Telemetry stream disconnected')).toHaveLength(1);
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('closes the telemetry event stream on unmount', async () => {
    const { unmount } = renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const source = FakeEventSource.instances[0];
    unmount();

    expect(source.closed).toBe(true);
    expect(source.closeCalls).toBe(1);
  });

  it('does not reconnect the event stream after unmount', async () => {
    const fetchMock = stubApiFetch();
    const { unmount } = renderApp();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    fetchMock.mockClear();
    vi.useFakeTimers();

    const source = FakeEventSource.instances[0];
    source.onerror?.();
    unmount();
    await vi.advanceTimersByTimeAsync(500);

    expect(source.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not connect the event stream if status resolves after unmount', async () => {
    const pendingResponses: Array<(response: Response) => void> = [];
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
      pendingResponses.push(resolve);
    })));

    const { unmount } = renderApp();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(7));

    unmount();
    pendingResponses[0](jsonResponse(statusPayload));
    pendingResponses[1](jsonResponse(capturePayload));
    pendingResponses[2](jsonResponse({ session_id: 'session-live', samples: recoveredSamples }));
    pendingResponses[3](jsonResponse({ session: defaultSessions[1] }));
    pendingResponses[4](jsonResponse({ sessions: defaultSessions, page: 1, page_size: 100, total: defaultSessions.length, total_pages: 1 }));
    pendingResponses[5](jsonResponse({ profiles: defaultTrackProfiles }));
    pendingResponses[6](jsonResponse(defaultWorldMapStatus));
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('renders main and overlay icon buttons as local svg icons instead of Material Symbols text', async () => {
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });

    const expand = screen.getByRole('button', { name: /expand menu/i });
    expect(expand.querySelector('svg')).not.toBeNull();
    expect(expand).toHaveAttribute('title', 'Expand menu');
    expect(expand).not.toHaveTextContent('menu');

    const speed = screen.getByRole('button', { name: 'Speed' });
    expect(speed.querySelector('svg')).not.toBeNull();
    expect(speed).toHaveAttribute('title', 'Show speed overlay');
    expect(speed).not.toHaveTextContent('speed');

    expect(document.querySelector('.material-symbols-rounded')).toBeNull();
    expect(document.querySelector('.material-symbols')).toBeNull();
  });

  it('switches the canvas from a reviewed lap to live telemetry when recording becomes active', async () => {
    renderApp();

    await screen.findByRole('button', { name: /^Lap 2/i });
    const canvas = document.querySelector('canvas');
    expect(canvas).toHaveAttribute('data-selected-start', '10');
    expect(canvas).toHaveAttribute('data-sample-count', '3');

    const source = FakeEventSource.instances[0];
    source.emit('live_sample', { sample: recoveredSamples[0] });
    source.emit('capture', {
      ...capturePayload,
      mode: 'auto',
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    });
    await waitFor(() => expect(within(getToastStack()).getByText(/Live recording view enabled/i)).toBeInTheDocument());
    expect(canvas).toHaveAttribute('data-sample-count', '0');
    source.emit('live_sample', { sample: recoveredSamples[1] });
    source.emit('live_sample', {
      sample: { sequence: 3, received_at_ms: 3, game_timestamp_ms: 3, lap_number: 0, current_lap: 0, current_race_time: 2, x: 8, y: 0, z: 9, speed_mps: 14, throttle: 255, brake: 0, steer: 0, gear: 2 }
    });

    const timeline = screen.getByRole('region', { name: /Review timeline/i });
    expect(within(timeline).queryByRole('slider', { name: 'Section start sequence' })).toBeNull();
    expect(within(timeline).queryByRole('button', { name: 'Reset timeline to full lap' })).toBeNull();
    expect(within(timeline).getByText(/Recording… select a saved lap to review its timeline/i)).toBeInTheDocument();
    expect(canvas).toHaveAttribute('data-selected-start', '');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '2'));
  });

  it('switches from a reviewed lap to the live route when race samples resume and live follow is running', async () => {
    const activeCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      capture: activeCapture,
      status: { ...statusPayload, capture: activeCapture },
      recent: { session_id: 'session-live', samples: [] }
    });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '0'));
    const lapButton = await screen.findByRole('button', { name: /^Lap 2/i });
    await fireEvent.click(lapButton);
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));
    expect(lapButton).toHaveAttribute('aria-pressed', 'true');

    const source = FakeEventSource.instances[0];
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(101, { lap_id: 'live-lap' }) });

    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '101');
    expect(canvas).toHaveAttribute('data-last-sequence', '101');
    expect(lapButton).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps a reviewed lap selected when race packets resume while live follow is paused', async () => {
    const activeCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      capture: activeCapture,
      status: { ...statusPayload, capture: activeCapture },
      recent: { session_id: 'session-live', samples: [] }
    });
    renderApp();

    const canvas = await screen.findByLabelText('Live telemetry path');
    const lapButton = await screen.findByRole('button', { name: /^Lap 2/i });
    await fireEvent.click(lapButton);
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '3'));

    await fireEvent.click(screen.getByRole('button', { name: 'Live follow' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Live follow' })).toHaveAttribute('aria-pressed', 'true'));

    const source = FakeEventSource.instances[0];
    source.emit('capture', {
      ...activeCapture,
      packet_receipt: {
        ...capturePayload.packet_receipt,
        state: 'receiving',
        has_received_packets: true,
        packets_observed: 1,
        last_timestamp_ms: 101,
        last_is_race_on: true,
        last_packet_type: 'race'
      }
    });
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(101, { lap_id: 'live-lap' }) });
    await new Promise((resolve) => window.setTimeout(resolve, 0));

    expect(canvas).toHaveAttribute('data-sample-count', '3');
    expect(canvas).toHaveAttribute('data-first-sequence', '10');
    expect(canvas).toHaveAttribute('data-last-sequence', '12');
    expect(lapButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('switches from a reviewed lap dashboard to the live route when race samples resume and live follow is running', async () => {
    const activeCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      capture: activeCapture,
      status: { ...statusPayload, capture: activeCapture },
      recent: { session_id: 'session-live', samples: [] }
    });
    renderApp();

    const lapButton = await screen.findByRole('button', { name: /^Lap 2/i });
    await fireEvent.click(lapButton);
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-sample-count', '3'));
    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));
    expect(screen.getByRole('region', { name: 'Telemetry dashboard canvas' })).toBeInTheDocument();

    const source = FakeEventSource.instances[0];
    source.emit('live_sample', { type: 'live_sample', sample: makeLiveSample(102, { lap_id: 'live-lap' }) });

    const canvas = await screen.findByLabelText('Live telemetry path');
    await waitFor(() => expect(canvas).toHaveAttribute('data-sample-count', '1'));
    expect(canvas).toHaveAttribute('data-first-sequence', '102');
    expect(screen.queryByRole('region', { name: 'Telemetry dashboard canvas' })).not.toBeInTheDocument();
  });

  it('renders one disabled review timeline until a saved lap is selected for review', async () => {
    stubApiFetch({ laps: [] });
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    const [timeline] = screen.getAllByRole('region', { name: /Review timeline/i });
    expect(timeline).toBeInTheDocument();
    expect(screen.getAllByRole('region', { name: /Review timeline/i })).toHaveLength(1);
    expect(within(timeline).queryByRole('slider', { name: 'Section start sequence' })).toBeNull();
    expect(within(timeline).queryByRole('button', { name: 'Reset timeline to full lap' })).toBeNull();
    expect(screen.getByText(/Timeline available after a saved lap or session is selected/i)).toBeInTheDocument();
  });

  it('switches between route visualiser and telemetry dashboard modes', async () => {
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    expect(screen.getByLabelText('Live telemetry path')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Speed' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Review timeline/i })).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));

    expect(screen.getByRole('region', { name: 'Telemetry dashboard canvas' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Dashboard playback' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose dashboard widgets' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Live telemetry path')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Speed' })).toBeNull();
    expect(screen.queryByRole('region', { name: /Review timeline/i })).toBeNull();

    await fireEvent.click(screen.getByRole('button', { name: 'Route visualiser mode' }));

    expect(screen.getByLabelText('Live telemetry path')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Speed' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Review timeline/i })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Telemetry dashboard canvas' })).toBeNull();
  });

  it('renders live dashboard telemetry and live car details while recording is active', async () => {
    const activeCapture = {
      ...capturePayload,
      phase: 'recording',
      recording: { ...capturePayload.recording, active: true, phase: 'recording', mode: 'auto' }
    };
    stubApiFetch({
      laps: [],
      capture: activeCapture,
      status: { ...statusPayload, capture: activeCapture },
      recent: {
        session_id: 'session-live',
        samples: [
          makeLiveSample(8, {
            speed_mps: 44.704,
            current_rpm: 7250,
            engine_max_rpm: 9000,
            power_w: 372850,
            torque_nm: 500,
            boost_bar: 1.23,
            fuel: 0.625
          })
        ],
        car: defaultCarInfo
      }
    });
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    await waitFor(() => expect(screen.getByLabelText('Live telemetry path')).toHaveAttribute('data-sample-count', '1'));
    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));

    const dashboard = screen.getByRole('region', { name: 'Telemetry dashboard canvas' });
    await waitFor(() => expect(within(dashboard).getByRole('region', { name: 'Tach / Speed / Gear' })).toHaveTextContent('100 mph'));
    const carDetails = within(dashboard).getByRole('region', { name: 'Car details' });
    expect(carDetails).toHaveTextContent('Mazda Furai');
    expect(carDetails).toHaveTextContent('Extreme Track Toys');
    expect(carDetails).not.toHaveTextContent('Fuel');
    expect(screen.getByRole('region', { name: 'Dashboard playback' })).toHaveTextContent('Live dashboard');
  });

  it('scrubs the selected-lap dashboard playback and keeps selected-lap car details available', async () => {
    renderApp();

    await screen.findByRole('button', { name: /^Lap 2/i });
    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));

    const playback = screen.getByRole('region', { name: 'Dashboard playback' });
    expect(playback).toHaveTextContent('Selected lap playback');
    expect(playback).toHaveTextContent('Sample 1 of 3');
    expect(screen.getByRole('region', { name: 'Car details' })).toHaveTextContent('Mazda Furai');

    await fireEvent.input(within(playback).getByRole('slider', { name: 'Scrub selected lap dashboard playback' }), { target: { value: '2' } });

    await waitFor(() => expect(playback).toHaveTextContent('Sample 3 of 3'));
    expect(screen.getByRole('region', { name: 'Tach / Speed / Gear' })).toHaveTextContent('102 mph');
  });

  it('plays selected-lap dashboard data at the recorded sample speed', async () => {
    const frameCallbacks: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => {
      frameCallbacks.push(callback);
      return frameCallbacks.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
    renderApp();

    await screen.findByRole('button', { name: /^Lap 2/i });
    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Play dashboard playback' }));

    expect(frameCallbacks.length).toBeGreaterThan(0);
    frameCallbacks.shift()?.(0);
    await Promise.resolve();
    frameCallbacks.shift()?.(2);

    const playback = screen.getByRole('region', { name: 'Dashboard playback' });
    await waitFor(() => expect(playback).toHaveTextContent('Sample 3 of 3'));
    expect(screen.getByRole('button', { name: 'Play dashboard playback' })).toBeInTheDocument();
  });

  it('lets dashboard widget visibility hide every widget and restore the default grid', async () => {
    renderApp();

    await screen.findByRole('heading', { name: /Forza Telemetry Tracker/i });
    await fireEvent.click(screen.getByRole('button', { name: 'Telemetry dashboard mode' }));
    await fireEvent.click(screen.getByRole('button', { name: 'Choose dashboard widgets' }));

    for (const widget of DASHBOARD_WIDGETS) {
      const labelPattern = new RegExp(widget.label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
      await fireEvent.click(screen.getByRole('button', { name: labelPattern }));
    }

    expect(screen.getByText('No dashboard widgets are visible')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Show all widgets' }));

    expect(screen.getByTestId('dashboard-widget-grid')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Tach / Speed / Gear' })).toBeInTheDocument();
  });

});
