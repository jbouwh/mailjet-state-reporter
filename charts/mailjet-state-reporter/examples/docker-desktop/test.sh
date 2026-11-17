#!/usr/bin/env bash
# Install the chart on the Docker Desktop Kubernetes cluster and start a test run.
#
#   ./test.sh            install or upgrade, start a job and follow its logs
#   ./test.sh cleanup    uninstall the release and delete the test namespace
#
# Environment:
#   MAILJET_APP_ID, MAILJET_APP_SECRET  Mailjet credentials (dummy values when unset)
#   CHART          chart to install: this repository (default) or the published chart,
#                  e.g. oci://ghcr.io/jbouwh/charts/mailjet-state-reporter
#   CHART_VERSION  chart version for an OCI chart, e.g. 0.3.11 (default: latest)
#   SETTINGS       settings file (default: settings.yaml next to this script)
#   KUBE_CONTEXT   kubectl context (default: docker-desktop)
#   NAMESPACE      namespace (default: mailjet-reporter-test)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
context="${KUBE_CONTEXT:-docker-desktop}"
namespace="${NAMESPACE:-mailjet-reporter-test}"
release="mailjet-state-reporter"
chart="${CHART:-$here/../..}"
settings="${SETTINGS:-$here/settings.yaml}"

kc() { kubectl --context "$context" --namespace "$namespace" "$@"; }

if [[ "${1:-}" == "cleanup" ]]; then
  helm uninstall "$release" --kube-context "$context" --namespace "$namespace" --ignore-not-found
  kubectl --context "$context" delete namespace "$namespace" --ignore-not-found
  exit 0
fi

kubectl --context "$context" create namespace "$namespace" --dry-run=client -o yaml \
  | kubectl --context "$context" apply -f -

if [[ -z "${MAILJET_APP_ID:-}" || -z "${MAILJET_APP_SECRET:-}" ]]; then
  echo "MAILJET_APP_ID/MAILJET_APP_SECRET not set: using dummy credentials (the Mailjet API will refuse them)" >&2
fi
kc create secret generic mailjet-credentials \
  --from-literal=MAILJET_APP_ID="${MAILJET_APP_ID:-dummy}" \
  --from-literal=MAILJET_APP_SECRET="${MAILJET_APP_SECRET:-dummy}" \
  --dry-run=client -o yaml | kc apply -f -

version_args=()
if [[ -n "${CHART_VERSION:-}" ]]; then
  version_args=(--version "$CHART_VERSION")
fi
helm upgrade --install "$release" "$chart" "${version_args[@]}" \
  --kube-context "$context" --namespace "$namespace" \
  -f "$here/values.yaml" --set-file settings.content="$settings"

job="test-$(date +%Y%m%d%H%M%S)"
kc create job --from="cronjob/$release" "$job"

echo "Waiting for the pod of job $job ..."
for _ in $(seq 1 120); do
  phase="$(kc get pods -l "job-name=$job" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)"
  [[ -n "$phase" && "$phase" != "Pending" ]] && break
  sleep 1
done
kc logs --follow "job/$job" || true

kc wait --for=condition=complete "job/$job" --timeout=10s >/dev/null 2>&1 && status=0 || status=1
kc get "job/$job"
kc get pvc
if [[ $status -ne 0 ]]; then
  echo "Job $job did not complete successfully (expected with dummy credentials)" >&2
fi
exit "$status"
