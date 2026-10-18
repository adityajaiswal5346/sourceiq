#!/usr/bin/env bash
# =================================================================
# DocuMind — GitHub Secrets Reference
# Settings → Secrets and variables → Actions → New repository secret
# =================================================================

cat << 'GUIDE'
================================================================
 DocuMind — GitHub Secrets Checklist (Day 4)
================================================================

── AWS (for Lambda deploy via SAM) ──────────────────────────

  AWS_ACCESS_KEY_ID
    IAM user documind-deploy access key ID

  AWS_SECRET_ACCESS_KEY
    IAM user documind-deploy secret key

  AWS_REGION
    e.g. us-east-1

── Anthropic ─────────────────────────────────────────────────

  ANTHROPIC_API_KEY
    sk-ant-... from console.anthropic.com

── RAG services ──────────────────────────────────────────────

  PINECONE_API_KEY
    From pinecone.io → API Keys

  VOYAGE_API_KEY
    From voyageai.com → Dashboard

  COHERE_API_KEY
    From cohere.com → API Keys

── Auth + DB ─────────────────────────────────────────────────

  DATABASE_URL
    postgresql://...?sslmode=require (Neon connection string)

  GOOGLE_CLIENT_ID
    ...apps.googleusercontent.com

── Frontend build ────────────────────────────────────────────

  VITE_GOOGLE_CLIENT_ID
    Same as GOOGLE_CLIENT_ID (baked into Vite bundle)

  VITE_API_BASE_URL
    https://xxxx.execute-api.us-east-1.amazonaws.com/prod
    Get from CloudFormation output after first SAM deploy

── Vercel ────────────────────────────────────────────────────

  VERCEL_TOKEN
    vercel.com → Settings → Tokens → Create

  VERCEL_ORG_ID
    Run: vercel link (in frontend/) → check .vercel/project.json

  VERCEL_PROJECT_ID
    Same as above — from .vercel/project.json

── Lambda CORS ───────────────────────────────────────────────

  ALLOWED_ORIGINS
    https://your-project.vercel.app
    (update after first Vercel deploy)

================================================================
 Total: 15 secrets. Zero stored in repository.
================================================================

Security properties:
  ✓ AWS uses long-term IAM key (scoped to documind-* resources only)
  ✓ All secrets injected at deploy time via SAM --parameter-overrides
  ✓ NoEcho on all SAM parameters — never logged in CloudFormation
  ✓ VITE_ vars baked into bundle at build time only
  ✓ Frontend has no runtime access to backend secrets
GUIDE
