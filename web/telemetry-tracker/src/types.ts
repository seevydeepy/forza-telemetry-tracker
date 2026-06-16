export type ListenerState = 'starting' | 'waiting' | 'receiving' | 'recording' | 'error';
export type ToastLevel = 'info' | 'success' | 'warning' | 'error';
export type CaptureMode = 'auto' | 'manual';
export type CapturePhase = 'idle' | 'receiving_not_recording' | 'recording';
export type PacketRaceState = 'race' | 'non_race' | 'unknown';
export type LapHistoryView = 'laps' | 'session';
export type CanvasMode = 'route' | 'dashboard';
export type DashboardPlaybackSource = 'live' | 'lap';
export type DashboardWidgetId =
  | 'tachSpeedGear'
  | 'inputsSteering'
  | 'tires'
  | 'suspensionAttitude'
  | 'accelerometer'
  | 'lapTiming'
  | 'miniRoute'
  | 'fuelRaceInfo'
  | 'carDetails';
export type OverlayId = 'issues' | 'speed' | 'inputs' | 'grip' | 'temperature' | 'suspension' | 'rpm';
export type UnitSystem = 'imperial' | 'metric';
export type IssueSeverity = 'info' | 'warning' | 'critical';
export type ReferenceScope = 'track' | 'track_car' | 'track_car_build';
export type ReferenceSource = 'session_best';
export type WorldMapSeason = 'spring' | 'summer' | 'autumn' | 'winter';
export type WorldMapStatusCode =
  | 'disabled'
  | 'ready'
  | 'cache_missing'
  | 'cache_stale'
  | 'source_missing'
  | 'converter_missing'
  | 'error';

export interface SequenceRange {
  startSequence: number;
  endSequence: number;
}

export interface ListenerStatus {
  state: ListenerState;
  udp_host: string;
  udp_port: number;
  packets_received: number;
  packets_recorded?: number;
  message: string;
}

export interface CapturePacketReceipt {
  state: 'waiting' | 'receiving';
  has_received_packets: boolean;
  packets_observed: number;
  last_timestamp_ms: number | null;
  last_is_race_on?: boolean | null;
  last_packet_type?: PacketRaceState;
}

export interface CaptureRecordingStatus {
  active: boolean;
  phase: CapturePhase;
  mode: CaptureMode;
  total_live_packets_recorded_excluding_prebuffer: number;
}

export interface CapturePrebufferStatus {
  capacity: number;
  size: number;
}

export interface CaptureAutoDetectionStatus {
  last_signals: Record<string, boolean>;
  last_reason: string;
}

export interface VisualiserSettings {
  capture_mode: string;
  udp_host: string;
  udp_port: number;
  preferred_overlay: OverlayId | string;
  unit_system: UnitSystem | string;
}

export interface VisualiserSettingsUpdate {
  unit_system?: UnitSystem;
  preferred_overlay?: OverlayId;
}

export interface CaptureStatus {
  mode: CaptureMode;
  phase: CapturePhase;
  packet_receipt: CapturePacketReceipt;
  recording: CaptureRecordingStatus;
  prebuffer: CapturePrebufferStatus;
  auto_detection: CaptureAutoDetectionStatus;
  listener?: ListenerStatus;
  settings?: VisualiserSettings;
}

export interface StatusPayload {
  listener: ListenerStatus;
  settings: VisualiserSettings;
  capture: CaptureStatus;
}

export interface DiagnosticsRowCounts {
  sessions: number;
  laps: number;
  packets: number;
  issue_markers: number;
  track_profiles: number;
  world_map_tile_sets: number;
}

export interface WorldMapSettings {
  fh6_media_root: string | null;
  world_map_enabled: boolean;
  world_map_season: WorldMapSeason;
}

export interface WorldMapManifestTile {
  z: number;
  x: number;
  y: number;
  path: string;
}

export interface WorldMapTileManifest {
  game: string;
  map: string;
  season?: WorldMapSeason | string;
  format: string;
  tileSize: number;
  minZoom: number;
  maxZoom: number;
  worldOriginX: number;
  worldOriginZ: number;
  worldSize: number;
  tileUrlTemplate?: string;
  tileCoordinateSystem?: string;
  tiles: WorldMapManifestTile[];
}

