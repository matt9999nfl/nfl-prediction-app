# Terraform Bootstrap

This runbook covers the one-time setup required before `terraform init` can be run.

## Prerequisites

- GCP CLI (`gcloud`) installed and authenticated to project `nfl-model-471509`
- Terraform 1.5.0 or later installed

## Bootstrap Steps

### 1. Create Terraform State Bucket

The state bucket must exist before Terraform can initialize.

```bash
# Create the GCS bucket for Terraform state
gsutil mb -l us-central1 gs://nfl-model-471509-tfstate

# Enable versioning to prevent accidental state loss
gsutil versioning set on gs://nfl-model-471509-tfstate

# Lock the bucket to prevent concurrent operations
gsutil defacl set gs://nfl-model-471509-tfstate -u
```

### 2. Create Terraform CI Service Account

This service account is used by GitHub Actions (and other CI systems) to apply Terraform.

```bash
# Create the service account
gcloud iam service-accounts create terraform-ci \
  --description="Used by GitHub Actions to apply Terraform" \
  --display-name="Terraform CI"

# Grant it the necessary roles for infrastructure management
gcloud projects add-iam-policy-binding nfl-model-471509 \
  --member="serviceAccount:terraform-ci@nfl-model-471509.iam.gserviceaccount.com" \
  --role="roles/editor"

gcloud projects add-iam-policy-binding nfl-model-471509 \
  --member="serviceAccount:terraform-ci@nfl-model-471509.iam.gserviceaccount.com" \
  --role="roles/iam.securityAdmin"
```

### 3. Set Up Workload Identity Federation (Recommended)

Workload Identity Federation allows GitHub Actions to authenticate without storing service account keys in secrets.

```bash
# Enable required APIs
gcloud services enable iap.googleapis.com
gcloud services enable sts.googleapis.com
gcloud services enable cloudresourcemanager.googleapis.com

# Create a Workload Identity Pool
gcloud iam workload-identity-pools create "github" \
  --project="nfl-model-471509" \
  --location="global" \
  --display-name="GitHub Actions"

# Create a Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="nfl-model-471509" \
  --location="global" \
  --workload-identity-pool="github" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=sub,attribute.aud=aud" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Authorize the GitHub service account to use the Workload Identity
gcloud iam service-accounts add-iam-policy-binding terraform-ci@nfl-model-471509.iam.gserviceaccount.com \
  --project="nfl-model-471509" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/nfl-model-471509/locations/global/workloadIdentityPools/github/attribute.aud/aud"
```

Record the WIF provider and service account for GitHub Actions secrets (see `Secrets Setup` below).

### 4. Secrets Setup

#### Option A: Workload Identity (Recommended)

If you completed the WIF setup above:

```bash
# Get the WIF provider resource name
wif_provider=$(gcloud iam workload-identity-pools providers describe github-provider \
  --workload-identity-pool=github \
  --location=global \
  --project=nfl-model-471509 \
  --format='value(name)')

echo "Add these to GitHub Actions secrets:"
echo "WIF_PROVIDER=$wif_provider"
echo "WIF_SERVICE_ACCOUNT=terraform-ci@nfl-model-471509.iam.gserviceaccount.com"
```

#### Option B: Service Account Key (Fallback)

If Workload Identity is not set up:

```bash
# Create a key for the terraform-ci service account
gcloud iam service-accounts keys create terraform-ci-key.json \
  --iam-account=terraform-ci@nfl-model-471509.iam.gserviceaccount.com

# Base64 encode the key and add it to GitHub Actions secrets
base64 -i terraform-ci-key.json | pbcopy  # macOS
# or
base64 -w 0 terraform-ci-key.json | xclip -selection clipboard  # Linux

# In GitHub Actions, set GCP_SA_KEY secret and update the deploy workflows to use:
# - uses: google-github-actions/auth@v2
#   with:
#     credentials_json: ${{ secrets.GCP_SA_KEY }}

# IMPORTANT: Delete the local key file after uploading to GitHub
rm terraform-ci-key.json
```

### 5. First Terraform Init and Apply

Now you can initialize and apply Terraform:

```bash
cd 05-DEVOPS/infra/terraform

# Initialize Terraform (this will use the GCS backend created above)
terraform init

# Validate the configuration
terraform validate

# Preview the changes
terraform plan

# Apply the infrastructure
terraform apply
```

## Troubleshooting

### "Backend initialization required" Error

If you get an error about the backend bucket not existing:

1. Verify the bucket exists:
   ```bash
   gsutil ls -b gs://nfl-model-471509-tfstate
   ```

2. If it doesn't exist, create it (step 1 above)

3. Re-run `terraform init`:
   ```bash
   terraform init
   ```

### "Permission denied" on Service Account

If CI jobs fail with "Permission denied":

1. Verify the service account has the required roles:
   ```bash
   gcloud projects get-iam-policy nfl-model-471509 \
     --flatten="bindings[].members" \
     --format='table(bindings.role)' \
     --filter="bindings.members:terraform-ci@nfl-model-471509.iam.gserviceaccount.com"
   ```

2. If missing roles, re-run the role assignment steps above

3. If using Workload Identity, verify the binding:
   ```bash
   gcloud iam service-accounts get-iam-policy terraform-ci@nfl-model-471509.iam.gserviceaccount.com
   ```

## One-Time Costs

The bootstrap incurs minimal one-time costs:
- GCS bucket for state: ~$0.01/month
- Workload Identity Pool/Provider: free tier includes up to 1M requests/month free
- Service account: free

## Post-Bootstrap

Once bootstrap is complete:

1. All infrastructure changes go through Terraform (not manual `gcloud` commands)
2. Every PR triggers `terraform plan` to check for drift
3. On merge to `main`, `terraform apply` provisions the resources
4. Rollback is via `terraform destroy` or reverting the PR

Document any manual changes to infrastructure in `INCIDENTS.md` with a note to fix in Terraform.
