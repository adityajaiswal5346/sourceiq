/**
 * DocuMind — API Client
 * All requests go through this module — never raw fetch in components.
 * Typed return values. Specific error messages for 401, 429, 503.
 */

import type { IndexedDocument, Namespace, QueryResponse, User } from "../types/api";

// .trim() guards against a stray trailing newline/space in the env var
// (e.g. a GitHub secret created with `echo` instead of `printf`).
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").trim();

class ApiError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path:       string,
  options:    RequestInit = {},
  credential?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(credential ? { Authorization: `Bearer ${credential}` } : {}),
  };

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> ?? {}) },
  });

  if (res.ok) return res.json() as Promise<T>;

  // Parse error detail from FastAPI response
  let detail = "An unexpected error occurred.";
  try {
    const body = await res.json() as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch { /* ignore parse failure */ }

  // Map status codes to user-facing messages
  switch (res.status) {
    case 401:
      throw new ApiError("Session expired. Please sign in again.", 401);
    case 403:
      throw new ApiError("Access denied.", 403);
    case 422:
      throw new ApiError("Invalid request. Please check your input.", 422);
    case 429:
      throw new ApiError(detail, 429);
    case 503:
      throw new ApiError("Service temporarily unavailable. Please try again.", 503);
    default:
      throw new ApiError(detail, res.status);
  }
}

export const api = {
  auth: {
    google: (credential: string): Promise<User> =>
      request<User>("/api/auth/google", {
        method: "POST",
        body:   JSON.stringify({ credential }),
      }),

    me: (credential: string): Promise<User> =>
      request<User>("/api/auth/me", {}, credential),

    logout: (credential: string): Promise<void> =>
      request<void>("/api/auth/logout", { method: "POST" }, credential),
  },

  query: {
    submit: (
      question:   string,
      namespace:  Namespace,
      credential: string,
      alpha?:     number,
    ): Promise<QueryResponse> =>
      request<QueryResponse>(
        "/api/query",
        {
          method: "POST",
          body:   JSON.stringify({ question, namespace, alpha: alpha ?? 0.7 }),
        },
        credential,
      ),
  },

  documents: {
    list: (namespace: Namespace, credential?: string): Promise<IndexedDocument[]> =>
      request<IndexedDocument[]>(
        `/api/documents?namespace=${encodeURIComponent(namespace)}`,
        {},
        credential,
      ),
  },

  health: (): Promise<{ status: string }> =>
    request<{ status: string }>("/health"),
};

export { ApiError };
