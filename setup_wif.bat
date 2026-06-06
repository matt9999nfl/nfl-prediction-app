@echo off
gcloud iam workload-identity-pools providers create-oidc github-provider ^
  --project=nfl-model-471509 ^
  --location=global ^
  --workload-identity-pool=github-pool ^
  --display-name=github-provider ^
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository ^
  --attribute-condition=assertion.repository==\"matt9999nfl/nfl-prediction-app\" ^
  --issuer-uri=https://token.actions.githubusercontent.com