export interface WorldMapTileSet {
  id: string;
  game: string;
  map_name: string;
  season: WorldMapSeason;
  source_zip_path: string;
  source_zip_mtime_ms: number;
  source_zip_size_bytes: number;
  cache_dir: string;
  tile_format: string;
  tile_size: number;
  min_zoom: number;
  max_zoom: number;
  world_origin_x: number;
  world_origin_z: number;
  world_size: number;
  status: 'missing' | 'building' | 'ready' | 'error';
  error_message: string | null;
  last_built_at_ms?: number | null;
  updated_at_ms: number;
  manifest: WorldMapTileManifest;
  tile_url_template: string;
}

export interface WorldMapStatus {
  status: WorldMapStatusCode;
  settings: WorldMapSettings;
  source: {
    available: boolean;
    path: string | null;
    season: WorldMapSeason;
  };
  converter: {
    available: boolean;
    path: string | null;
  };
  tile_set: WorldMapTileSet | null;
  error_message?: string;
}

export interface DiagnosticsPayload {
  database_path: string;
  database_size_bytes: number;
  wal_size_bytes: number;
  row_counts: DiagnosticsRowCounts;
  world_map: {
    settings: WorldMapSettings;
    tile_set_count: number;
    ready_tile_set_id: string | null;
  };
  listener_status: (ListenerStatus & Record<string, unknown>) | null;
  capture_status: (CaptureStatus & Record<string, unknown>) | null;
  recent_errors: unknown[];
  app_version: string;
}

export interface TelemetryDeleteResponse {
  deleted: boolean;
  deleted_counts: Record<string, number>;
  row_counts: DiagnosticsRowCounts;
}

export interface LiveSample {
  lap_id?: string | null;
  sequence: number;
  received_at_ms: number;
  game_timestamp_ms: number;
  is_race_on?: boolean;
  lap_number: number;
  current_lap: number;
  current_race_time: number;
  x: number;
  y: number;
  z: number;
  speed_mps: number;
  throttle: number;
  brake: number;
  steer: number;
  gear: number;
  combined_slip?: number | null;
  rear_combined_slip?: number | null;
  tire_temp_front_left?: number | null;
  tire_temp_front_right?: number | null;
  tire_temp_rear_left?: number | null;
  tire_temp_rear_right?: number | null;
  suspension_travel_front_left?: number | null;
  suspension_travel_front_right?: number | null;
  suspension_travel_rear_left?: number | null;
  suspension_travel_rear_right?: number | null;
  current_rpm?: number | null;
  engine_max_rpm?: number | null;
  acceleration_x?: number | null;
  acceleration_y?: number | null;
  acceleration_z?: number | null;
  velocity_x?: number | null;
  velocity_y?: number | null;
  velocity_z?: number | null;
  angular_velocity_x?: number | null;
  angular_velocity_y?: number | null;
  angular_velocity_z?: number | null;
  yaw?: number | null;
  pitch?: number | null;
  roll?: number | null;
  smashable_vel_diff?: number | null;
  smashable_mass?: number | null;
  power_w?: number | null;
  torque_nm?: number | null;
  boost_bar?: number | null;
  engine_idle_rpm?: number | null;
  fuel?: number | null;
  distance_traveled_m?: number | null;
  best_lap?: number | null;
  last_lap?: number | null;
  race_position?: number | null;
  clutch?: number | null;
  handbrake?: number | null;
  normalized_driving_line?: number | null;
  normalized_ai_brake_difference?: number | null;
  tire_slip_ratio_front_left?: number | null;
  tire_slip_ratio_front_right?: number | null;
  tire_slip_ratio_rear_left?: number | null;
  tire_slip_ratio_rear_right?: number | null;
  tire_slip_angle_front_left?: number | null;
  tire_slip_angle_front_right?: number | null;
  tire_slip_angle_rear_left?: number | null;
  tire_slip_angle_rear_right?: number | null;
  tire_combined_slip_front_left?: number | null;
  tire_combined_slip_front_right?: number | null;
  tire_combined_slip_rear_left?: number | null;
  tire_combined_slip_rear_right?: number | null;
  wheel_rotation_speed_front_left?: number | null;
  wheel_rotation_speed_front_right?: number | null;
  wheel_rotation_speed_rear_left?: number | null;
  wheel_rotation_speed_rear_right?: number | null;
  wheel_on_rumble_strip_front_left?: number | null;
  wheel_on_rumble_strip_front_right?: number | null;
  wheel_on_rumble_strip_rear_left?: number | null;
  wheel_on_rumble_strip_rear_right?: number | null;
  wheel_in_puddle_depth_front_left?: number | null;
  wheel_in_puddle_depth_front_right?: number | null;
  wheel_in_puddle_depth_rear_left?: number | null;
  wheel_in_puddle_depth_rear_right?: number | null;
  surface_rumble_front_left?: number | null;
  surface_rumble_front_right?: number | null;
  surface_rumble_rear_left?: number | null;
  surface_rumble_rear_right?: number | null;
  suspension_travel_meters_front_left?: number | null;
  suspension_travel_meters_front_right?: number | null;
  suspension_travel_meters_rear_left?: number | null;
  suspension_travel_meters_rear_right?: number | null;
  boundary_confidence?: string | null;
  session_action?: string | null;
  lap_action?: string | null;
  uncertainty?: string | null;
}

