import { API_BASE_URL } from './env';
import { TIMEOUTS } from './constants';
import type {
  AskRequest,
  AskResponse,
  CompareRequest,
  CompareResponse,
  ComparisonCountResponse,
  ChunkResponse,
  HealthResponse,
  LeaseMetadata,
  MetadataRefreshResponse,
  UploadResponse,
} from '@leasora/shared-types';

export type ApiMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

/**
 * Standard error envelope returned by FastAPI. The backend serves
 * `{"detail": "...", "error_code": "...", "status": N}` for all error
 * responses; we type it explicitly here so callers can't accidentally
 * fall through `String(null) ⇒ 'null'`.
 */
export interface ApiError {
  detail: string;
  error_code: string;
  status: number;
}

/**
 * Discriminated-ish response wrapper. Exactly one of `data`/`error` is
 * populated for any given HTTP response (the other is `undefined`).
 * `status` is preserved on transport failures so callers can still tell
 * a 4xx/5xx from a network timeout.
 */
export interface ApiResponse<T> {
  data?: T;
  error?: ApiError;
  status: number;
}

export interface ApiRequestOptions<TBody = unknown> {
  method?: ApiMethod;
  headers?: Record<string, string>;
  body?: TBody;
  /** Pass `true` when `body` is a FormData — the browser sets the
   *  multipart boundary, so we must not override `Content-Type`. */
  isFormData?: boolean;
  timeout?: number;
}

