#!/bin/sh
# Demonstrates a zero-downtime rolling update, a failed release, and a rollback,
# while an in-cluster client keeps calling the app to prove it never went down.
#
# Prereqs (docs/KUBERNETES.md): kubectl pointed at a cluster that has the
# finveritas:1.0.0 and finveritas:1.1.0 images, and the finveritas-secrets Secret.
#
#   sh deploy/k8s/demo-rollout.sh
set -eu

NS=finveritas
DEPLOY=deployment/finveritas
HERE=$(cd "$(dirname "$0")" && pwd)

k() { kubectl -n "$NS" "$@"; }
step() { printf '\n==== %s ====\n' "$*"; }
pods() {
  k get pods -l app.kubernetes.io/name=finveritas \
    -o custom-columns='POD:.metadata.name,IMAGE:.spec.containers[0].image,READY:.status.containerStatuses[0].ready,WAITING:.status.containerStatuses[0].state.waiting.reason'
}
replicasets() {
  k get rs -l app.kubernetes.io/name=finveritas \
    -o custom-columns='REPLICASET:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,DESIRED:.spec.replicas,READY:.status.readyReplicas'
}

step "1. Deploy v1.0.0 (3 replicas)"
kubectl apply -k "$HERE/overlays/local"
k annotate "$DEPLOY" kubernetes.io/change-cause="initial deploy: finveritas:1.0.0" --overwrite
k rollout status "$DEPLOY" --timeout=180s
pods

step "2. Start traffic: an in-cluster client calls the Service 5 times a second"
k delete pod traffic --ignore-not-found --wait
k apply -f "$HERE/demo/traffic.yaml"
k wait --for=condition=Ready pod/traffic --timeout=60s

step "3. Rolling update: v1.0.0 -> v1.1.0"
k set image "$DEPLOY" app=finveritas:1.1.0
k annotate "$DEPLOY" kubernetes.io/change-cause="rolling update to finveritas:1.1.0" --overwrite
k rollout status "$DEPLOY" --timeout=180s
replicasets

step "4. Bad release: finveritas:1.2.0 was never built"
k set image "$DEPLOY" app=finveritas:1.2.0
k annotate "$DEPLOY" kubernetes.io/change-cause="bad release: finveritas:1.2.0 (image missing)" --overwrite
if k rollout status "$DEPLOY" --timeout=40s; then
  echo "unexpected: the bad release went live"; exit 1
fi
echo "-> rollout is stuck: the new pod can't start, so the 3 v1.1.0 pods keep serving"
pods

step "5. Roll back to the last good version"
k rollout undo "$DEPLOY"
k rollout status "$DEPLOY" --timeout=180s
replicasets
k rollout history "$DEPLOY"

step "6. Traffic seen by the client during all of the above"
k logs traffic | grep "requests=" | tail -n 1
k logs traffic | grep "FAILED" || echo "no failed requests"
k delete pod traffic --wait=false
