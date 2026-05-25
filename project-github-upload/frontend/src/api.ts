/**
 * 🔗 api.ts — 백엔드 API 연동 모듈
 *
 * FastAPI 백엔드의 API 엔드포인트를 호출하는 함수들을 모아 둔 모듈입니다.
 * Vite 프록시 설정을 통해 /api/* 요청은 자동으로 FastAPI(localhost:8000)로 전달됩니다.
 */

const API_BASE = "/api/v1";

/* ─────────────── 타입 정의 ─────────────── */

/** 백엔드 UploadResponse.courses[*] */
export interface BackendCourseItem {
  course_name: string;
  credits: number;
  grade: string;
  match_score: number | null;
}

/** POST /api/v1/upload 응답 */
export interface UploadResponse {
  success: boolean;
  message: string;
  total_images: number;
  courses: BackendCourseItem[];
  warnings: string[];
  raw_text: string | null;
  next_step: string;
  ocr_mode: string;
}

/** GET /api/v1/tracks 응답 — 학과 목록 */
export interface DeptSummary {
  dept_name: string;
  college_name: string;
  track_count: number;
  module_count: number;
  tracks: string[];
}

export interface CollegeGroup {
  college_name: string;
  dept_count: number;
  departments: DeptSummary[];
}

export interface TracksListResponse {
  success: boolean;
  total_departments: number;
  total_tracks: number;
  colleges: CollegeGroup[];
  dept_list: string[];
}

/** GET /api/v1/tracks/by-department 응답 */
export interface TrackDetailInfo {
  track_id: string;
  track_name: string;
  module_keys: string[];
  module_names: string[];
  rules_summary: string;
  rules: Record<string, unknown>[];
  total_courses: number;
  analysis_mode: string;
}

export interface ModuleInfo {
  module_key: string;
  module_name: string;
  courses: { course_name: string; credits: number; note?: string; has_note?: boolean }[];
}

export interface DeptTracksResponse {
  success: boolean;
  dept_name: string;
  college_name: string;
  page_ref: string;
  tracks: TrackDetailInfo[];
  modules: ModuleInfo[];
}

/** POST /api/v1/analyze 요청/응답 */
export interface AnalyzeCourseInput {
  course_name: string;
  credits: number;
  grade: string;
}

export interface CourseDetail {
  course_name: string;
  credits: number;
  note: string;
  has_note: boolean;
  note_type: string | null;
  note_label: string;
  warning_level: string | null;
}

export interface RuleResultInfo {
  rule_type: string;
  description: string;
  satisfied: boolean;
  current_value: number;
  required_value: number;
  shortage_count: number;
  shortage_credits: number;
  missing_courses: string[];
  remaining_courses: string[];
  taken_courses: string[];
  evaluation_status?: string;
  note?: string;
  manual_review_items?: string[];
  taken_course_details?: CourseDetail[];
  remaining_course_details?: CourseDetail[];
  missing_course_details?: CourseDetail[];
}

export interface TrackResultInfo {
  track_id: string;
  track_name: string;
  is_completed: boolean;
  completion_rate: number;
  total_rules: number;
  satisfied_rules: number;
  rule_results: RuleResultInfo[];
  missing_courses: string[];
  missing_candidate_count: number;
  additional_required_courses: number;
  taken_courses: string[];
  analysis_mode: string;
}

export interface RecommendedTrackInfo {
  rank: number;
  track_id: string;
  track_name: string;
  completion_rate: number;
  remaining_courses: number;
  additional_required_courses: number;
  missing_candidate_count: number;
  missing_courses: string[];
  reason: string;
}

export interface IncompleteTrackInfo {
  track_id: string;
  track_name: string;
  completion_rate: number;
  remaining_courses: number;
  additional_required_courses: number;
  missing_courses: string[];
  reason: string;
}