export interface RecentLivePayload {
  session_id: string | null;
  samples: LiveSample[];
  car?: CarInfo | null;
}

export interface RawTelemetryImportResponse {
  session_id: string | null;
  session_ids: string[];
  lap_ids: string[];
  packet_count: number;
  samples: LiveSample[];
}

export type RawTelemetryImportJobStatus = 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled';

export interface RawTelemetryImportJobError {
  file: string | null;
  message: string;
}

export interface RawTelemetryImportJob {
  id: string;
  label: string;
  source_type: 'file' | 'files' | 'folder' | string;
  status: RawTelemetryImportJobStatus;
  status_text: string;
  progress: number;
  created_at_ms: number;
  started_at_ms: number | null;
  completed_at_ms: number | null;
  total_files: number;
  processed_files: number;
  failed_files: number;
  total_bytes: number;
  packet_count: number;
  session_ids: string[];
  lap_ids: string[];
  current_file: string | null;
  current_file_index: number | null;
  current_file_packets: number;
  current_file_packets_processed: number;
  errors: RawTelemetryImportJobError[];
  error_count: number;
  can_cancel: boolean;
}

export interface RawTelemetryImportJobResponse {
  job: RawTelemetryImportJob;
}

export interface RawTelemetryImportJobsResponse {
  jobs: RawTelemetryImportJob[];
}

export interface RawTelemetryImportPathJobRequest {
  file_paths?: string[];
  folder_path?: string;
  label?: string;
  source_type?: 'file' | 'files' | 'folder';
}

export type TelemetryExportKind = 'raw_binary' | 'raw_csv' | 'curated_csv';
export type TelemetryExportJobStatus = 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled';

export interface TelemetryExportEstimate {
  raw_packet_count: number;
  raw_byte_count: number;
  curated_sample_count: number;
  session_count: number;
  lap_count: number;
}

export interface TelemetryExportDefaults {
  output_dir: string;
  filename_prefix: string;
  estimate: TelemetryExportEstimate;
}

export interface TelemetryExportOutputFile {
  path: string;
  filename: string;
  size_bytes: number;
}

export interface TelemetryExportJob {
  id: string;
  kind: TelemetryExportKind;
  label: string;
  status: TelemetryExportJobStatus;
  status_text: string;
  progress: number;
  output_dir: string;
  filename_prefix: string | null;
  output_files: TelemetryExportOutputFile[];
  total_size_bytes: number;
  row_count: number;
  created_at_ms: number;
  started_at_ms: number | null;
  completed_at_ms: number | null;
  duration_ms: number | null;
  error: string | null;
  can_cancel: boolean;
}

export interface TelemetryExportJobRequest {
  kind: TelemetryExportKind;
  output_dir: string;
  filename_prefix?: string;
}

export interface TelemetryExportJobResponse {
  job: TelemetryExportJob;
}

export interface TelemetryExportJobsResponse {
  jobs: TelemetryExportJob[];
}

export interface IssueMarker {
  id: string;
  session_id: string;
  lap_id: string | null;
  start_sequence: number;
  end_sequence: number;
  metric: string;
  severity: IssueSeverity;
  reason: string;
  ruleset_version: number;
  confidence: number;
  anchor_sequence: number | null;
  issue_kind: string | null;
  actual_value: number | null;
  threshold_value: number | null;
  threshold_operator: 'gte' | 'lte' | null;
  value_label: string | null;
  value_unit: string | null;
}

export interface AnalysisSummary {
  packet_count: number;
  top_speed_mps: number;
  average_speed_mps: number;
  peak_combined_slip: number;
  limiter_samples: number;
  bottoming_events: number;
  start_sequence: number;
  end_sequence: number;
  lap_time_ms?: number | null;
  lap_duration_ms?: number | null;
}

