/**
 * Sourciq — Login Page
 *
 * Design references: Vercel dashboard login, Linear, Anthropic Console.
 * Pure white background. Maximum whitespace. Indigo accent only where it matters.
 * Left: clean product proof panel. Right: minimal auth form.
 * No gradients. No decorative blobs. Typography does the work.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Footer from "../components/Footer";
import { useAuth } from "../context/AuthContext";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize:   (c: object) => void;
          renderButton: (el: HTMLElement, c: object) => void;
        };
      };
    };
  }
}

// .trim() guards against a stray trailing newline/space in the env var
// (e.g. a GitHub secret created with `echo` instead of `printf`), which
// would otherwise be sent to Google and rejected as invalid_client.
const CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "").trim();

// What makes Sourciq different — kept short, specific, credible
const PROOF_POINTS = [
  {
    stat:   "Cited",
    detail: "Every answer references the exact document, section, and page.",
  },
  {
    stat:   "Verified",
    detail: "Answers are drawn only from indexed source material — never inferred.",
  },
  {
    stat:   "Scored",
    detail: "Confidence level surfaced on every response so you know when to verify.",
  },
] as const;

export default function LoginPage() {
  const { signInWithGoogle } = useAuth();
  const btnRef = useRef<HTMLDivElement>(null);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleCredential = useCallback(
    async (res: { credential: string }) => {
      setError(null);
      setLoading(true);
      try {
        await signInWithGoogle(res.credential);
      } catch {
        setError("Sign-in failed. Please try again.");
      } finally {
        setLoading(false);
      }
    },
    [signInWithGoogle],
  );

  useEffect(() => {
    if (!CLIENT_ID) return;

    function init() {
      if (!window.google || !btnRef.current) return;
      window.google.accounts.id.initialize({
        client_id:   CLIENT_ID,
        callback:    handleCredential,
        auto_select: false,
      });
      window.google.accounts.id.renderButton(btnRef.current, {
        type:  "standard",
        theme: "outline",
        size:  "large",
        text:  "continue_with",
        width: 280,
        shape: "rectangular",
      });
    }
    if (window.google) { init(); return; }
    const id = setInterval(() => {
      if (window.google) { init(); clearInterval(id); }
    }, 100);
    return () => clearInterval(id);
  }, [handleCredential]);

  return (
    <div className="min-h-screen bg-surface flex">

      {/* ── Left panel — product proof ──────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[520px] flex-shrink-0
                      border-r border-edge bg-surface px-14 py-14">

        {/* Wordmark */}
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-brand rounded-md flex items-center
                          justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold tracking-tight">S</span>
          </div>
          <span className="text-md font-semibold text-ink tracking-tight">
            Sourciq
          </span>
        </div>

        {/* Main copy */}
        <div>
          <h1 className="text-5xl font-semibold text-ink leading-tight
                         tracking-tight mb-5">
            Ask your docs.<br />
            <span className="text-brand">Get a cited answer.</span>
          </h1>
          <p className="text-lg text-ink-secondary leading-relaxed mb-12 max-w-sm">
            Retrieval-augmented search across your engineering
            documentation. Every response attributes its source.
          </p>

          {/* Proof points */}
          <div className="space-y-6">
            {PROOF_POINTS.map((p, i) => (
              <div key={p.stat} className="flex gap-4">
                <div className="w-8 h-8 rounded-lg border border-edge
                                flex items-center justify-center flex-shrink-0
                                text-ink-tertiary text-sm font-mono shadow-xs">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div>
                  <p className="text-md font-semibold text-ink">{p.stat}</p>
                  <p className="text-sm text-ink-secondary mt-0.5 leading-relaxed">
                    {p.detail}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Corpus footer */}
        <div>
          <p className="label-caps mb-3">Pre-indexed corpus</p>
          <div className="flex flex-wrap gap-2">
            {["Kubernetes"].map(tag => (
              <span key={tag}
                    className="text-xs font-medium text-ink-secondary bg-surface-muted
                               border border-edge px-3 py-1.5 rounded-full">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right panel — auth ──────────────────────────────────── */}
      <div className="relative flex-1 flex items-center justify-center px-8 py-14
                      bg-surface-subtle">
        <div className="w-full max-w-[360px]">

          {/* Mobile wordmark */}
          <div className="flex items-center gap-2 mb-10 lg:hidden">
            <div className="w-6 h-6 bg-brand rounded flex items-center
                            justify-center">
              <span className="text-white text-xs font-bold">S</span>
            </div>
            <span className="text-base font-semibold text-ink">Sourciq</span>
          </div>

          {/* Heading */}
          <div className="mb-8">
            <h2 className="text-3xl font-semibold text-ink tracking-tight mb-2">
              Sign in
            </h2>
            <p className="text-sm text-ink-secondary">
              3 queries included. No card required.
            </p>
          </div>

          {/* Google button container */}
          {!CLIENT_ID ? (
            <div role="alert"
                 className="mb-4 px-4 py-3 rounded-lg bg-warning-bg border
                            border-warning-border text-sm text-warning-text">
              Google sign-in is not configured for this deployment.
              Set <code className="font-mono text-xs">VITE_GOOGLE_CLIENT_ID</code> in
              Vercel environment variables and redeploy.
            </div>
          ) : (
            <div ref={btnRef} className="mb-4" />
          )}

          {/* Loading */}
          {loading && (
            <div className="flex items-center gap-2 mt-3 animate-fade-in">
              <div className="w-3.5 h-3.5 border-2 border-brand
                              border-t-transparent rounded-full animate-spin-fast" />
              <span className="text-xs text-ink-secondary">Signing in…</span>
            </div>
          )}

          {/* Error */}
          {error !== null && (
            <div role="alert"
                 className="mt-4 px-4 py-3 rounded-lg bg-danger-bg border
                            border-danger-border text-sm text-danger-text
                            animate-fade-in">
              {error}
            </div>
          )}

          {/* Divider */}
          <div className="flex items-center gap-3 my-8">
            <div className="flex-1 h-px bg-edge" />
            <span className="text-xs text-ink-disabled">secure via Google OAuth</span>
            <div className="flex-1 h-px bg-edge" />
          </div>

          {/* Trust note */}
          <p className="text-xs text-ink-tertiary leading-relaxed text-center">
            Queries are logged for quality monitoring.
            Source documents are never shared or used for training.
          </p>
        </div>

        <Footer className="absolute bottom-6 right-8" />
      </div>
    </div>
  );
}
