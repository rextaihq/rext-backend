#!/usr/bin/env bash

set -Eeuo pipefail

# ============================================================
# Rext.ai Stage Docker Build & Push
# ============================================================

REPO_OWNER="rextaihq"
REPO_NAME="rext-backend"
BRANCH="stage"
API_VERSION="0.12.6"

IMAGE="ghcr.io/${REPO_OWNER}/${REPO_NAME}"
DEPLOY_TAG="stage"

CURRENT_STEP="Starting"

# ------------------------------------------------------------
# Colors
# ------------------------------------------------------------

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ------------------------------------------------------------
# Error handler
# ------------------------------------------------------------

on_error() {
    echo
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}❌ STAGE DEPLOYMENT FAILED${NC}"
    echo -e "${RED}============================================================${NC}"
    echo
    echo -e "${RED}Failed step:${NC} ${CURRENT_STEP}"
    echo
    echo "Deployment stopped. No further steps were executed."
    exit 1
}

trap on_error ERR

# ------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------

step() {
    CURRENT_STEP="$1"
    echo
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}▶ $1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# ------------------------------------------------------------
# Start
# ------------------------------------------------------------

echo
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}🚀 Rext.ai Stage Docker Build & Push${NC}"
echo -e "${CYAN}============================================================${NC}"
echo
echo "Repository : ${REPO_OWNER}/${REPO_NAME}"
echo "Branch     : ${BRANCH}"
echo "Image      : ${IMAGE}"
echo "Tag        : ${DEPLOY_TAG}"
echo "API Version: ${API_VERSION}"
echo

# ------------------------------------------------------------
# 1. Check required commands
# ------------------------------------------------------------

step "Checking required tools"

command -v git >/dev/null
command -v docker >/dev/null
command -v python3 >/dev/null
command -v pip >/dev/null

success "git is available"
success "docker is available"
success "python3 is available"
success "pip is available"

# ------------------------------------------------------------
# 2. Update repository
# ------------------------------------------------------------

step "Fetching latest ${BRANCH} from origin"

git fetch origin

success "Git fetch completed"

step "Syncing local ${BRANCH} with origin/${BRANCH}"

git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

success "Local ${BRANCH} is synced with origin/${BRANCH}"

# ------------------------------------------------------------
# 3. Verify working tree
# ------------------------------------------------------------

step "Checking Git working tree"

if [[ -n "$(git status --porcelain)" ]]; then
    echo -e "${RED}❌ Working tree is not clean${NC}"
    git status
    exit 1
fi

success "Working tree is clean"

# ------------------------------------------------------------
# 4. Install LangGraph CLI
# ------------------------------------------------------------

step "Checking existing LangGraph CLI"

LANGGRAPH="${PWD}/.venv/bin/langgraph"

if [[ ! -x "${LANGGRAPH}" ]]; then
    echo "Error: LangGraph CLI not found at ${LANGGRAPH}"
    exit 1
fi

"${LANGGRAPH}" --version

success "Existing LangGraph CLI is available"

# ------------------------------------------------------------
# 5. Get exact commit SHA
# ------------------------------------------------------------

step "Getting stage commit SHA"

SHA="$(git rev-parse HEAD)"

echo
echo "Stage commit:"
echo "${SHA}"
echo

success "Commit SHA captured"

# ------------------------------------------------------------
# 6. Build Docker image
# ------------------------------------------------------------

step "Building stage Docker image"

echo
echo "Image: ${IMAGE}:${DEPLOY_TAG}"
echo "Commit: ${SHA}"
echo

"${LANGGRAPH}" build \
    --api-version "${API_VERSION}" \
    -t "${IMAGE}:${DEPLOY_TAG}"

success "Stage Docker image built successfully"

# ------------------------------------------------------------
# 7. Tag image with commit SHA
# ------------------------------------------------------------

step "Creating rollback image tag"

docker tag \
    "${IMAGE}:${DEPLOY_TAG}" \
    "${IMAGE}:sha-${SHA}"

success "Rollback tag created"
echo "Tag: ${IMAGE}:sha-${SHA}"

# ------------------------------------------------------------
# 8. Push stage image
# ------------------------------------------------------------

step "Pushing stage image to GHCR"

docker push "${IMAGE}:${DEPLOY_TAG}"

success "Stage image pushed successfully"

# ------------------------------------------------------------
# 9. Push SHA image
# ------------------------------------------------------------

step "Pushing stage SHA image to GHCR"

docker push "${IMAGE}:sha-${SHA}"

success "Stage SHA image pushed successfully"

# ------------------------------------------------------------
# 10. Verify images
# ------------------------------------------------------------

step "Verifying images in GHCR"

docker manifest inspect "${IMAGE}:${DEPLOY_TAG}" >/dev/null
success "${IMAGE}:${DEPLOY_TAG} verified in GHCR"

docker manifest inspect "${IMAGE}:sha-${SHA}" >/dev/null
success "${IMAGE}:sha-${SHA} verified in GHCR"

# ------------------------------------------------------------
# 11. Docker cleanup
# ------------------------------------------------------------

step "Cleaning unused Docker resources"

docker system prune -f

success "Docker cleanup completed"

# ------------------------------------------------------------
# 12. Final summary
# ------------------------------------------------------------

echo
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}🎉 STAGE BUILD & PUSH SUCCESSFULLY COMPLETED${NC}"
echo -e "${GREEN}============================================================${NC}"
echo
echo "Repository : ${REPO_OWNER}/${REPO_NAME}"
echo "Branch     : ${BRANCH}"
echo "Commit SHA : ${SHA}"
echo
echo "Docker images pushed:"
echo "  ✓ ${IMAGE}:stage"
echo "  ✓ ${IMAGE}:sha-${SHA}"
echo
echo -e "${GREEN}✅ Build completed successfully${NC}"
echo -e "${GREEN}✅ SHA rollback tag created successfully${NC}"
echo -e "${GREEN}✅ Both images pushed to GHCR successfully${NC}"
echo -e "${GREEN}✅ GHCR images verified successfully${NC}"
echo -e "${GREEN}✅ Docker cleanup completed${NC}"
echo
echo -e "${CYAN}🚀 Next step:${NC}"
echo "Redeploy the Stage service in Coolify."
echo
echo -e "${GREEN}Stage deployment preparation is complete.${NC}"
echo
