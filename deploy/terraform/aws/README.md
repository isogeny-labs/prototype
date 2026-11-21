# Evidence Lab on AWS (Terraform)

Added 21 November 2026. One copy of the app on AWS, with the hosting parts described in
[docs/HOSTING.md](../../../docs/HOSTING.md):

| Part | AWS |
| --- | --- |
| The app (one container, demo mode) | ECS Fargate, exactly one task, in private subnets |
| Address | Application Load Balancer; HTTPS with an ACM certificate when `domain_name` and `route53_zone_id` are given |
| Database | RDS PostgreSQL 16, encrypted, private, TLS required; the password is kept and rotated by RDS in Secrets Manager |
| Cache | ElastiCache Redis 7.1, TLS in transit |
| File copies | S3 bucket: private, encrypted, versioned, TLS only |
| The data folder (`/data`: the evidence signing key, the demo certificate, connected demo repositories) | EFS, encrypted, mounted through an access point as the app's user |
| Image | ECR repository (scanned on push) |
| GitHub client secret | Secrets Manager |
| Logs | CloudWatch (`/ecs/<name>`) |

Exactly one task runs, and a deploy stops the old task before starting the new one (a short pause). The app keeps
its running tests and demo servers in its own process, so two copies must not share one data folder.

Rough cost at the defaults (us-east-1, on-demand, small instances): about 100 US dollars a month. The NAT gateway, the
load balancer, RDS and ElastiCache make up most of it.

## Before you start

- Terraform 1.6 or newer, the AWS CLI logged in to the account, and Docker to build the image.
- For HTTPS on your own address: a Route 53 hosted zone that holds it.
- For the GitHub login: a GitHub App (docs/HOSTING.md, "The GitHub App"). Its Callback URL is the
  `github_callback_url` output, so create the App after step 1, or set the URL afterwards.

## 1. Create everything

```
cd deploy/terraform/aws
cp terraform.tfvars.example terraform.tfvars      # fill in; git ignores it
export TF_VAR_github_client_secret=...             # only with a GitHub App; keeps it out of the file
terraform init
terraform apply
```

The first apply takes about 15 minutes (RDS and ElastiCache are the slow parts). The app's service starts, but no
image is in the repository yet, so its task fails until step 2.

## 2. Build and push the image

From the repository root (the image is for x86-64):

```
REPO=$(terraform -chdir=deploy/terraform/aws output -raw ecr_repository_url)
aws ecr get-login-password | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/amd64 -t "$REPO:latest" .
docker push "$REPO:latest"
aws ecs update-service --cluster "$(terraform -chdir=deploy/terraform/aws output -raw ecs_cluster)" \
  --service "$(terraform -chdir=deploy/terraform/aws output -raw ecs_service)" --force-new-deployment
```

For a pinned release, push a tag such as `2026-11-21` and set `image_tag` to it, then `terraform apply`.

## 3. Open it

`terraform output app_url`. With a GitHub App the login screen shows **Log in with GitHub**. Without one, the app
asks the first visitor to **create the password**, so open it yourself straight away (or narrow `allowed_cidrs`
first).

`/api/health` should say `postgresql`, `redis` and `s3`, all `ok`. Logs: `aws logs tail /ecs/<name> --follow`.

## Checks

`terraform test` plans the whole stack against mocked AWS, with no account needed. It checks one task, HTTP versus
HTTPS, secrets that reach the task only from Secrets Manager, a private bucket, Redis over TLS, and data protection.
`terraform validate` and `terraform fmt -check` should pass too.

## Taking it down

`protect_data = true` (the default) keeps the database (deletion protection and a final snapshot), the bucket and the
images from being removed by `terraform destroy`. For a throwaway copy, set `protect_data = false`, apply, then
destroy.

## Before real customer data

Read "Not in this version, and for the owner to decide" in docs/HOSTING.md first. In particular, a hosted copy runs
TLS checks from inside this VPC: the app's security group allows all outbound traffic so that GitHub, osv.dev and
the addresses people confirm can be reached. Narrow it, and `allowed_cidrs`, to what you decide.
