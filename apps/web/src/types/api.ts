export type HospitalRole = "hospital_admin" | "doctor";

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}

export interface ApiError {
  status: number;
  code: string;
  message: string;
  requestId?: string;
}

export interface Actor {
  user_id: string;
  full_name: string;
  email: string;
  hospital_id: string;
  hospital_name: string;
  hospital_slug: string;
  role: HospitalRole;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  actor: Actor;
}

export interface Hospital {
  id: string;
  name: string;
  slug: string;
  role: HospitalRole;
  created_at: string;
}

export interface Doctor {
  user_id: string;
  full_name: string;
  email: string;
  created_at: string;
}

export interface DoctorListResponse {
  doctors: Doctor[];
}

export interface MriCase {
  id: string;
  case_reference: string;
  created_at: string;
}

export interface MriCaseListResponse {
  cases: MriCase[];
}

export interface MriJob {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface MriModelInfo {
  model_source: "local" | "global_fedavg_abc";
  model_name: string;
  modality_order: string[];
  architecture: Record<string, unknown>;
  expected_parameter_count: number;
  configured: boolean;
  integrity_status: string;
  checkpoint: {
    sha256: string;
    size_bytes: number;
  } | null;
  model_loaded: boolean;
}

export interface TumorStatistics {
  tumor_voxels: number;
  label_voxels: Record<string, number>;
  voxel_volume_mm3: number;
  tumor_volume_mm3: number;
  tumor_volume_ml: number;
}

export interface MriResult {
  job_id: string;
  status: "completed";
  model_sha256: string;
  model_source: "local" | "global_fedavg_abc";
  input_shape: number[];
  segmentation_shape: number[];
  labels: number[];
  statistics: TumorStatistics;
  inference_seconds: number;
  artifact_download_url: string;
}
