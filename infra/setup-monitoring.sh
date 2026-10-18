#!/usr/bin/env bash
# =================================================================
# DocuMind — CloudWatch Monitoring Setup
# Run once after first Lambda deploy to create all alarms.
#
# Alarms created:
#   1. Lambda error rate > 5 in 5 minutes     (severity: critical)
#   2. p95 Lambda duration > 5000ms            (severity: warning)
#   3. Lambda throttles > 0 in 5 minutes      (severity: warning)
#   4. AWS budget alert at $10/month
#
# Usage:
#   chmod +x infra/setup-monitoring.sh
#   ./infra/setup-monitoring.sh your@email.com
#   ./infra/setup-monitoring.sh your@email.com eu-north-1
#
# Region: AWS_REGION env, 2nd arg, or backend/samconfig.toml (not us-east-1 default).
# Budget API always uses us-east-1 (AWS global requirement for Budgets).
# =================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMCONFIG="$REPO_ROOT/backend/samconfig.toml"

ALERT_EMAIL="${1:-}"
REGION_ARG="${2:-}"

if [[ -z "$ALERT_EMAIL" ]]; then
  echo "Usage: ./infra/setup-monitoring.sh your@email.com [aws-region]"
  echo "       AWS_REGION=eu-north-1 ./infra/setup-monitoring.sh your@email.com"
  exit 1
fi

detect_region() {
  if [[ -n "${AWS_REGION:-}" ]]; then
    echo "$AWS_REGION"
    return
  fi
  if [[ -n "$REGION_ARG" ]]; then
    echo "$REGION_ARG"
    return
  fi
  if [[ -f "$SAMCONFIG" ]]; then
    local from_sam
    # Portable parse (macOS sed does not support \s in all versions)
    from_sam=$(awk -F'"' '/^[[:space:]]*region[[:space:]]*=/ { print $2; exit }' "$SAMCONFIG")
    if [[ -n "$from_sam" ]]; then
      echo "$from_sam"
      return
    fi
  fi
  echo "eu-north-1"
}

STACK_NAME="documind-prod"
REGION="$(detect_region)"
FUNCTION_NAME="documind-api-prod"

echo "Setting up CloudWatch monitoring..."
echo "Region:   $REGION"
echo "Function: $FUNCTION_NAME"
echo "Email:    $ALERT_EMAIL"
echo ""

# ── 1. SNS topic for alert emails ────────────────────────────────
echo "[1/5] Creating SNS topic..."
TOPIC_ARN=$(aws sns create-topic \
  --name "documind-alerts" \
  --region "$REGION" \
  --query TopicArn \
  --output text)

aws sns subscribe \
  --topic-arn "$TOPIC_ARN" \
  --protocol email \
  --notification-endpoint "$ALERT_EMAIL" \
  --region "$REGION" \
  --output json >/dev/null

echo "      ✓ SNS topic: $TOPIC_ARN"
echo "      ✓ Check $ALERT_EMAIL to confirm subscription"

# ── 2. Lambda error rate alarm ────────────────────────────────────
echo "[2/5] Lambda error alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name         "documind-lambda-errors" \
  --alarm-description  "DocuMind Lambda error rate > 5 in 5 minutes" \
  --metric-name        Errors \
  --namespace          AWS/Lambda \
  --dimensions         Name=FunctionName,Value="$FUNCTION_NAME" \
  --statistic          Sum \
  --period             300 \
  --evaluation-periods 1 \
  --threshold          5 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions      "$TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region             "$REGION"
echo "      ✓ Error alarm (>5 errors in 5min)"

# ── 3. p95 latency alarm ──────────────────────────────────────────
echo "[3/5] p95 latency alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name          "documind-lambda-latency-p95" \
  --alarm-description   "DocuMind p95 Lambda duration > 5 seconds" \
  --metric-name         Duration \
  --namespace           AWS/Lambda \
  --dimensions          Name=FunctionName,Value="$FUNCTION_NAME" \
  --extended-statistic  p95 \
  --period              300 \
  --evaluation-periods  2 \
  --threshold           5000 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions       "$TOPIC_ARN" \
  --treat-missing-data  notBreaching \
  --region              "$REGION"
echo "      ✓ Latency alarm (p95 > 5s for 10min)"

# ── 4. Throttle alarm ─────────────────────────────────────────────
echo "[4/5] Throttle alarm..."
aws cloudwatch put-metric-alarm \
  --alarm-name         "documind-lambda-throttles" \
  --alarm-description  "DocuMind Lambda is being throttled" \
  --metric-name        Throttles \
  --namespace          AWS/Lambda \
  --dimensions         Name=FunctionName,Value="$FUNCTION_NAME" \
  --statistic          Sum \
  --period             300 \
  --evaluation-periods 1 \
  --threshold          0 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions      "$TOPIC_ARN" \
  --treat-missing-data notBreaching \
  --region             "$REGION"
echo "      ✓ Throttle alarm"

# ── 5. AWS budget alert ───────────────────────────────────────────
echo "[5/5] AWS budget alert..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws budgets create-budget \
  --account-id "$ACCOUNT_ID" \
  --budget '{
    "BudgetName": "documind-monthly",
    "BudgetLimit": { "Amount": "10", "Unit": "USD" },
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }' \
  --notifications-with-subscribers '[
    {
      "Notification": {
        "NotificationType": "ACTUAL",
        "ComparisonOperator": "GREATER_THAN",
        "Threshold": 80,
        "ThresholdType": "PERCENTAGE"
      },
      "Subscribers": [
        { "SubscriptionType": "EMAIL", "Address": "'"$ALERT_EMAIL"'" }
      ]
    }
  ]' \
  --region us-east-1 2>/dev/null || echo "      (Budget already exists — skipped; Budgets API is always us-east-1)"

echo "      ✓ Budget alert at \$8/month (80% of \$10)"
echo ""
echo "================================================"
echo " Monitoring setup complete"
echo "================================================"
echo ""
echo " Alarms:"
echo "   Lambda errors  > 5 in 5min   → email"
echo "   Lambda p95     > 5s for 10min → email"
echo "   Lambda throttles > 0          → email"
echo "   AWS spend      > \$8/month    → email"
echo "   Anthropic spend > \$3/day     → GitHub issue (cost-monitor.yml)"
echo ""
echo " View in AWS Console:"
echo "   CloudWatch → Alarms"
echo "   https://console.aws.amazon.com/cloudwatch/home?region=$REGION#alarmsV2"
