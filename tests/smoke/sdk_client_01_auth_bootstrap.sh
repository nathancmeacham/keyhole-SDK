#!/usr/bin/env bash
# =============================================================================
# SDK-CLIENT-01 - Official Smoke Test (Client-Side)
# Name: sdk-client-01-smoke-auth-bootstrap
#
# Purpose:
#   Prove real-world viability of the SDK + CLI against the live MCP server:
#     - real auth flow
#     - real token
#     - real /whoami
#     - real identity context
#     - real proof bundle
#     - optional real event emission check
#
# Notes:
#   - This is an operator-assisted smoke test. Device flow may require
#     user interaction and is not assumed to be unattended CI.
#   - Event verification is optional by default because auth event emission
#     may still be partially wired until SDK-CLIENT-01-A is complete.
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

MCP_BASE_URL="${MCP_BASE_URL:-https://mcp.keyholesolution.com}"
KEYHOLE_HOME="${KEYHOLE_HOME:-$HOME/.keyhole}"

# By default, this script validates the live boundary, not a local docker stack.
CHECK_LOCAL_RUNTIME="${CHECK_LOCAL_RUNTIME:-false}"
LOCAL_RUNTIME_URL="${LOCAL_RUNTIME_URL:-http://localhost:8080}"

# Event checking is optional until auth event spine alignment is fully sealed.
SKIP_EVENT_CHECK="${SKIP_EVENT_CHECK:-false}"
EVENT_CHECK_REQUIRED="${EVENT_CHECK_REQUIRED:-false}"

# Secondary authenticated endpoint check.
SECONDARY_AUTH_URL="${SECONDARY_AUTH_URL:-$MCP_BASE_URL/mcp/v1/memory/search}"
SECONDARY_AUTH_PAYLOAD="${SECONDARY_AUTH_PAYLOAD:-{\"query\":\"smoke test identity\",\"limit\":1}}"

# Proof directory can be forced externally if desired.
PROOF_DIR="${PROOF_DIR:-}"

DEBUG="${DEBUG:-false}"

# -----------------------------------------------------------------------------
# Colors
# -----------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# Counters
# -----------------------------------------------------------------------------

TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# -----------------------------------------------------------------------------
# Globals populated during execution
# -----------------------------------------------------------------------------

LOGIN_OUTPUT=""
WHOAMI_OUTPUT=""
TOKEN=""
WHOAMI_USER_ID=""
WHOAMI_MODE=""
CREDENTIALS_FILE=""
INFERRED_PROOF_DIR=""

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------

inc_total()  { ((TOTAL_CHECKS+=1)); }
inc_passed() { ((PASSED_CHECKS+=1)); }
inc_failed() { ((FAILED_CHECKS+=1)); }
inc_warn()   { ((WARNINGS+=1)); }

log_info() {
    echo -e "${BLUE}ℹ?  $1${NC}"
}

log_success() {
    echo -e "${GREEN}OK $1${NC}"
    inc_passed
    inc_total
}

log_fail() {
    echo -e "${RED}NO $1${NC}"
    inc_failed
    inc_total
}

log_warn() {
    echo -e "${YELLOW}⚠?  $1${NC}"
    inc_warn
}

log_step() {
    echo ""
    echo -e "${BLUE}------------------------------------------------------------${NC}"
    echo -e "${BLUE}🔹 $1${NC}"
    echo -e "${BLUE}------------------------------------------------------------${NC}"
}

debug() {
    if [[ "$DEBUG" == "true" ]]; then
        echo -e "${YELLOW}[DEBUG] $1${NC}"
    fi
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_fail "Required command not found: $1"
        exit 1
    fi
}

json_get() {
    local input="$1"
    local jq_expr="$2"
    jq -r "$jq_expr // empty" <<<"$input" 2>/dev/null || true
}

json_file_get() {
    local file="$1"
    local jq_expr="$2"
    jq -r "$jq_expr // empty" "$file" 2>/dev/null || true
}

http_get() {
    local url="$1"
    local auth_token="${2:-}"
    if [[ -n "$auth_token" ]]; then
        curl -sS -w $'\n%{http_code}' \
            -X GET "$url" \
            -H "Authorization: Bearer $auth_token" \
            -H "Content-Type: application/json"
    else
        curl -sS -w $'\n%{http_code}' \
            -X GET "$url" \
            -H "Content-Type: application/json"
    fi
}

