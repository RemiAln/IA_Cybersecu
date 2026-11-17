#!/usr/bin/env bash
# WAF (Cloud Armor) de l'API : limite de débit GLOBALE, appliquée avant les pods.
#   60 requêtes par minute et par clé API (en-tête X-API-Key), au-delà : 429.
#
# Cloud Armor se configure côté Google Cloud (gcloud), pas dans Kubernetes.
# Il est ensuite branché sur l'API par le BackendConfig de ingress.yaml
# (securityPolicy: dss-waf).
#
# Usage (Cloud Shell, depuis TP1/Deployment/k8s/) :
#   bash waf.sh
#   kubectl apply -f service.yaml -f ingress.yaml

set -euo pipefail

POLITIQUE=dss-waf
LIMITE=60          # requêtes...
FENETRE=60         # ...par 60 secondes

# Politique (créée une seule fois)
gcloud compute security-policies describe "$POLITIQUE" >/dev/null 2>&1 \
  || gcloud compute security-policies create "$POLITIQUE" \
       --description="WAF API Digital Social Score"

# Règle de limite de débit : créée, ou mise à jour si elle existe déjà
ACTION=create
gcloud compute security-policies rules describe 1000 --security-policy="$POLITIQUE" >/dev/null 2>&1 && ACTION=update
gcloud compute security-policies rules "$ACTION" 1000 --security-policy="$POLITIQUE" \
  --src-ip-ranges="*" --action=throttle \
  --conform-action=allow --exceed-action=deny-429 \
  --rate-limit-threshold-count="$LIMITE" --rate-limit-threshold-interval-sec="$FENETRE" \
  --enforce-on-key=HTTP-HEADER --enforce-on-key-name=X-API-Key

gcloud compute security-policies describe "$POLITIQUE" --format="table(rules.priority, rules.action, rules.rateLimitOptions.rateLimitThreshold)"
