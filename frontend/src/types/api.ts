/**
 * DocuMind — API Types
 * All shapes are derived from the FastAPI response models.
 * Keep in sync with backend/app/core/models.py.
 */

export type ConfidenceLabel = "high" | "medium" | "low";

export type Namespace =
  | "default"
  | "kubernetes-docs"
  | "stripe-api"
  | "aws-waf";

export interface User {
  readonly id:                string;
  readonly email:             string;
  readonly name:              string | null;
  readonly avatar_url:        string | null;
  readonly total_queries:     number;
  readonly query_limit:       number;
  readonly queries_remaining: number;
}

export interface Citation {
  readonly source_file:  string;
  readonly heading_path: string;
  readonly page:         number;
  readonly citation:     string;
  readonly confidence:   number;
}

export interface QueryResponse {
  readonly answer:               string;
  readonly citations:            Citation[];
  readonly confidence_score:     number;
  readonly confidence_label:     ConfidenceLabel;
  readonly chunks_used:          number;
  readonly namespace:            string;
  readonly response_ms:          number;
  readonly insufficient_context: boolean;
  readonly warning_message:      string;
  readonly queries_remaining:    number;
  readonly total_queries:        number;
  readonly query_limit:          number;
}

export interface IndexedDocument {
  readonly id:          string;
  readonly filename:    string;
  readonly format:      string;
  readonly status:      "pending" | "complete" | "failed";
  readonly chunk_count: number | null;
  readonly indexed_at:  string | null;
}

export interface ApiError {
  readonly detail: string;
}

// Query state machine
export type QueryStatus =
  | { type: "idle" }
  | { type: "loading" }
  | { type: "success"; data: QueryResponse }
  | { type: "error"; message: string };
