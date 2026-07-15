/**
 * Auto-generated TypeScript types from FastAPI OpenAPI schema
 *
 * DO NOT EDIT MANUALLY - regenerate with: pnpm gen:types
 */

export interface AskRequest {
  lease_id: string; // ID of the lease document
  question: string; // Question to ask about the lease
}

export interface AskResponse {
  answer: string; // Grounded answer based on lease content
  sources?: SourceReference[]; // Source references
  confidence?: number; // Confidence score (0-1)
  quote?: string | null; // Verbatim quoted span from the lease that the answer is grounded in
  signal?: SignalLabel | null; // How the relevant clause compares to standard lease practice
}

export interface Body_upload_file_upload_post {
  file: string; // PDF lease document
  name: string; // Lease name
  tenant?: string; // Tenant name
  landlord?: string; // Landlord name
}

export interface ChunkResponse {
  id: string; // Unique chunk identifier
  text: string; // Full chunk text
  clause_type: string; // Heuristically assigned clause type
  page?: number | null; // Page number the chunk was extracted from
  source?: string | null; // Source document filename
}

export interface CompareRequest {
  lease_ids: string[]; // Exactly two distinct lease IDs to compare
}

export interface CompareResponse {
  lease_ids: string[]; // IDs of compared leases
  differences: ComparisonDifference[]; // List of differences
  key_insights?: string[]; // Key insights from comparison
}

export interface ComparisonCountResponse {
  count: number; // Total number of comparisons recorded
}

export interface ComparisonDifference {
  clause_type: string; // Type of clause
  lease1_value: string; // Value in first lease
  lease2_value: string; // Value in second lease
  difference: string; // Description of the difference
}

export interface ComparisonHistoryItem {
  id: string; // Unique comparison record identifier
  lease_ids: string[]; // IDs of the leases that were compared
  created_at: string; // ISO timestamp of when the comparison was run
}

export interface ComparisonHistoryResponse {
  items: ComparisonHistoryItem[]; // Comparison records for this page
  page: number; // 1-indexed page number returned
  page_size: number; // Number of records per page (server-capped)
  total: number; // Total number of comparison records
}

export interface DeletionReport {
  lease_id: string;
  lease_record_removed?: boolean;
  pdf_removed?: boolean;
  chroma_chunks_removed?: number;
  bm25_index_entries_removed?: number;
  query_cache_entries_removed?: number;
  semantic_cache_entries_removed?: number;
  age_days?: number | null;
  actor?: string;
  errors?: string[];
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

export interface HealthResponse {
  status: string; // Service status
  version?: string; // API version
}

export interface LeaseMetadata {
  id: string; // Unique lease identifier
  name: string; // Human-readable lease name
  tenant: string; // Tenant name
  landlord: string; // Landlord name
  start_date: string; // Lease start date (YYYY-MM-DD)
  end_date: string; // Lease end date (YYYY-MM-DD)
  rent_amount: string; // Monthly rent amount
  location: string; // Property location
  chunk_count?: number | null; // Number of indexed chunks from ingestion
  created_at?: string | null; // ISO timestamp of when the lease was uploaded
}

export type MetadataExtractionStatus = 'updated' | 'no_fields' | 'failed';

export interface MetadataRefreshResponse {
  status: MetadataExtractionStatus;
  updated_fields: string[];
  lease: LeaseMetadata;
}

export type SignalLabel = 'standard' | 'tenant_friendly' | 'landlord_friendly' | 'unusual' | 'red_flag';

export interface SourceReference {
  clause_id: string; // ID of the clause
  clause_type: string; // Type of clause (e.g., rental_term, maintenance)
  excerpt: string; // Relevant excerpt from the clause
  source?: string | null; // Source document filename
  page?: number | null; // Page number where the clause appears
}

export interface UploadResponse {
  lease_id: string; // ID of the uploaded lease
  name: string; // Lease name
  status: string; // Upload status (pending, processing, complete)
  message: string; // Status message
}

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

// API Endpoints

// Ask a question about a lease
export declare function askAskPost(data: AskRequest): Promise<AskResponse>;

// Compare multiple leases
export declare function compareComparePost(data: CompareRequest): Promise<CompareResponse>;