async function makeRequest<T>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<ApiResponse<T>> {
  const {
    method = 'GET',
    headers = {},
    body,
    isFormData = false,
    timeout = TIMEOUTS.API_REQUEST,
  } = options;

  const url = new URL(endpoint, API_BASE_URL).toString();

  // Build headers — only set Content-Type when we're not posting a
  // FormData (browsers set multipart/form-data;boundary=... themselves,
  // and overriding it breaks the upload).
  const finalHeaders: Record<string, string> = { ...headers };
  if (!isFormData) {
    finalHeaders['Content-Type'] = finalHeaders['Content-Type'] ?? 'application/json';
  }

  // FormData bodies go over the wire as-is; JSON bodies get stringified.
  // `undefined`/`null` body → no body at all.
  const serializedBody =
    body === undefined || body === null
      ? undefined
      : isFormData
        ? (body as FormData)
        : JSON.stringify(body);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      method,
      headers: finalHeaders,
      body: serializedBody,
      signal: controller.signal,
    });

    const contentType = response.headers.get('content-type');
    const isJson = contentType?.includes('application/json');

    let data;
    try {
      data = isJson ? await response.json() : await response.text();
    } catch {
      // Body parsing failed. Preserve status; surface a generic error
      // so callers can still distinguish a transport issue from a
      // successful-but-empty body.
      const err: ApiError = {
        detail: response.ok ? 'Empty response body' : `Request failed with status ${response.status}`,
        error_code: response.ok ? 'empty_body' : 'http_error',
        status: response.status,
      };
      return { data: undefined, error: response.ok ? undefined : err, status: response.status };
    }

    if (response.ok) {
      // `ok` can include 204 No Content — leave `data` undefined rather
      // than synthesizing a truthy value.
      return {
        data: data === undefined ? undefined : (data as T),
        status: response.status,
      };
    }

    // Non-OK: try to extract the structured error envelope. If the body
    // isn't shaped like one, fall back to a synthesized envelope that
    // still carries the original message — better than swallowing it.
    const extracted = extractApiError(data, response.status);
    return { data: undefined, error: extracted, status: response.status };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return {
        error: { detail: 'Request timeout', error_code: 'timeout', status: 0 },
        status: 0,
      };
    }
    const message = error instanceof Error ? error.message : 'Unknown error';
    return {
      error: { detail: message, error_code: 'network_error', status: 0 },
      status: 0,
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Format a single Pydantic/FastAPI `ValidationError` entry as
 * `"field: message"`, e.g. `"question: field required"`. `loc` includes a
 * leading `"body"`/`"query"` segment we drop since it's not useful to a
 * caller-facing message.
 */
function formatValidationError(err: { loc?: unknown; msg?: unknown }): string {
  const loc = Array.isArray(err.loc) ? err.loc.filter((seg) => seg !== 'body' && seg !== 'query') : [];
  const field = loc.length > 0 ? loc.join('.') : null;
  const msg = typeof err.msg === 'string' ? err.msg : 'Invalid value';
  return field ? `${field}: ${msg}` : msg;
}

/** Coerce whatever shape the backend returned into our `ApiError`. */
function extractApiError(body: unknown, status: number): ApiError {
  if (body && typeof body === 'object') {
    const b = body as { detail?: unknown; error_code?: unknown };
    if (typeof b.detail === 'string' && b.detail.length > 0) {
      return {
        detail: b.detail,
        error_code: typeof b.error_code === 'string' ? b.error_code : 'http_error',
        status,
      };
    }
    // Standard FastAPI/Pydantic 422 shape: `detail` is a
    // `ValidationError[]`, not a string. Without this branch, every
    // request-validation failure collapsed into the generic
    // "Request failed with status 422" fallback below, losing the
    // field-level message entirely.
    if (Array.isArray(b.detail) && b.detail.length > 0) {
      const messages = b.detail
        .filter((entry): entry is { loc?: unknown; msg?: unknown } => entry && typeof entry === 'object')
        .map(formatValidationError);
      if (messages.length > 0) {
        return {
          detail: messages.join('; '),
          error_code: typeof b.error_code === 'string' ? b.error_code : 'validation_error',
          status,
        };
      }
    }
  }
  if (typeof body === 'string' && body.length > 0) {
    return { detail: body, error_code: 'http_error', status };
  }
  return { detail: `Request failed with status ${status}`, error_code: 'http_error', status };
}

// Typed API client methods
export const api = {
  get: <T,>(endpoint: string, options?: Omit<ApiRequestOptions, 'method'>) =>
    makeRequest<T>(endpoint, { ...options, method: 'GET' }),

  post: <T, TBody = unknown>(
    endpoint: string,
    body?: TBody,
    options?: Omit<ApiRequestOptions, 'method' | 'body'>
  ) => makeRequest<T>(endpoint, { ...options, method: 'POST', body }),

  /** Multipart upload variant. Caller passes FormData; we skip the
   *  Content-Type header so the browser supplies the boundary. */
  postForm: <T,>(endpoint: string, formData: FormData, options?: Omit<ApiRequestOptions, 'method' | 'body' | 'isFormData'>) =>
    makeRequest<T>(endpoint, { ...options, method: 'POST', body: formData, isFormData: true }),

  put: <T, TBody = unknown>(
    endpoint: string,
    body?: TBody,
    options?: Omit<ApiRequestOptions, 'method' | 'body'>
  ) => makeRequest<T>(endpoint, { ...options, method: 'PUT', body }),

  delete: <T,>(endpoint: string, options?: Omit<ApiRequestOptions, 'method'>) =>
    makeRequest<T>(endpoint, { ...options, method: 'DELETE' }),

  patch: <T, TBody = unknown>(
    endpoint: string,
    body?: TBody,
    options?: Omit<ApiRequestOptions, 'method' | 'body'>
  ) => makeRequest<T>(endpoint, { ...options, method: 'PATCH', body }),
};

export async function healthCheck() {
  return api.get<HealthResponse>('/health');
}

export async function listLeases() {
  return api.get<LeaseMetadata[]>('/leases');
}

export async function getLease(leaseId: string) {
  return api.get<LeaseMetadata>(`/leases/${leaseId}`);
}

export interface DeletionReport {
  lease_id: string;
  lease_record_removed: boolean;
  pdf_removed: boolean;
  chroma_chunks_removed: number;
  bm25_index_entries_removed: number;
  query_cache_entries_removed: number;
  semantic_cache_entries_removed: number;
  age_days: number | null;
  actor: string;
  errors: string[];
}

export async function deleteLease(leaseId: string) {
  return api.delete<DeletionReport>(`/leases/${leaseId}`);
}

export async function refreshLeaseMetadata(leaseId: string) {
  return api.post<MetadataRefreshResponse>(`/leases/${leaseId}/metadata`);
}

export async function askQuestion(leaseId: string, question: string): Promise<ApiResponse<AskResponse>> {
  const body: AskRequest = { lease_id: leaseId, question };
  return api.post<AskResponse>('/ask', body);
}

export async function compareLeases(leaseIds: string[]) {
  const body: CompareRequest = { lease_ids: leaseIds };
  return api.post<CompareResponse>('/compare', body);
}

export async function getComparisonCount() {
  return api.get<ComparisonCountResponse>('/compare/count');
}

export async function getLeaseChunks(leaseId: string) {
  return api.get<ChunkResponse[]>(`/leases/${leaseId}/chunks`);
}

export interface UploadHandle {
  promise: Promise<ApiResponse<UploadResponse>>;
  abort: () => void;
}

/** Result of a failed body parse — status is preserved, no message details available. */
function uploadParseFailureResult(status: number): ApiResponse<UploadResponse> {
  const ok = status >= 200 && status < 300;
  return {
    data: undefined,
    error: ok
      ? undefined
      : { detail: `Upload failed with status ${status}`, error_code: 'parse_error', status },
    status,
  };
}

/**
 * Shared interpretation of an already-parsed upload response body, used by
 * both `uploadLeaseWithProgress` (XHR, parsed synchronously via
 * `JSON.parse`) and `uploadLease` (fetch, parsed via `response.json()`).
 * Only the raw body retrieval differs between the two transports; success
 * status checking and error envelope extraction stay here so they can't
 * drift between the two implementations.
 */
function uploadResultFromBody(
  status: number,
  data: unknown,
  isJson: boolean | undefined
): ApiResponse<UploadResponse> {
  const ok = status >= 200 && status < 300;
  if (ok) {
    return { data: data as UploadResponse, status };
  }

  const extracted = isJson ? extractApiError(data, status) : {
    detail: typeof data === 'string' && data.length > 0 ? data : `Upload failed with status ${status}`,
    error_code: 'http_error',
    status,
  };
  return { data: undefined, error: extracted, status };
}

/**
 * Returns both the response promise and an `abort()` handle so callers can
 * cancel the in-flight request (e.g. on component unmount) instead of
 * leaving it running in the background after the user navigates away.
 */
export function uploadLeaseWithProgress(
  formData: FormData,
  onProgress: (percent: number) => void
): UploadHandle {
  const url = new URL('/upload', API_BASE_URL).toString();
  const xhr = new XMLHttpRequest();

  const promise = new Promise<ApiResponse<UploadResponse>>((resolve) => {
    xhr.open('POST', url, true);
    // Intentionally the 5-minute upload budget (not the 30s default API
    // timeout) — large PDFs on slow connections need more time than a
    // typical JSON request. See TIMEOUTS.UPLOAD in lib/constants.ts.
    xhr.timeout = TIMEOUTS.UPLOAD;

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      const contentType = xhr.getResponseHeader('content-type');
      const isJson = contentType?.includes('application/json');

      let data;
      try {
        data = isJson ? JSON.parse(xhr.responseText) : xhr.responseText;
      } catch {
        resolve(uploadParseFailureResult(xhr.status));
        return;
      }

      resolve(uploadResultFromBody(xhr.status, data, isJson));
    };

    xhr.onerror = () => {
      resolve({
        error: { detail: 'Upload failed', error_code: 'network_error', status: 0 },
        status: 0,
      });
    };

    xhr.ontimeout = () => {
      resolve({
        error: { detail: 'Upload timeout', error_code: 'timeout', status: 0 },
        status: 0,
      });
    };

    xhr.onabort = () => {
      resolve({
        error: { detail: 'Upload cancelled', error_code: 'cancelled', status: 0 },
        status: 0,
      });
    };

    xhr.send(formData);
  });

  return { promise, abort: () => xhr.abort() };
}

export async function uploadLease(formData: FormData) {
  // Uses the dedicated `postForm` helper, which deliberately omits the
  // `Content-Type` header so the browser sets the multipart boundary
  // automatically. Setting it to `application/json` here silently breaks
  // uploads.
  return api.postForm<UploadResponse>('/upload', formData, { timeout: TIMEOUTS.UPLOAD });
}

// Re-export the shared types so existing call sites that imported them
// from `@/lib/api` (dashboard, upload, list pages) keep working.
export type {
  AskRequest,
  AskResponse,
  CompareRequest,
  CompareResponse,
  ComparisonCountResponse,
  ChunkResponse,
  HealthResponse,
  LeaseMetadata,
  MetadataRefreshResponse,
  UploadResponse,
};