export interface LapSummary {
  id: string;
  user_id?: string;
  session_id: string;
  session_label: string;
  lap_number: number | null;
  status: string;
  started_at_ms: number;
  ended_at_ms: number | null;
  ended_reason: string | null;
  boundary_confidence: string | null;
  lap_time_ms?: number | null;
  track_profile_id?: string | null;
  track_profile_name?: string | null;
  track_profile_layout?: string | null;
}

export interface SessionSummary {
  id: string;
  user_id: string;
  label: string;
  status: string;
  started_at_ms: number;
  ended_at_ms: number | null;
  ended_reason: string | null;
  last_active_at_ms: number;
  lap_count: number;
  car_identity_key?: string | null;
  car_ordinal?: number | null;
  car_name?: string | null;
  car_class_id?: number | null;
  car_class_label?: string | null;
  car_performance_index?: number | null;
  drivetrain_id?: number | null;
  drivetrain_label?: string | null;
  label_generated?: number | boolean | null;
  auto_created_reason?: string | null;
  completed_lap_count?: number;
  best_lap_time_ms?: number | null;
  average_lap_time_ms?: number | null;
  total_lap_time_ms?: number | null;
}

export interface StatsFavourite {
  value: string;
  detail?: string | null;
  lap_count: number;
  session_count: number;
  last_used_at_ms?: number | null;
}

export interface StatsSummary {
  laps_recorded: number;
  sessions_created: number;
  tracks_driven: number;
  cars_driven: number;
  max_speed_mps: number | null;
  favourite_car: StatsFavourite | null;
  favourite_track: StatsFavourite | null;
  favourite_pi_class: StatsFavourite | null;
  favoured_drive: StatsFavourite | null;
  time_spent_racing_ms: number;
}