http_post_json() {
    local url="$1"
    local payload="$2"
    local auth_token="${3:-}"
    if [[ -n "$auth_token" ]]; then
        curl -sS -w $'\n%{http_code}' \
            -X POST "$url" \
            -H "Authorization: Bearer $auth_token" \
            -H "Content-Type: application/json" \
            -d "$payload"
    else
        curl -sS -w $'\n%{http_code}' \
            -X POST "$url" \
            -H "Content-Type: application/json" \
            -d "$payload"
    fi
}

split_http_response() {
    local raw="$1"
    HTTP_CODE="$(echo "$raw" | tail -n1)"
    HTTP_BODY="$(echo "$raw" | sed '$d')"
}

cleanup() {
    :
}

# -----------------------------------------------------------------------------
# Layer 0 - Prerequisites Check
# -----------------------------------------------------------------------------

check_prerequisites() {
    log_step "Layer 0 - Prerequisites Check"

    require_command curl
    log_success "curl available"

    require_command jq
    log_success "jq available"

    require_command keyhole
    log_success "keyhole CLI available"

    if command -v python3 >/dev/null 2>&1; then
        log_success "python3 available"
    else
        log_warn "python3 not available - some optional checks may be skipped"
    fi
}

# -----------------------------------------------------------------------------
# Optional - Local Runtime Probe
# -----------------------------------------------------------------------------

probe_local_runtime() {
    if [[ "$CHECK_LOCAL_RUNTIME" != "true" ]]; then
        return 0
    fi

    log_step "Optional Local Runtime Probe"

    log_info "Checking local runtime at $LOCAL_RUNTIME_URL"

    local raw
    raw="$(http_get "$LOCAL_RUNTIME_URL/healthz" || true)"
    split_http_response "$raw"

    if [[ "$HTTP_CODE" == "200" ]]; then
        log_success "Local runtime healthz returned HTTP 200"
    else
        log_warn "Local runtime healthz returned HTTP $HTTP_CODE"
    fi

    raw="$(http_get "$LOCAL_RUNTIME_URL/identity" || true)"
    split_http_response "$raw"

    if [[ "$HTTP_CODE" == "200" ]]; then
        local runtime_id
        runtime_id="$(json_get "$HTTP_BODY" '.runtime_id')"
        if [[ -n "$runtime_id" ]]; then
            log_success "Local runtime identity returned runtime_id=$runtime_id"
        else
            log_warn "Local runtime /identity returned 200 but runtime_id missing"
        fi
    else
        log_warn "Local runtime /identity returned HTTP $HTTP_CODE"
    fi
}

# -----------------------------------------------------------------------------
# Layer 1 - CLI Login Invocation
# -----------------------------------------------------------------------------

run_cli_login() {
    log_step "Layer 1 - CLI Login (Device Flow)"

    log_info "Clearing existing credentials for clean test..."
    rm -rf "$KEYHOLE_HOME" 2>/dev/null || true

    log_info "Executing: keyhole login --flow device --json"
    log_info "This may require operator approval in the device flow."

    if LOGIN_OUTPUT="$(keyhole login --flow device --json 2>&1)"; then
        log_success "Login command completed successfully"
        debug "Login output: $LOGIN_OUTPUT"
    else
        log_fail "Login command failed"
        echo "$LOGIN_OUTPUT"
        exit 1
    fi

    local success
    success="$(json_get "$LOGIN_OUTPUT" '.success')"

    if [[ "$success" == "true" ]]; then
        log_success "Login reported success=true"
    else
        log_fail "Login reported success=false"
        echo "$LOGIN_OUTPUT" | jq '.' 2>/dev/null || echo "$LOGIN_OUTPUT"
        exit 1
    fi

    local mode
    mode="$(json_get "$LOGIN_OUTPUT" '.data.mode')"
    if [[ -n "$mode" ]]; then
        log_info "Login reported mode: $mode"
    else
        log_warn "Mode not present in login output"
    fi

    local user_id
    user_id="$(json_get "$LOGIN_OUTPUT" '.data.user_id')"
    if [[ -n "$user_id" ]]; then
        log_success "Login output includes user_id=$user_id"
    else
        log_warn "Login output does not include user_id"
    fi

    local login_corr
    login_corr="$(json_get "$LOGIN_OUTPUT" '.correlation_id')"
    if [[ -z "$login_corr" ]]; then
        login_corr="$(json_get "$LOGIN_OUTPUT" '.data.correlation_id')"
    fi

    if [[ -n "$login_corr" ]]; then
        log_success "Login output includes correlation_id=$login_corr"
    else
        log_warn "No correlation_id found in login output"
    fi

    local proof_dir_from_output
    proof_dir_from_output="$(json_get "$LOGIN_OUTPUT" '.proof_dir')"
    if [[ -z "$proof_dir_from_output" ]]; then
        proof_dir_from_output="$(json_get "$LOGIN_OUTPUT" '.data.proof_dir')"
    fi
    if [[ -z "$proof_dir_from_output" ]]; then
        proof_dir_from_output="$(json_get "$LOGIN_OUTPUT" '.proof_bundle_dir')"
    fi
    if [[ -z "$proof_dir_from_output" ]]; then
        proof_dir_from_output="$(json_get "$LOGIN_OUTPUT" '.data.proof_bundle_dir')"
    fi

    if [[ -n "$proof_dir_from_output" ]]; then
        INFERRED_PROOF_DIR="$proof_dir_from_output"
        log_info "Login output provided proof directory: $INFERRED_PROOF_DIR"
    fi
}