export interface ModuleResultInfo {
  module_key: string;
  module_name: string;
  is_completed: boolean;
  taken_count: number;
  total_courses: number;
  taken_credits: number;
  total_credits: number;
  completion_rate: number;
  requirement_label: string;
  taken_courses: string[];
  not_taken_courses: string[];
}

export interface AnalyzeResponse {
  success: boolean;
  dept_name: string;
  total_courses_submitted: number;
  total_credits: number;
  submitted_credits: number;
  recognized_credits: number;
  excluded_credits: number;
  track_results: TrackResultInfo[];
  completed_tracks: string[];
  recommended_tracks: RecommendedTrackInfo[];
  incomplete_tracks: IncompleteTrackInfo[];
  module_stats: Record<string, unknown>;
  module_results: ModuleResultInfo[];
  filtered_info: Record<string, unknown>;
}

/** GET /api/v1/scenarios 응답 */
export interface ScenariosResponse {
  success: boolean;
  scenarios: { key: string; label: string; description: string }[];
  message: string;
}

/** GET /api/v1/health 응답 */
export interface HealthResponse {
  status: string;
  message: string;
  version: string;
  ocr_mode: string;
  data_source: string;
  db?: Record<string, unknown>;
}

/* ─────────────── API 호출 함수 ─────────────── */

async function handleApiError(res: Response, defaultMessage: string): Promise<never> {
  const errBody = await res.json().catch(() => null);
  let errMsg = errBody?.message || defaultMessage;
  if (errBody?.details && Array.isArray(errBody.details) && errBody.details.length > 0) {
    errMsg += "\n\n[상세 내용]\n- " + errBody.details.join("\n- ");
  }
  throw new Error(errMsg);
}

/** 서버 상태 확인 */
export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) await handleApiError(res, `Health check failed: ${res.status}`);
  return res.json();
}

/** 학과 목록 조회 */
export async function fetchDeptList(): Promise<TracksListResponse> {
  const res = await fetch(`${API_BASE}/tracks`);
  if (!res.ok) await handleApiError(res, `트랙 목록 조회 실패: ${res.status}`);
  return res.json();
}

/** 특정 학과 트랙 상세 조회 */
export async function fetchDeptTracks(deptName: string): Promise<DeptTracksResponse> {
  const res = await fetch(`${API_BASE}/tracks/by-department?dept_name=${encodeURIComponent(deptName)}`);
  if (!res.ok) await handleApiError(res, `학과 트랙 조회 실패: ${res.status}`);
  return res.json();
}

/** Mock 시나리오 목록 조회 */
export async function fetchScenarios(): Promise<ScenariosResponse> {
  const res = await fetch(`${API_BASE}/scenarios`);
  if (!res.ok) await handleApiError(res, `시나리오 목록 조회 실패: ${res.status}`);
  return res.json();
}

/** 이미지 업로드 + OCR */
export async function uploadImages(
  files: File[],
  scenario?: string,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  if (scenario) {
    formData.append("scenario", scenario);
  }

  // OCR은 이미지 크기에 따라 시간이 걸릴 수 있어 120초 타임아웃 설정
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);
  const handleExternalAbort = () => controller.abort();

  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", handleExternalAbort, { once: true });
  }

  try {
    const res = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", handleExternalAbort);

    if (!res.ok) {
      await handleApiError(res, `업로드 실패: ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", handleExternalAbort);
    if (e.name === "AbortError") {
      if (signal?.aborted) {
        throw e;
      }
      throw new Error("OCR 처리 시간이 초과되었습니다 (120초). 이미지 크기를 줄이거나 다시 시도해주세요.");
    }
    throw e;
  }
}

/** 트랙 분석 요청 */
export async function analyzeTrack(
  deptName: string,
  courses: AnalyzeCourseInput[],
): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dept_name: deptName,
      courses,
    }),
  });
  if (!res.ok) {
    await handleApiError(res, `분석 실패: ${res.status}`);
  }
  return res.json();
}