export interface SessionPageResponse {
  sessions: SessionSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface SessionFilters {
  page?: number;
  pageSize?: number;
  name?: string;
  createdFrom?: number;
  createdTo?: number;
  lastActiveFrom?: number;
  lastActiveTo?: number;
  lapCountMin?: number;
  lapCountMax?: number;
  track?: string;
  car?: string;
}

export interface SessionResponse {
  session: SessionSummary | null;
}

export interface SessionDeleteResponse {
  deleted: boolean;
  session_id: string;
  session?: SessionSummary;
}

export interface TrackProfile {
  id: string;
  owner_user_id?: string | null;
  name: string;
  layout: string;
  source: string;
  confidence: string;
  shape_signature?: string | null;
  created_at_ms: number;
  updated_at_ms: number;
}

export interface TrackProfileCreateInput {
  name: string;
  layout: string;
  source?: string;
  confidence?: string;
}

export interface TrackProfileUpdateInput {
  name: string;
  layout: string;
}

export interface TrackProfileAssignInput {
  sessionId: string;
  lapId: string;
}

export interface TrackProfileMergeInput {
  keepProfileId: string;
  mergeProfileId: string;
}

export interface TrackProfileResponse {
  profile: TrackProfile;
}

export interface TrackProfileAssignmentResponse extends TrackProfileResponse {
  assignment: {
    profile_id: string;
    session_id: string;
    lap_id: string | null;
  };
}

export interface TrackMatchCandidate {
  track_profile_id?: string | null;
  assigned_track_profile_id?: string | null;
  track_profile_name?: string | null;
  track_profile_layout?: string | null;
  name?: string | null;
  layout?: string | null;
  score?: number | null;
  confidence?: string | number | null;
  [key: string]: unknown;
}

export interface TrackMatchResponse {
  lap_id: string;
  session_id?: string | null;
  matcher_version?: string;
  candidates: TrackMatchCandidate[];
  best_candidate?: TrackMatchCandidate | null;
  assignment?: {
    assigned?: boolean;
    reason?: string;
    track_profile_id?: string | null;
    track_key?: string | null;
    confidence?: number | null;
    [key: string]: unknown;
  };
}

export interface TrackProfileMergeResponse extends TrackProfileResponse {
  merged_profile_id: string;
}

export interface TrackAssetTransform {
  scale: number;
  rotate_deg: number;
  translate_x: number;
  translate_y: number;
}

export interface TrackAsset {
  id: string;
  track_profile_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  transform: TrackAssetTransform;
  created_at_ms: number;
  updated_at_ms: number;
  file_url: string;
}

export interface TrackAssetCreateInput {
  filename: string;
  sourcePath: string;
  mimeType: string;
  sizeBytes: number;
  transform?: TrackAssetTransform;
}

export interface TrackAssetResponse {
  asset: TrackAsset;
}

export interface TrackAssetsResponse {
  assets: TrackAsset[];
}

export interface TrackAssetDeleteResponse extends TrackAssetResponse {
  deleted: boolean;
  asset_id: string;
}


export interface CarInfoDetails {
  num_cylinders: number | null;
  car_group: number | null;
  car_group_label?: string | null;
  engine_max_rpm: number | null;
  peak_power_w: number | null;
  average_power_w: number | null;
  peak_torque_nm: number | null;
  average_torque_nm: number | null;
  peak_boost_bar: number | null;
  fuel: number | null;
}

export interface CarInfo {
  ordinal: number | null;
  name: string;
  display_name: string | null;
  model_short: string | null;
  year: number | null;
  class_id: number | null;
  class_label: string | null;
  performance_index: number | null;
  drivetrain_id: number | null;
  drivetrain_label: string | null;
  catalog_source: string;
  catalog: Record<string, unknown> | null;
  details: CarInfoDetails;
}

export interface LapSummaryResponse {
  lap_id: string;
  session_id: string;
  summary: AnalysisSummary;
  car?: CarInfo | null;
}

export interface LapMarkersResponse {
  lap_id: string;
  session_id: string;
  markers: IssueMarker[];
}

export interface LapSamplesResponse {
  lap_id: string;
  samples: LiveSample[];
}

export interface ReferenceLap {
  id?: string;
  lap_id: string;
  user_id?: string;
  session_id?: string;
  session_label?: string;
  lap_number?: number | null;
  status?: string;
  started_at_ms?: number | null;
  ended_at_ms?: number | null;
  ended_reason?: string | null;
  boundary_confidence?: string | null;
  summary?: AnalysisSummary | Record<string, unknown> | null;
  summary_created_at_ms?: number | null;
  summary_updated_at_ms?: number | null;
  stored_sample_count?: number | null;
  sample_count?: number | null;
  lap_time_ms?: number | null;
  lap_duration_ms?: number | null;
  scope?: ReferenceScope | string;
  context_key?: string;
  comparison_context_key?: string;
  source: ReferenceSource;
  pinned_at_ms?: number | null;
}

export interface ReferenceResponse {
  lap_id: string;
  scope: ReferenceScope;
  context_key: string;
  reference: ReferenceLap | null;
}

export interface GhostSample extends LiveSample {
  lap_progress?: number | null;
  elapsed_ms?: number | null;
}

export interface GhostResponse extends ReferenceResponse {
  samples: GhostSample[];
}

export interface DeltaPoint {
  sequence: number | null;
  lap_progress: number | null;
  current_elapsed_ms: number | null;
  reference_elapsed_ms: number | null;
  time_delta_ms: number | null;
  current_speed_mps: number | null;
  reference_speed_mps: number | null;
  speed_delta_mps: number | null;
}

export interface DeltaSummary {
  start_sequence: number | null;
  end_sequence: number | null;
  sample_count: number;
  current_sample_count: number;
  reference_sample_count: number;
  time_delta_ms: number | null;
  average_speed_delta_mps: number | null;
  max_gain_ms: number;
  max_loss_ms: number;
  points: DeltaPoint[];
}

export interface DeltaResponse extends ReferenceResponse {
  summary: DeltaSummary;
}

export interface RawPointResponse {
  session_id: string;
  sequence: number;
  point: Record<string, unknown>;
}

export interface ToastMessage {
  id: number;
  level: ToastLevel;
  message: string;
  sticky: boolean;
}

export interface AppAboutUpdates {
  supported: boolean;
  release_access: 'public';
}

export interface AppAboutPayload {
  name: string;
  version: string;
  release_date: string | null;
  git_sha: string | null;
  channel: string;
  repository: string;
  packaged: boolean;
  updates: AppAboutUpdates;
}

export type AppUpdateCheckStatus = 'update_available' | 'up_to_date' | 'unsupported' | 'error';

export interface AppUpdateCheckResponse {
  status: AppUpdateCheckStatus;
  current_version: string;
  latest_version: string | null;
  release_url: string | null;
  published_at: string | null;
  asset_name: string | null;
  message: string;
}