# -----------------------------------------------------------------------------
# Layer 2 - Token Capture and Validation
# -----------------------------------------------------------------------------

capture_and_validate_token() {
    log_step "Layer 2 - Token Capture and Validation"

    CREDENTIALS_FILE="$KEYHOLE_HOME/credentials.json"

    if [[ ! -f "$CREDENTIALS_FILE" ]]; then
        log_fail "Credentials file not found: $CREDENTIALS_FILE"
        exit 1
    fi
    log_success "Credentials file exists"

    local perms=""
    perms="$(stat -c "%a" "$CREDENTIALS_FILE" 2>/dev/null || true)"
    if [[ -z "$perms" ]]; then
        perms="$(stat -f "%Lp" "$CREDENTIALS_FILE" 2>/dev/null || true)"
    fi

    if [[ "$perms" == "600" ]]; then
        log_success "Credentials file has secure permissions (600)"
    else
        log_warn "Credentials file permissions are '$perms' (expected 600)"
    fi

    TOKEN="$(json_file_get "$CREDENTIALS_FILE" '.access_token')"
    if [[ -z "$TOKEN" ]]; then
        TOKEN="$(json_file_get "$CREDENTIALS_FILE" '.session.access_token')"
    fi

    if [[ -z "$TOKEN" ]]; then
        log_fail "No access token found in credentials file"
        exit 1
    fi
    log_success "Access token extracted (length=${#TOKEN})"

    if [[ ${#TOKEN} -lt 20 ]]; then
        log_fail "Token appears malformed (too short)"
        exit 1
    fi
    log_success "Token passes basic format validation"

    local stored_mode
    stored_mode="$(json_file_get "$CREDENTIALS_FILE" '.mode')"
    if [[ -z "$stored_mode" ]]; then
        stored_mode="$(json_file_get "$CREDENTIALS_FILE" '.session.mode')"
    fi

    if [[ -n "$stored_mode" ]]; then
        log_success "Stored session mode present: $stored_mode"
    else
        log_warn "Stored session mode not found"
    fi

    local expires_at
    expires_at="$(json_file_get "$CREDENTIALS_FILE" '.expires_at')"
    if [[ -z "$expires_at" ]]; then
        expires_at="$(json_file_get "$CREDENTIALS_FILE" '.session.expires_at')"
    fi

    if [[ -n "$expires_at" ]]; then
        log_success "Stored session expiration present: $expires_at"
    else
        log_warn "Stored session expiration not found"
    fi

    export TOKEN
}

# -----------------------------------------------------------------------------
# Layer 3 - Whoami Verification via CLI
# -----------------------------------------------------------------------------

verify_whoami_cli() {
    log_step "Layer 3 - Whoami Verification (CLI)"

    if WHOAMI_OUTPUT="$(keyhole whoami --json 2>&1)"; then
        log_success "Whoami command completed successfully"
        debug "Whoami output: $WHOAMI_OUTPUT"
    else
        log_fail "Whoami command failed"
        echo "$WHOAMI_OUTPUT"
        exit 1
    fi

    local success
    success="$(json_get "$WHOAMI_OUTPUT" '.success')"
    if [[ "$success" != "true" ]]; then
        log_fail "Whoami reported success=false"
        echo "$WHOAMI_OUTPUT" | jq '.' 2>/dev/null || echo "$WHOAMI_OUTPUT"
        exit 1
    fi
    log_success "Whoami reported success=true"

    WHOAMI_USER_ID="$(json_get "$WHOAMI_OUTPUT" '.data.user_id')"
    if [[ -z "$WHOAMI_USER_ID" ]]; then
        WHOAMI_USER_ID="$(json_get "$WHOAMI_OUTPUT" '.user_id')"
    fi

    if [[ -n "$WHOAMI_USER_ID" ]]; then
        log_success "CLI whoami returned user_id=$WHOAMI_USER_ID"
    else
        log_fail "CLI whoami missing user_id"
        exit 1
    fi

    local tenant_id
    tenant_id="$(json_get "$WHOAMI_OUTPUT" '.data.tenant_id')"
    if [[ -z "$tenant_id" ]]; then
        tenant_id="$(json_get "$WHOAMI_OUTPUT" '.tenant_id')"
    fi

    if [[ -n "$tenant_id" ]]; then
        log_success "CLI whoami returned tenant_id=$tenant_id"
    else
        log_warn "CLI whoami missing tenant_id"
    fi

    WHOAMI_MODE="$(json_get "$WHOAMI_OUTPUT" '.data.mode')"
    if [[ -z "$WHOAMI_MODE" ]]; then
        WHOAMI_MODE="$(json_get "$WHOAMI_OUTPUT" '.mode')"
    fi

    if [[ -n "$WHOAMI_MODE" ]]; then
        log_success "CLI whoami returned mode=$WHOAMI_MODE"
    else
        log_fail "CLI whoami missing mode"
        exit 1
    fi

    local org_id workspace_id plan
    org_id="$(json_get "$WHOAMI_OUTPUT" '.data.org_id')"
    [[ -z "$org_id" ]] && org_id="$(json_get "$WHOAMI_OUTPUT" '.org_id')"

    workspace_id="$(json_get "$WHOAMI_OUTPUT" '.data.workspace_id')"
    [[ -z "$workspace_id" ]] && workspace_id="$(json_get "$WHOAMI_OUTPUT" '.workspace_id')"

    plan="$(json_get "$WHOAMI_OUTPUT" '.data.plan')"
    [[ -z "$plan" ]] && plan="$(json_get "$WHOAMI_OUTPUT" '.plan')"

    [[ -n "$org_id" ]] && log_info "CLI whoami org_id=$org_id"
    [[ -n "$workspace_id" ]] && log_info "CLI whoami workspace_id=$workspace_id"
    [[ -n "$plan" ]] && log_info "CLI whoami plan=$plan"

    export WHOAMI_USER_ID
    export WHOAMI_MODE
}

# -----------------------------------------------------------------------------
# Layer 4 - Direct MCP /whoami Call
# -----------------------------------------------------------------------------

verify_whoami_direct() {
    log_step "Layer 4 - Direct MCP /whoami Call"

    local raw
    raw="$(http_get "$MCP_BASE_URL/mcp/v1/whoami" "$TOKEN")"
    split_http_response "$raw"

    debug "HTTP_CODE=$HTTP_CODE"
    debug "HTTP_BODY=$HTTP_BODY"

    if [[ "$HTTP_CODE" == "200" ]]; then
        log_success "Direct MCP /whoami returned HTTP 200"
    else
        log_fail "Direct MCP /whoami returned HTTP $HTTP_CODE"
        echo "$HTTP_BODY"
        exit 1
    fi

    local direct_user_id
    direct_user_id="$(json_get "$HTTP_BODY" '.data.user_id')"
    if [[ -z "$direct_user_id" ]]; then
        direct_user_id="$(json_get "$HTTP_BODY" '.user_id')"
    fi

    if [[ -n "$direct_user_id" ]]; then
        log_success "Direct MCP /whoami returned user_id=$direct_user_id"
    else
        log_fail "Direct MCP /whoami missing user_id"
        echo "$HTTP_BODY" | jq '.' 2>/dev/null || echo "$HTTP_BODY"
        exit 1
    fi

    if [[ "$direct_user_id" == "$WHOAMI_USER_ID" ]]; then
        log_success "Direct /whoami user_id matches CLI whoami user_id"
    else
        log_fail "Identity mismatch: direct=$direct_user_id, cli=$WHOAMI_USER_ID"
        exit 1
    fi

    local direct_mode
    direct_mode="$(json_get "$HTTP_BODY" '.data.mode')"
    if [[ -z "$direct_mode" ]]; then
        direct_mode="$(json_get "$HTTP_BODY" '.mode')"
    fi

    if [[ -n "$direct_mode" ]]; then
        log_success "Direct MCP /whoami returned mode=$direct_mode"
    else
        log_fail "Direct MCP /whoami missing mode"
        exit 1
    fi

    if [[ "$direct_mode" == "$WHOAMI_MODE" ]]; then
        log_success "Direct /whoami mode matches CLI whoami mode"
    else
        log_fail "Mode mismatch: direct=$direct_mode, cli=$WHOAMI_MODE"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Layer 5 - Secondary Authenticated Endpoint
# -----------------------------------------------------------------------------

test_secondary_endpoint() {
    log_step "Layer 5 - Secondary Authenticated Endpoint"

    log_info "Testing secondary authenticated endpoint: $SECONDARY_AUTH_URL"

    local raw
    raw="$(http_post_json "$SECONDARY_AUTH_URL" "$SECONDARY_AUTH_PAYLOAD" "$TOKEN" || true)"
    split_http_response "$raw"

    debug "HTTP_CODE=$HTTP_CODE"
    debug "HTTP_BODY=$HTTP_BODY"

    case "$HTTP_CODE" in
        200)
            log_success "Secondary authenticated endpoint returned HTTP 200"
            ;;
        401)
            log_fail "Secondary authenticated endpoint rejected token with HTTP 401"
            exit 1
            ;;
        403)
            log_warn "Secondary authenticated endpoint returned HTTP 403 (auth recognized, scope may differ)"
            ;;
        404)
            log_warn "Secondary authenticated endpoint returned HTTP 404 (endpoint may not be deployed here)"
            ;;
        405)
            log_warn "Secondary authenticated endpoint returned HTTP 405 (method/path mismatch in this environment)"
            ;;
        *)
            log_warn "Secondary authenticated endpoint returned HTTP $HTTP_CODE"
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Layer 6 - Event Spine Verification (Optional)
# -----------------------------------------------------------------------------

verify_event_spine() {
    log_step "Layer 6 - Event Spine Verification"

    if [[ "$SKIP_EVENT_CHECK" == "true" ]]; then
        log_info "Skipping event spine verification (SKIP_EVENT_CHECK=true)"
        return 0
    fi

    local events_url="$MCP_BASE_URL/mcp/v1/events/query"
    local query_payload
    query_payload='{"types":["type:AUTH_SUCCESS"],"limit":5}'

    log_info "Querying event endpoint: $events_url"

    local raw
    raw="$(http_post_json "$events_url" "$query_payload" "$TOKEN" || true)"
    split_http_response "$raw"

    debug "HTTP_CODE=$HTTP_CODE"
    debug "HTTP_BODY=$HTTP_BODY"

    if [[ "$HTTP_CODE" == "200" ]]; then
        log_success "Event query endpoint returned HTTP 200"

        local event_count
        event_count="$(jq -r '
            (.events | length) //
            (.data.events | length) //
            (.results | length) //
            (.data.results | length) //
            0
        ' <<<"$HTTP_BODY" 2>/dev/null || echo "0")"

        if [[ "$event_count" =~ ^[0-9]+$ ]] && [[ "$event_count" -gt 0 ]]; then
            log_success "Found $event_count AUTH_SUCCESS event(s)"
        else
            if [[ "$EVENT_CHECK_REQUIRED" == "true" ]]; then
                log_fail "No AUTH_SUCCESS events found and EVENT_CHECK_REQUIRED=true"
                exit 1
            else
                log_warn "No AUTH_SUCCESS events found (known-gap-tolerant mode)"
            fi
        fi
    elif [[ "$HTTP_CODE" == "404" ]]; then
        if [[ "$EVENT_CHECK_REQUIRED" == "true" ]]; then
            log_fail "Event query endpoint unavailable (HTTP 404) and EVENT_CHECK_REQUIRED=true"
            exit 1
        else
            log_warn "Event query endpoint unavailable (HTTP 404)"
        fi
    elif [[ "$HTTP_CODE" == "401" || "$HTTP_CODE" == "403" ]]; then
        if [[ "$EVENT_CHECK_REQUIRED" == "true" ]]; then
            log_fail "Event query authorization insufficient (HTTP $HTTP_CODE) and EVENT_CHECK_REQUIRED=true"
            exit 1
        else
            log_warn "Event query authorization insufficient (HTTP $HTTP_CODE)"
        fi
    else
        if [[ "$EVENT_CHECK_REQUIRED" == "true" ]]; then
            log_fail "Event query returned HTTP $HTTP_CODE and EVENT_CHECK_REQUIRED=true"
            exit 1
        else
            log_warn "Event query returned HTTP $HTTP_CODE"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Layer 7 - Proof Bundle Verification
# -----------------------------------------------------------------------------

resolve_proof_dir() {
    if [[ -n "$PROOF_DIR" ]]; then
        echo "$PROOF_DIR"
        return 0
    fi

    if [[ -n "$INFERRED_PROOF_DIR" ]]; then
        echo "$INFERRED_PROOF_DIR"
        return 0
    fi

    if [[ -d "$KEYHOLE_HOME/proof_bundle" ]]; then
        echo "$KEYHOLE_HOME/proof_bundle"
        return 0
    fi

    if [[ -d "$KEYHOLE_HOME/proof" ]]; then
        echo "$KEYHOLE_HOME/proof"
        return 0
    fi

    echo ""
}

verify_proof_bundle() {
    log_step "Layer 7 - Proof Bundle Verification"

    local proof_dir
    proof_dir="$(resolve_proof_dir)"

    if [[ -z "$proof_dir" || ! -d "$proof_dir" ]]; then
        log_fail "Proof bundle directory not found"
        log_info "Tried explicit PROOF_DIR, login output, $KEYHOLE_HOME/proof_bundle, and $KEYHOLE_HOME/proof"
        exit 1
    fi

    log_success "Proof bundle directory exists: $proof_dir"
    log_info "Proof bundle contents:"
    ls -la "$proof_dir" 2>/dev/null || true

    local required_files=(
        "core.json"
        "event_chain.json"
        "identity_context.json"
        "verification_result.json"
    )

    local optional_files=(
        "request.json"
        "response.json"
        "correlation.json"
        "summary.md"
        "digest.txt"
    )

    local missing_required=0

    for file in "${required_files[@]}"; do
        if [[ -f "$proof_dir/$file" ]]; then
            log_success "Required proof file exists: $file"
        else
            log_fail "Required proof file missing: $file"
            missing_required=1
        fi
    done

    for file in "${optional_files[@]}"; do
        if [[ -f "$proof_dir/$file" ]]; then
            log_info "Optional proof file exists: $file"
        else
            debug "Optional proof file missing: $file"
        fi
    done

    if [[ "$missing_required" -ne 0 ]]; then
        exit 1
    fi

    if [[ -f "$proof_dir/core.json" ]]; then
        local proof_type
        proof_type="$(json_file_get "$proof_dir/core.json" '.proof_type')"
        if [[ "$proof_type" == "auth_bootstrap" ]]; then
            log_success "core.json proof_type=auth_bootstrap"
        else
            log_warn "core.json proof_type is '$proof_type'"
        fi

        local whoami_completed
        whoami_completed="$(json_file_get "$proof_dir/core.json" '.whoami_completed')"
        if [[ "$whoami_completed" == "true" ]]; then
            log_success "core.json confirms whoami_completed=true"
        else
            log_warn "core.json whoami_completed=$whoami_completed"
        fi
    fi

    if [[ -f "$proof_dir/identity_context.json" ]]; then
        local source
        source="$(json_file_get "$proof_dir/identity_context.json" '.source')"
        if [[ "$source" == "server/whoami" ]]; then
            log_success "identity_context.json source=server/whoami"
        else
            log_warn "identity_context.json source is '$source'"
        fi
    fi

    if [[ -f "$proof_dir/verification_result.json" ]]; then
        local governed_identity_confirmed
        governed_identity_confirmed="$(json_file_get "$proof_dir/verification_result.json" '.governed_identity_confirmed')"

        if [[ "$governed_identity_confirmed" == "true" ]]; then
            log_success "verification_result.json governed_identity_confirmed=true"
        else
            log_warn "verification_result.json governed_identity_confirmed=$governed_identity_confirmed"
        fi
    fi

    log_info "Checking proof bundle for secret leakage..."
    if grep -R -nE 'access_token|refresh_token|Bearer ' "$proof_dir" 2>/dev/null \
        | grep -vE 'token_acquired|token_type' \
        | head -3; then
        log_fail "Potential token leakage detected in proof bundle"
        exit 1
    else
        log_success "No obvious secret leakage detected in proof bundle"
    fi

    log_info "Checking correlation_id consistency across proof artifacts..."

    local correlation_ids=()

    for file in core.json event_chain.json correlation.json; do
        if [[ -f "$proof_dir/$file" ]]; then
            local cid
            cid="$(json_file_get "$proof_dir/$file" '.correlation_id')"
            if [[ -z "$cid" ]]; then
                cid="$(json_file_get "$proof_dir/$file" '.data.correlation_id')"
            fi
            if [[ -n "$cid" ]]; then
                correlation_ids+=("$cid")
            fi
        fi
    done

    if [[ ${#correlation_ids[@]} -gt 1 ]]; then
        local first_cid="${correlation_ids[0]}"
        local all_match="true"
        local cid
        for cid in "${correlation_ids[@]}"; do
            if [[ "$cid" != "$first_cid" ]]; then
                all_match="false"
                break
            fi
        done

        if [[ "$all_match" == "true" ]]; then
            log_success "correlation_id consistent across proof artifacts: $first_cid"
        else
            log_fail "correlation_id inconsistent across proof artifacts"
            printf '%s\n' "${correlation_ids[@]}"
            exit 1
        fi
    elif [[ ${#correlation_ids[@]} -eq 1 ]]; then
        log_success "correlation_id present in proof artifacts: ${correlation_ids[0]}"
    else
        log_warn "No correlation_id found in inspected proof artifacts"
    fi
}

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

print_summary() {
    echo ""
    echo -e "${BLUE}---------------------------------------------------------------${NC}"
    echo -e "${BLUE}                      SMOKE TEST SUMMARY                      ${NC}"
    echo -e "${BLUE}---------------------------------------------------------------${NC}"
    echo ""
    echo "  Total Checks:   $TOTAL_CHECKS"
    echo -e "  ${GREEN}Passed:${NC}         $PASSED_CHECKS"
    echo -e "  ${RED}Failed:${NC}         $FAILED_CHECKS"
    echo -e "  ${YELLOW}Warnings:${NC}       $WARNINGS"
    echo ""

    if [[ "$FAILED_CHECKS" -eq 0 ]]; then
        echo -e "${GREEN}---------------------------------------------------------------${NC}"
        echo -e "${GREEN}🎉 SMOKE TEST PASSED - Auth Bootstrap Working End-to-End${NC}"
        echo -e "${GREEN}---------------------------------------------------------------${NC}"
        return 0
    else
        echo -e "${RED}---------------------------------------------------------------${NC}"
        echo -e "${RED}💥 SMOKE TEST FAILED - $FAILED_CHECKS check(s) failed${NC}"
        echo -e "${RED}---------------------------------------------------------------${NC}"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    trap cleanup EXIT

    echo ""
    echo -e "${BLUE}---------------------------------------------------------------${NC}"
    echo -e "${BLUE}   SDK-CLIENT-01 Smoke Test: sdk-client-01-auth-bootstrap       ${NC}"
    echo -e "${BLUE}---------------------------------------------------------------${NC}"
    echo ""
    echo "  MCP Base URL:         $MCP_BASE_URL"
    echo "  Keyhole Home:         $KEYHOLE_HOME"
    echo "  Check Local Runtime:  $CHECK_LOCAL_RUNTIME"
    echo "  Local Runtime URL:    $LOCAL_RUNTIME_URL"
    echo "  Skip Event Check:     $SKIP_EVENT_CHECK"
    echo "  Event Check Required: $EVENT_CHECK_REQUIRED"
    echo "  Secondary Auth URL:   $SECONDARY_AUTH_URL"
    echo "  Debug Mode:           $DEBUG"
    echo ""

    check_prerequisites
    probe_local_runtime
    run_cli_login
    capture_and_validate_token
    verify_whoami_cli
    verify_whoami_direct
    test_secondary_endpoint
    verify_event_spine
    verify_proof_bundle
    print_summary
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
