CREATE TYPE public.billingperiod AS ENUM (
    'MONTHLY',
    'YEARLY',
    'LIFETIME'
);

CREATE TYPE public.licensestatus AS ENUM (
    'active',
    'inactive',
    'expired',
    'disabled'
);

CREATE TYPE public.orderstatus AS ENUM (
    'pending',
    'paid',
    'failed',
    'refunded',
    'partial_refund'
);

CREATE TYPE public.refundrequeststatus AS ENUM (
    'pending',
    'approved',
    'rejected'
);

CREATE TYPE public.refundstatus AS ENUM (
    'pending',
    'completed',
    'failed'
);

CREATE TYPE public.subscriptionstatus AS ENUM (
    'ACTIVE',
    'CANCELLED',
    'EXPIRED',
    'TRIAL',
    'SUSPENDED',
    'past_due',
    'paused'
);

CREATE TYPE public.templatetype AS ENUM (
    'workspace_invitation',
    'invitation_accepted',
    'role_changed',
    'member_removed',
    'welcome'
);

CREATE FUNCTION public.enforce_single_workspace_owner() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.workspace_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM roles WHERE id = NEW.role_id AND name = 'workspace_owner')
       AND EXISTS (
           SELECT 1 FROM user_roles ur
           JOIN roles r ON r.id = ur.role_id
           WHERE ur.workspace_id = NEW.workspace_id
             AND r.name = 'workspace_owner'
             AND ur.id <> NEW.id
       )
    THEN
        RAISE EXCEPTION 'workspace % already has a workspace_owner', NEW.workspace_id
            USING ERRCODE = 'unique_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TABLE public.account_creation_ip_allowlist (
    id uuid NOT NULL,
    ip_address character varying(64) NOT NULL,
    label character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.account_recovery_requests (
    id uuid NOT NULL,
    user_id uuid,
    email character varying(255) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    request_note text,
    review_note text,
    requested_ip character varying(64),
    requested_user_agent character varying(512),
    reviewed_by_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    reviewed_at timestamp with time zone
);

CREATE TABLE public.api_usage_hourly (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    hour_bucket timestamp with time zone NOT NULL,
    request_count integer DEFAULT 0 NOT NULL,
    error_count integer DEFAULT 0 NOT NULL,
    total_duration_ms bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.api_usage_rollup_state (
    id integer NOT NULL,
    settled_through timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_api_usage_rollup_state_single_row CHECK ((id = 1))
);

CREATE SEQUENCE public.api_usage_rollup_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.api_usage_rollup_state_id_seq OWNED BY public.api_usage_rollup_state.id;

CREATE TABLE public.audit_logs (
    id uuid NOT NULL,
    user_id uuid,
    user_email character varying(255),
    action character varying(100) NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id character varying(255),
    workspace_id uuid,
    ip_address inet,
    user_agent text,
    request_id character varying(255),
    old_values jsonb,
    new_values jsonb,
    audit_metadata jsonb,
    status character varying(20),
    error_message text,
    created_at timestamp with time zone NOT NULL,
    full_name character varying(200)
);

CREATE TABLE public.brand_voice (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    about text,
    customer_profile text,
    selling_position text,
    target_audience jsonb,
    brand_voice jsonb,
    competitors jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    content_pillar jsonb,
    brand_name character varying(255),
    site_compliance jsonb
);

CREATE TABLE public.content (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    title text NOT NULL,
    slug text NOT NULL,
    body_markdown text,
    body_html text,
    status text DEFAULT 'draft'::text,
    content_language text DEFAULT 'English'::text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    deleted_at timestamp with time zone,
    langgraph_thread_id uuid,
    introduction text,
    tags text[],
    images_data jsonb,
    links_data jsonb,
    schema_markup jsonb,
    wordpress_post_id integer,
    wordpress_url text,
    wordpress_published_at timestamp with time zone,
    shopify_article_id bigint,
    shopify_article_url text,
    shopify_published_at timestamp with time zone,
    category text,
    persona_id uuid
);

COMMENT ON COLUMN public.content.tags IS 'Tags (common to content)';

COMMENT ON COLUMN public.content.images_data IS 'Inline images data';

COMMENT ON COLUMN public.content.links_data IS 'Internal and outbound links';

COMMENT ON COLUMN public.content.schema_markup IS 'Structured data/schema markup';

COMMENT ON COLUMN public.content.category IS 'WordPress category name';

COMMENT ON COLUMN public.content.persona_id IS 'Author persona selected during the content outline step';

CREATE TABLE public.content_publishing_results (
    content_id uuid NOT NULL,
    site_id uuid NOT NULL,
    wp_post_id integer,
    shopify_article_id bigint,
    shopify_blog_id bigint,
    external_url character varying,
    status character varying NOT NULL,
    last_synced_at timestamp with time zone,
    sync_error text,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    scheduled_publish_at timestamp with time zone,
    retry_count integer DEFAULT 0 NOT NULL
);

CREATE TABLE public.content_seo_data (
    content_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    meta_title text,
    meta_description text,
    focus_keyphrase text,
    keyphrase_density double precision,
    secondary_keywords text[],
    search_intent text[],
    seo_score double precision,
    readability_score double precision,
    seo_details text,
    trust_score double precision
);

COMMENT ON COLUMN public.content_seo_data.meta_title IS 'Meta title (50-60 chars)';

COMMENT ON COLUMN public.content_seo_data.meta_description IS 'Meta description (150-160 chars)';

COMMENT ON COLUMN public.content_seo_data.focus_keyphrase IS 'Primary focus keyphrase';

COMMENT ON COLUMN public.content_seo_data.keyphrase_density IS 'Keyphrase density percentage';

COMMENT ON COLUMN public.content_seo_data.secondary_keywords IS 'Secondary keywords';

COMMENT ON COLUMN public.content_seo_data.search_intent IS 'informational, navigational, etc.';

COMMENT ON COLUMN public.content_seo_data.seo_details IS 'Detailed SEO analysis/feedback';

COMMENT ON COLUMN public.content_seo_data.trust_score IS 'Trust score of the content';

CREATE TABLE public.customer_notes (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    admin_id uuid,
    note text NOT NULL,
    category character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);

CREATE TABLE public.discount_usage (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    discount_code character varying(100) NOT NULL,
    discount_amount numeric(10,2),
    discount_amount_type character varying(20),
    subscription_id uuid,
    order_id character varying(255),
    lemonsqueezy_discount_id character varying(255),
    applied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    usage_metadata jsonb
);

COMMENT ON COLUMN public.discount_usage.discount_amount IS 'Amount saved (in currency or percentage)';

COMMENT ON COLUMN public.discount_usage.discount_amount_type IS 'Type: ''percent'' or ''fixed''';

COMMENT ON COLUMN public.discount_usage.order_id IS 'LemonSqueezy order ID';

COMMENT ON COLUMN public.discount_usage.lemonsqueezy_discount_id IS 'LemonSqueezy discount ID';

COMMENT ON COLUMN public.discount_usage.usage_metadata IS 'Additional discount information from LemonSqueezy';

CREATE TABLE public.email_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email_log_id uuid,
    provider character varying(50) NOT NULL,
    provider_event_id character varying(255) NOT NULL,
    provider_message_id character varying(255) NOT NULL,
    event_type character varying(50) NOT NULL,
    event_data jsonb,
    received_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.email_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    workspace_id uuid,
    user_id uuid,
    template_type character varying(100),
    provider character varying(50) NOT NULL,
    provider_message_id character varying(255),
    to_email character varying(255) NOT NULL,
    from_email character varying(255) NOT NULL,
    subject character varying(500) NOT NULL,
    status character varying(50) DEFAULT 'queued'::character varying NOT NULL,
    error_message text,
    sent_at timestamp with time zone,
    delivered_at timestamp with time zone,
    failed_at timestamp with time zone,
    provider_response jsonb,
    tags jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    html_content text
);

CREATE TABLE public.email_preferences (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    workspace_invitation boolean DEFAULT true NOT NULL,
    invitation_accepted boolean DEFAULT true NOT NULL,
    role_changed boolean DEFAULT true NOT NULL,
    member_removed boolean DEFAULT true NOT NULL,
    marketing boolean DEFAULT false NOT NULL,
    unsubscribe_token character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    content_generation_started boolean DEFAULT true NOT NULL,
    content_generation_completed boolean DEFAULT true NOT NULL,
    content_generation_failed boolean DEFAULT true NOT NULL,
    content_published boolean DEFAULT true NOT NULL,
    payment_succeeded boolean DEFAULT true NOT NULL,
    payment_failed boolean DEFAULT true NOT NULL,
    subscription_cancelled boolean DEFAULT true NOT NULL,
    subscription_expiring_soon boolean DEFAULT true NOT NULL,
    trial_ending_soon boolean DEFAULT true NOT NULL,
    usage_limit_warning boolean DEFAULT true NOT NULL,
    usage_limit_exceeded boolean DEFAULT true NOT NULL,
    kb_processing_completed boolean DEFAULT true NOT NULL,
    kb_processing_failed boolean DEFAULT true NOT NULL,
    digest_enabled boolean DEFAULT false NOT NULL,
    digest_frequency character varying(20) DEFAULT '''weekly'''::character varying NOT NULL
);

CREATE TABLE public.email_templates (
    id uuid NOT NULL,
    workspace_id uuid,
    template_type public.templatetype NOT NULL,
    subject character varying(255) NOT NULL,
    body text NOT NULL,
    is_active boolean,
    is_default boolean,
    created_by_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);

CREATE TABLE public.error_logs (
    id uuid NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    severity character varying(8) NOT NULL,
    message text NOT NULL,
    source character varying(255),
    user_id uuid,
    request_id character varying(100),
    stack_trace text,
    metadata jsonb DEFAULT '{}'::jsonb,
    resolved boolean DEFAULT false,
    resolved_at timestamp with time zone,
    resolved_by uuid,
    -- As the migration wrote it: pg_dump's form re-parses into a different (equivalent) expression.
    CONSTRAINT error_log_severity CHECK (severity IN ('error', 'warning', 'critical'))
);

CREATE TABLE public.impersonation_sessions (
    id uuid NOT NULL,
    session_id character varying(255) NOT NULL,
    is_valid boolean NOT NULL,
    invalidated_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.integrations (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    integration_type character varying(50) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    site_url character varying(500),
    api_endpoint character varying(500),
    username character varying(255),
    app_password character varying,
    api_key character varying,
    config_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    deleted_at timestamp with time zone
);

COMMENT ON COLUMN public.integrations.site_url IS 'Integration site URL';

COMMENT ON COLUMN public.integrations.api_endpoint IS 'Provider-specific API endpoint';

COMMENT ON COLUMN public.integrations.username IS 'Provider username';

COMMENT ON COLUMN public.integrations.app_password IS 'Provider application password (encrypted)';

COMMENT ON COLUMN public.integrations.api_key IS 'Provider API key or token (encrypted)';

COMMENT ON COLUMN public.integrations.config_json IS 'Additional integration configuration and settings';

CREATE TABLE public.knowledge_base (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    type character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    created_by_user_id uuid
);

CREATE TABLE public.knowledge_files (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    file_name character varying NOT NULL,
    file_type character varying NOT NULL,
    file_size integer NOT NULL,
    file_path character varying NOT NULL,
    status character varying DEFAULT 'completed'::character varying NOT NULL,
    char_count integer,
    word_count integer,
    created_at timestamp with time zone NOT NULL,
    file_hash character varying(64),
    mime_type character varying(100),
    chunk_count integer,
    knowledge_base_id uuid NOT NULL,
    updated_at timestamp with time zone
);

CREATE TABLE public.license_activations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    license_id uuid NOT NULL,
    instance_id character varying(255) NOT NULL,
    instance_name character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    activated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    deactivated_at timestamp with time zone,
    last_checked_at timestamp with time zone,
    activation_metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);

COMMENT ON COLUMN public.license_activations.instance_id IS 'Device ID, domain, or unique instance identifier';

COMMENT ON COLUMN public.license_activations.instance_name IS 'Human-readable name for the instance';

COMMENT ON COLUMN public.license_activations.last_checked_at IS 'Last time this activation was validated/checked';

COMMENT ON COLUMN public.license_activations.activation_metadata IS 'Additional info: IP, user agent, OS, etc.';

CREATE TABLE public.licenses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    license_key character varying(255) NOT NULL,
    lemonsqueezy_license_id character varying(255) NOT NULL,
    lemonsqueezy_order_id character varying(255) NOT NULL,
    lemonsqueezy_product_id character varying(255) NOT NULL,
    product_name character varying(255) NOT NULL,
    status public.licensestatus DEFAULT 'inactive'::public.licensestatus NOT NULL,
    activation_email character varying(255) NOT NULL,
    activation_limit integer,
    activation_count integer DEFAULT 0 NOT NULL,
    activated_at timestamp with time zone,
    expires_at timestamp with time zone,
    license_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.notification_preferences (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    email_notifications boolean DEFAULT true NOT NULL,
    in_app_notifications boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    digest_enabled boolean DEFAULT true NOT NULL,
    digest_frequency character varying(20) DEFAULT 'daily'::character varying NOT NULL,
    marketing_updates boolean DEFAULT false NOT NULL,
    unsubscribe_token character varying NOT NULL,
    category_preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    digest_last_sent_at timestamp with time zone
);

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    workspace_id uuid,
    title character varying(255) NOT NULL,
    message text NOT NULL,
    type character varying(50) NOT NULL,
    category character varying(50),
    priority character varying(20) NOT NULL,
    status character varying(20) NOT NULL,
    is_read boolean NOT NULL,
    read_at timestamp with time zone,
    deleted_at timestamp with time zone,
    payload jsonb,
    action_url text,
    action_label character varying(100),
    sent_via_email boolean NOT NULL,
    sent_via_sse boolean NOT NULL,
    email_sent_at timestamp with time zone,
    sse_sent_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

COMMENT ON COLUMN public.notifications.type IS 'Type of notification';

COMMENT ON COLUMN public.notifications.category IS 'Specific notification category';

COMMENT ON COLUMN public.notifications.deleted_at IS 'Soft delete timestamp. NULL = active, non-NULL = deleted.';

CREATE TABLE public.oauth_accounts (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    provider character varying(50) NOT NULL,
    provider_account_id character varying(255) NOT NULL,
    provider_account_email character varying(255),
    access_token text,
    refresh_token text,
    token_expires_at timestamp with time zone,
    provider_username character varying(255),
    provider_profile_url character varying(500),
    provider_avatar_url character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    last_used_at timestamp with time zone
);

CREATE TABLE public.orders (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    subscription_id uuid,
    lemonsqueezy_order_id character varying(255) NOT NULL,
    lemonsqueezy_customer_id character varying(255),
    lemonsqueezy_subscription_id character varying(255),
    lemonsqueezy_product_id character varying(255),
    lemonsqueezy_variant_id character varying(255),
    product_name character varying(255),
    total integer DEFAULT 0 NOT NULL,
    subtotal integer,
    tax integer,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    status public.orderstatus DEFAULT 'pending'::public.orderstatus NOT NULL,
    receipt_url character varying(1024),
    refunded_at timestamp with time zone,
    ordered_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.payment_methods (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    provider_payment_method_id character varying(255) NOT NULL,
    provider_customer_id character varying(255) NOT NULL,
    type character varying(50) NOT NULL,
    is_default boolean NOT NULL,
    status character varying(50) NOT NULL,
    card_brand character varying(50),
    card_last4 character varying(4),
    card_exp_month integer,
    card_exp_year integer,
    billing_email character varying(255),
    payment_metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);

CREATE TABLE public.permissions (
    id uuid NOT NULL,
    name character varying(150) NOT NULL,
    display_name character varying(200),
    description text,
    resource character varying(50),
    action character varying(50),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    is_system boolean DEFAULT false NOT NULL
);

CREATE TABLE public.persona (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    demographics text,
    pain_points text,
    goals text,
    behaviors text,
    custom_metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    full_name character varying(255),
    professional_title character varying(255),
    areas_of_expertise jsonb,
    tone_of_voice character varying(255),
    bio text,
    linkedin_url character varying(500),
    avatar_url character varying(500),
    avatar_source character varying(20),
    email character varying(320),
    -- As the migration wrote it: pg_dump's form re-parses into a different (equivalent) expression.
    CONSTRAINT ck_persona_avatar_source CHECK (avatar_source IS NULL OR avatar_source IN ('custom', 'page', 'gravatar', 'generated'))
);

CREATE TABLE public.platform_admin_invitations (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    invitation_token character varying(255) NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    admin_role character varying(50) NOT NULL,
    permissions jsonb,
    message text,
    invited_by_admin_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    accepted_at timestamp with time zone,
    accepted_by_user_id uuid,
    declined_at timestamp with time zone,
    declined_reason text,
    revoked_at timestamp with time zone,
    revoked_by_admin_id uuid,
    revoked_reason text
);

COMMENT ON TABLE public.platform_admin_invitations IS 'Platform admin invitations - For inviting platform-level administrators';

COMMENT ON COLUMN public.platform_admin_invitations.id IS 'Unique identifier for the admin invitation';

COMMENT ON COLUMN public.platform_admin_invitations.email IS 'Email address of the invited admin';

COMMENT ON COLUMN public.platform_admin_invitations.invitation_token IS 'Secure token for invitation acceptance';

COMMENT ON COLUMN public.platform_admin_invitations.status IS 'Invitation status: pending, accepted, revoked, expired, declined';

COMMENT ON COLUMN public.platform_admin_invitations.admin_role IS 'Admin role to assign: super_admin, support_admin, etc.';

COMMENT ON COLUMN public.platform_admin_invitations.permissions IS 'Optional: Additional permissions beyond standard role (JSONB)';

COMMENT ON COLUMN public.platform_admin_invitations.message IS 'Optional personalized message from inviter';

COMMENT ON COLUMN public.platform_admin_invitations.invited_by_admin_id IS 'Admin who sent the invitation';

COMMENT ON COLUMN public.platform_admin_invitations.created_at IS 'When invitation was created';

COMMENT ON COLUMN public.platform_admin_invitations.expires_at IS 'When invitation expires';

COMMENT ON COLUMN public.platform_admin_invitations.accepted_at IS 'When invitation was accepted';

COMMENT ON COLUMN public.platform_admin_invitations.accepted_by_user_id IS 'User who accepted the invitation';

COMMENT ON COLUMN public.platform_admin_invitations.declined_at IS 'When invitation was declined (if declined)';

COMMENT ON COLUMN public.platform_admin_invitations.declined_reason IS 'Reason for declining (optional)';

COMMENT ON COLUMN public.platform_admin_invitations.revoked_at IS 'When invitation was revoked';

COMMENT ON COLUMN public.platform_admin_invitations.revoked_by_admin_id IS 'Admin who revoked the invitation';

COMMENT ON COLUMN public.platform_admin_invitations.revoked_reason IS 'Reason for revoking (optional)';

CREATE TABLE public.refund_requests (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    order_id uuid NOT NULL,
    lemonsqueezy_order_id character varying(255) NOT NULL,
    requested_amount integer NOT NULL,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    reason text NOT NULL,
    status public.refundrequeststatus DEFAULT 'pending'::public.refundrequeststatus NOT NULL,
    reviewed_by_user_id uuid,
    admin_note text,
    reviewed_at timestamp with time zone,
    refund_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE public.refunds (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    subscription_id uuid,
    lemonsqueezy_order_id character varying NOT NULL,
    lemonsqueezy_refund_id character varying,
    refund_amount integer NOT NULL,
    original_amount integer NOT NULL,
    currency character varying(3) DEFAULT 'USD'::character varying NOT NULL,
    reason text,
    status public.refundstatus DEFAULT 'pending'::public.refundstatus NOT NULL,
    is_partial boolean DEFAULT false NOT NULL,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.role_permissions (
    id uuid NOT NULL,
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.roles (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(150) NOT NULL,
    description text,
    hierarchy_level integer,
    is_system_role boolean,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    is_workspace_role boolean NOT NULL
);

CREATE TABLE public.shopify_app_installs (
    id uuid NOT NULL,
    shop_url character varying(255) NOT NULL,
    access_token text NOT NULL,
    scopes character varying,
    workspace_id uuid,
    linked_by uuid,
    linked_at timestamp with time zone,
    installed_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.subscription_plans (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(150) NOT NULL,
    description text,
    price_monthly numeric(10,2),
    price_yearly numeric(10,2),
    features jsonb,
    max_workspaces integer,
    max_members_per_workspace integer,
    max_topics integer,
    max_knowledge_items integer,
    max_api_calls_per_month integer,
    is_active boolean,
    is_public boolean,
    provider_price_id_monthly character varying(255),
    provider_price_id_yearly character varying(255),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    lemonsqueezy_product_id character varying(255),
    lemonsqueezy_variant_id_monthly character varying(255),
    lemonsqueezy_variant_id_yearly character varying(255),
    lemonsqueezy_store_id character varying(255),
    credits_per_month integer,
    is_trial_plan boolean DEFAULT false NOT NULL
);

CREATE TABLE public.text_knowledge (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    title character varying DEFAULT 'Untitled Note'::character varying NOT NULL,
    content text NOT NULL,
    tags jsonb,
    custom_metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    knowledge_base_id uuid NOT NULL
);

CREATE TABLE public.token_blacklist (
    id uuid NOT NULL,
    jti character varying(255) NOT NULL,
    token_type character varying(20) NOT NULL,
    user_id uuid NOT NULL,
    revoked_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    reason character varying(100),
    updated_at timestamp with time zone
);

CREATE TABLE public.trial_conversions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    trial_started_at timestamp with time zone NOT NULL,
    trial_ended_at timestamp with time zone NOT NULL,
    converted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    trial_duration_days integer NOT NULL,
    conversion_plan_id uuid,
    conversion_billing_period character varying(20) NOT NULL,
    conversion_amount numeric(10,2),
    conversion_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);

COMMENT ON COLUMN public.trial_conversions.trial_started_at IS 'When the trial started';

COMMENT ON COLUMN public.trial_conversions.trial_ended_at IS 'When the trial ended';

COMMENT ON COLUMN public.trial_conversions.converted_at IS 'When trial converted to paid';

COMMENT ON COLUMN public.trial_conversions.trial_duration_days IS 'Total trial duration in days';

COMMENT ON COLUMN public.trial_conversions.conversion_plan_id IS 'Plan user converted to';

COMMENT ON COLUMN public.trial_conversions.conversion_billing_period IS 'Monthly or yearly';

COMMENT ON COLUMN public.trial_conversions.conversion_amount IS 'First payment amount';

COMMENT ON COLUMN public.trial_conversions.conversion_metadata IS 'Additional conversion data (discount code, source, etc.)';

CREATE TABLE public.user_invitations (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    workspace_id uuid NOT NULL,
    role_id uuid NOT NULL,
    invited_by_user_id uuid,
    invitation_token character varying(255) NOT NULL,
    status character varying(50),
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    reminder_sent boolean DEFAULT false NOT NULL,
    accepted_at timestamp with time zone
);

CREATE TABLE public.user_onboarding (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    completed boolean DEFAULT false NOT NULL,
    current_step integer DEFAULT 0 NOT NULL,
    completed_steps json DEFAULT '[]'::json NOT NULL,
    skipped_steps json DEFAULT '[]'::json NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    user_industry character varying(100),
    user_role character varying(100),
    user_goal text,
    heard_from character varying(100)
);

CREATE TABLE public.user_preferences (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    theme character varying(20) DEFAULT 'system'::character varying,
    date_format character varying(20) DEFAULT 'iso'::character varying,
    time_format character varying(20) DEFAULT '24h'::character varying,
    items_per_page integer DEFAULT 25,
    sidebar_collapsed boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.user_roles (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    role_id uuid NOT NULL,
    workspace_id uuid,
    assigned_by_user_id uuid,
    is_primary boolean,
    assigned_at timestamp with time zone NOT NULL
);

CREATE TABLE public.user_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    jti character varying(255) NOT NULL,
    device_name character varying(255),
    device_type character varying(50),
    user_agent text,
    ip_address character varying(45),
    country character varying(100),
    city character varying(100),
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_activity_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    session_metadata jsonb
);

CREATE TABLE public.user_subscriptions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    status public.subscriptionstatus NOT NULL,
    billing_period public.billingperiod NOT NULL,
    start_date timestamp with time zone NOT NULL,
    end_date timestamp with time zone,
    trial_end_date timestamp with time zone,
    cancelled_at timestamp with time zone,
    provider_subscription_id character varying(255),
    provider_customer_id character varying(255),
    current_api_calls integer,
    usage_reset_date timestamp with time zone,
    subscription_metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    lemonsqueezy_subscription_id character varying(255),
    lemonsqueezy_customer_id character varying(255),
    lemonsqueezy_order_id character varying(255),
    lemonsqueezy_product_id character varying(255),
    lemonsqueezy_variant_id character varying(255),
    renews_at timestamp with time zone,
    ends_at timestamp with time zone,
    cancel_at_period_end boolean DEFAULT false NOT NULL,
    grace_period_end timestamp with time zone,
    payment_failed_at timestamp with time zone,
    cancellation_reason text,
    current_credits integer DEFAULT 0 NOT NULL,
    credits_reset_date timestamp with time zone
);

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255),
    display_name character varying(200),
    password_changed_at timestamp with time zone,
    locked_until timestamp with time zone,
    reset_token text,
    status character varying(20),
    email_verified boolean,
    email_verified_at timestamp with time zone,
    last_login_at timestamp with time zone,
    login_count integer,
    failed_login_attempts integer,
    language character varying(10),
    timezone character varying(50),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    deleted_at timestamp with time zone,
    avatar_url character varying(500),
    deactivated_at timestamp with time zone,
    provider_customer_id character varying(255),
    bio character varying(500),
    full_name character varying(200),
    registration_device_fingerprint character varying(16)
);

COMMENT ON COLUMN public.users.deleted_at IS 'Soft delete timestamp. NULL = active, non-NULL = deleted.';

CREATE TABLE public.webhook_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_id character varying(255) NOT NULL,
    event_name character varying(100) NOT NULL,
    payload jsonb NOT NULL,
    processed boolean NOT NULL,
    processed_at timestamp with time zone,
    error_message text,
    retry_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.website (
    id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    url character varying NOT NULL,
    status character varying DEFAULT 'process'::character varying NOT NULL,
    char_count integer,
    word_count integer,
    knowledge_base_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    title character varying(255)
);

CREATE TABLE public.workspace (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name character varying NOT NULL,
    slug character varying NOT NULL,
    url character varying,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone,
    timezone character varying(50),
    deleted_at timestamp with time zone,
    deleted_by uuid
);

CREATE TABLE public.workspace_members (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    workspace_id uuid NOT NULL,
    invitation_id uuid,
    status character varying(50) NOT NULL,
    is_default boolean NOT NULL,
    joined_at timestamp with time zone NOT NULL,
    last_activity_at timestamp with time zone
);

ALTER TABLE ONLY public.api_usage_rollup_state ALTER COLUMN id SET DEFAULT nextval('public.api_usage_rollup_state_id_seq'::regclass);

ALTER TABLE ONLY public.account_creation_ip_allowlist
    ADD CONSTRAINT account_creation_ip_allowlist_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.account_recovery_requests
    ADD CONSTRAINT account_recovery_requests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.api_usage_hourly
    ADD CONSTRAINT api_usage_hourly_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.api_usage_rollup_state
    ADD CONSTRAINT api_usage_rollup_state_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_id_key UNIQUE (id);

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.brand_voice
    ADD CONSTRAINT brand_voice_id_key UNIQUE (id);

ALTER TABLE ONLY public.brand_voice
    ADD CONSTRAINT brand_voice_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.content
    ADD CONSTRAINT content_id_key UNIQUE (id);

ALTER TABLE ONLY public.content
    ADD CONSTRAINT content_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.content_publishing_results
    ADD CONSTRAINT content_publishing_results_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.content_seo_data
    ADD CONSTRAINT content_seo_data_pkey PRIMARY KEY (content_id);

ALTER TABLE ONLY public.customer_notes
    ADD CONSTRAINT customer_notes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.discount_usage
    ADD CONSTRAINT discount_usage_id_key UNIQUE (id);

ALTER TABLE ONLY public.discount_usage
    ADD CONSTRAINT discount_usage_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.email_events
    ADD CONSTRAINT email_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.email_events
    ADD CONSTRAINT email_events_provider_event_id_key UNIQUE (provider_event_id);

ALTER TABLE ONLY public.email_logs
    ADD CONSTRAINT email_logs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_unsubscribe_token_key UNIQUE (unsubscribe_token);

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_user_id_key UNIQUE (user_id);

ALTER TABLE ONLY public.email_templates
    ADD CONSTRAINT email_templates_id_key UNIQUE (id);

ALTER TABLE ONLY public.email_templates
    ADD CONSTRAINT email_templates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.impersonation_sessions
    ADD CONSTRAINT impersonation_sessions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_id_key UNIQUE (id);

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.knowledge_base
    ADD CONSTRAINT knowledge_base_id_key UNIQUE (id);

ALTER TABLE ONLY public.knowledge_base
    ADD CONSTRAINT knowledge_base_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.knowledge_files
    ADD CONSTRAINT knowledge_files_id_key UNIQUE (id);

ALTER TABLE ONLY public.knowledge_files
    ADD CONSTRAINT knowledge_files_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.license_activations
    ADD CONSTRAINT license_activations_id_key UNIQUE (id);

ALTER TABLE ONLY public.license_activations
    ADD CONSTRAINT license_activations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_id_key UNIQUE (id);

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_id_key UNIQUE (id);

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.oauth_accounts
    ADD CONSTRAINT oauth_accounts_id_key UNIQUE (id);

ALTER TABLE ONLY public.oauth_accounts
    ADD CONSTRAINT oauth_accounts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT payment_methods_id_key UNIQUE (id);

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT payment_methods_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_id_key UNIQUE (id);

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_name_key UNIQUE (name);

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.persona
    ADD CONSTRAINT persona_id_key UNIQUE (id);

ALTER TABLE ONLY public.persona
    ADD CONSTRAINT persona_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.platform_admin_invitations
    ADD CONSTRAINT platform_admin_invitations_id_key UNIQUE (id);

ALTER TABLE ONLY public.platform_admin_invitations
    ADD CONSTRAINT platform_admin_invitations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.refund_requests
    ADD CONSTRAINT refund_requests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_id_key UNIQUE (id);

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_id_key UNIQUE (id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_name_key UNIQUE (name);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.shopify_app_installs
    ADD CONSTRAINT shopify_app_installs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.shopify_app_installs
    ADD CONSTRAINT shopify_app_installs_shop_url_key UNIQUE (shop_url);

ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_id_key UNIQUE (id);

ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_name_key UNIQUE (name);

ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.text_knowledge
    ADD CONSTRAINT text_knowledge_id_key UNIQUE (id);

ALTER TABLE ONLY public.text_knowledge
    ADD CONSTRAINT text_knowledge_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.token_blacklist
    ADD CONSTRAINT token_blacklist_jti_key UNIQUE (jti);

ALTER TABLE ONLY public.token_blacklist
    ADD CONSTRAINT token_blacklist_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.trial_conversions
    ADD CONSTRAINT trial_conversions_id_key UNIQUE (id);

ALTER TABLE ONLY public.trial_conversions
    ADD CONSTRAINT trial_conversions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.account_creation_ip_allowlist
    ADD CONSTRAINT uq_account_creation_ip_allowlist_ip UNIQUE (ip_address);

ALTER TABLE ONLY public.api_usage_hourly
    ADD CONSTRAINT uq_api_usage_hour UNIQUE (hour_bucket);

ALTER TABLE ONLY public.content_publishing_results
    ADD CONSTRAINT uq_content_publishing_result_content_site UNIQUE (content_id, site_id);

ALTER TABLE ONLY public.content
    ADD CONSTRAINT uq_content_workspace_slug UNIQUE (workspace_id, slug);

ALTER TABLE ONLY public.content
    ADD CONSTRAINT uq_content_workspace_title UNIQUE (workspace_id, title);

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT uq_email_workspace UNIQUE (email, workspace_id);

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT uq_notification_preferences_unsubscribe_token UNIQUE (unsubscribe_token);

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT uq_notification_preferences_user_id UNIQUE (user_id);

ALTER TABLE ONLY public.oauth_accounts
    ADD CONSTRAINT uq_provider_account UNIQUE (provider, provider_account_id);

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT uq_provider_payment_method_id UNIQUE (provider_payment_method_id);

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT uq_role_permission UNIQUE (role_id, permission_id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT uq_roles_name UNIQUE (name);

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT uq_user_preferences_user_id UNIQUE (user_id);

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT uq_user_role_workspace UNIQUE (user_id, role_id, workspace_id);

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT uq_user_workspace UNIQUE (user_id, workspace_id);

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_id_key UNIQUE (id);

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_invitation_token_key UNIQUE (invitation_token);

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_onboarding
    ADD CONSTRAINT user_onboarding_id_key UNIQUE (id);

ALTER TABLE ONLY public.user_onboarding
    ADD CONSTRAINT user_onboarding_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_id_key UNIQUE (id);

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_jti_key UNIQUE (jti);

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_id_key UNIQUE (id);

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_stripe_subscription_id_key UNIQUE (provider_subscription_id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_id_key UNIQUE (id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.webhook_events
    ADD CONSTRAINT webhook_events_id_key UNIQUE (id);

ALTER TABLE ONLY public.webhook_events
    ADD CONSTRAINT webhook_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.website
    ADD CONSTRAINT website_id_key UNIQUE (id);

ALTER TABLE ONLY public.website
    ADD CONSTRAINT website_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.workspace
    ADD CONSTRAINT workspace_id_key UNIQUE (id);

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_id_key UNIQUE (id);

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.workspace
    ADD CONSTRAINT workspace_pkey PRIMARY KEY (id);

CREATE INDEX idx_audit_logs_action ON public.audit_logs USING btree (action);

CREATE INDEX idx_audit_logs_created_at ON public.audit_logs USING btree (created_at);

CREATE INDEX idx_audit_logs_resource_id ON public.audit_logs USING btree (resource_id);

CREATE INDEX idx_audit_logs_resource_type ON public.audit_logs USING btree (resource_type);

CREATE INDEX idx_audit_logs_user_id ON public.audit_logs USING btree (user_id);

CREATE INDEX idx_audit_logs_workspace_id ON public.audit_logs USING btree (workspace_id);

CREATE INDEX idx_dedup_user_category_workspace ON public.notifications USING btree (user_id, category, workspace_id, created_at);

CREATE INDEX idx_license_activations_active ON public.license_activations USING btree (license_id, is_active);

CREATE INDEX idx_license_activations_license_instance ON public.license_activations USING btree (license_id, instance_id);

CREATE INDEX idx_notif_user_active_created ON public.notifications USING btree (user_id, created_at) WHERE (deleted_at IS NULL);

CREATE INDEX idx_notif_user_category_created ON public.notifications USING btree (user_id, category, created_at) WHERE (deleted_at IS NULL);

CREATE INDEX idx_notif_user_type_created ON public.notifications USING btree (user_id, type, created_at) WHERE (deleted_at IS NULL);

CREATE INDEX idx_notif_user_unread ON public.notifications USING btree (user_id) WHERE ((deleted_at IS NULL) AND (is_read = false));

CREATE INDEX idx_notif_user_workspace_created ON public.notifications USING btree (user_id, workspace_id, created_at) WHERE (deleted_at IS NULL);

CREATE INDEX idx_token_blacklist_expires_at ON public.token_blacklist USING btree (expires_at);

CREATE INDEX idx_token_blacklist_jti ON public.token_blacklist USING btree (jti);

CREATE INDEX idx_token_blacklist_user_id ON public.token_blacklist USING btree (user_id);

CREATE INDEX idx_user_read_deleted ON public.notifications USING btree (user_id, is_read, deleted_at);

CREATE INDEX idx_user_sessions_jti ON public.user_sessions USING btree (jti);

CREATE INDEX idx_user_sessions_last_activity ON public.user_sessions USING btree (last_activity_at);

CREATE INDEX idx_user_sessions_user_active ON public.user_sessions USING btree (user_id, is_active);

CREATE INDEX ix_account_creation_ip_allowlist_created_by ON public.account_creation_ip_allowlist USING btree (created_by);

CREATE INDEX ix_account_creation_ip_allowlist_is_active ON public.account_creation_ip_allowlist USING btree (is_active);

CREATE INDEX ix_account_recovery_requests_email ON public.account_recovery_requests USING btree (email);

CREATE INDEX ix_account_recovery_requests_reviewed_by_user_id ON public.account_recovery_requests USING btree (reviewed_by_user_id);

CREATE INDEX ix_account_recovery_requests_status ON public.account_recovery_requests USING btree (status);

CREATE INDEX ix_account_recovery_requests_user_id ON public.account_recovery_requests USING btree (user_id);

CREATE INDEX ix_api_usage_hourly_bucket ON public.api_usage_hourly USING btree (hour_bucket);

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);

CREATE INDEX ix_brand_voice_workspace_id ON public.brand_voice USING btree (workspace_id);

CREATE INDEX ix_content_created_by_user_id ON public.content USING btree (created_by_user_id);

CREATE INDEX ix_content_langgraph_thread_id ON public.content USING btree (langgraph_thread_id);

CREATE INDEX ix_content_persona_id ON public.content USING btree (persona_id);

CREATE INDEX ix_content_publishing_results_content_id ON public.content_publishing_results USING btree (content_id);

CREATE INDEX ix_content_publishing_results_scheduled_publish_at ON public.content_publishing_results USING btree (scheduled_publish_at);

CREATE INDEX ix_content_publishing_results_site_id ON public.content_publishing_results USING btree (site_id);

CREATE INDEX ix_content_slug ON public.content USING btree (slug);

CREATE INDEX ix_content_workspace_id ON public.content USING btree (workspace_id);

CREATE INDEX ix_customer_notes_admin_id ON public.customer_notes USING btree (admin_id);

CREATE INDEX ix_customer_notes_created_at ON public.customer_notes USING btree (created_at);

CREATE INDEX ix_customer_notes_user_id ON public.customer_notes USING btree (user_id);

CREATE INDEX ix_discount_usage_applied_at ON public.discount_usage USING btree (applied_at);

CREATE INDEX ix_discount_usage_discount_code ON public.discount_usage USING btree (discount_code);

CREATE INDEX ix_discount_usage_subscription_id ON public.discount_usage USING btree (subscription_id);

CREATE INDEX ix_discount_usage_user_id ON public.discount_usage USING btree (user_id);

CREATE INDEX ix_email_events_email_log_id ON public.email_events USING btree (email_log_id);

CREATE INDEX ix_email_events_event_type ON public.email_events USING btree (event_type);

CREATE INDEX ix_email_events_provider_message_id ON public.email_events USING btree (provider_message_id);

CREATE INDEX ix_email_events_received_at ON public.email_events USING btree (received_at);

CREATE INDEX ix_email_logs_created_at ON public.email_logs USING btree (created_at);

CREATE INDEX ix_email_logs_provider_message_id ON public.email_logs USING btree (provider_message_id);

CREATE INDEX ix_email_logs_status ON public.email_logs USING btree (status);

CREATE INDEX ix_email_logs_to_email ON public.email_logs USING btree (to_email);

CREATE INDEX ix_email_logs_user_id ON public.email_logs USING btree (user_id);

CREATE INDEX ix_email_logs_workspace_id ON public.email_logs USING btree (workspace_id);

CREATE INDEX ix_email_templates_created_by_user_id ON public.email_templates USING btree (created_by_user_id);

CREATE INDEX ix_email_templates_workspace_id ON public.email_templates USING btree (workspace_id);

CREATE INDEX ix_error_logs_resolved ON public.error_logs USING btree (resolved);

CREATE INDEX ix_error_logs_resolved_by ON public.error_logs USING btree (resolved_by);

CREATE INDEX ix_error_logs_severity ON public.error_logs USING btree (severity);

CREATE INDEX ix_error_logs_timestamp ON public.error_logs USING btree ("timestamp");

CREATE INDEX ix_error_logs_user_id ON public.error_logs USING btree (user_id);

CREATE UNIQUE INDEX ix_impersonation_sessions_session_id ON public.impersonation_sessions USING btree (session_id);

CREATE INDEX ix_integrations_integration_type ON public.integrations USING btree (integration_type);

CREATE INDEX ix_integrations_workspace_id ON public.integrations USING btree (workspace_id);

CREATE INDEX ix_knowledge_base_created_by_user_id ON public.knowledge_base USING btree (created_by_user_id);

CREATE INDEX ix_knowledge_base_workspace_id ON public.knowledge_base USING btree (workspace_id);

CREATE INDEX ix_knowledge_base_workspace_name ON public.knowledge_base USING btree (workspace_id, name);

CREATE INDEX ix_knowledge_base_workspace_type ON public.knowledge_base USING btree (workspace_id, type);

CREATE INDEX ix_knowledge_files_file_hash ON public.knowledge_files USING btree (file_hash);

CREATE INDEX ix_knowledge_files_knowledge_base_id ON public.knowledge_files USING btree (knowledge_base_id);

CREATE INDEX ix_knowledge_files_workspace_hash ON public.knowledge_files USING btree (workspace_id, file_hash);

CREATE INDEX ix_knowledge_files_workspace_id ON public.knowledge_files USING btree (workspace_id);

CREATE INDEX ix_knowledge_files_workspace_kb ON public.knowledge_files USING btree (workspace_id, knowledge_base_id);

CREATE INDEX ix_license_activations_instance_id ON public.license_activations USING btree (instance_id);

CREATE INDEX ix_license_activations_is_active ON public.license_activations USING btree (is_active);

CREATE INDEX ix_license_activations_license_id ON public.license_activations USING btree (license_id);

CREATE INDEX ix_licenses_activation_email ON public.licenses USING btree (activation_email);

CREATE UNIQUE INDEX ix_licenses_lemonsqueezy_license_id ON public.licenses USING btree (lemonsqueezy_license_id);

CREATE UNIQUE INDEX ix_licenses_license_key ON public.licenses USING btree (license_key);

CREATE INDEX ix_licenses_status ON public.licenses USING btree (status);

CREATE INDEX ix_licenses_user_id ON public.licenses USING btree (user_id);

CREATE INDEX ix_notifications_category ON public.notifications USING btree (category);

CREATE INDEX ix_notifications_is_read ON public.notifications USING btree (is_read);

CREATE INDEX ix_notifications_status ON public.notifications USING btree (status);

CREATE INDEX ix_notifications_type ON public.notifications USING btree (type);

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);

CREATE INDEX ix_notifications_workspace_id ON public.notifications USING btree (workspace_id);

CREATE INDEX ix_oauth_accounts_user_id ON public.oauth_accounts USING btree (user_id);

CREATE INDEX ix_orders_lemonsqueezy_customer_id ON public.orders USING btree (lemonsqueezy_customer_id);

CREATE UNIQUE INDEX ix_orders_lemonsqueezy_order_id ON public.orders USING btree (lemonsqueezy_order_id);

CREATE INDEX ix_orders_lemonsqueezy_subscription_id ON public.orders USING btree (lemonsqueezy_subscription_id);

CREATE INDEX ix_orders_lemonsqueezy_variant_id ON public.orders USING btree (lemonsqueezy_variant_id);

CREATE INDEX ix_orders_ordered_at ON public.orders USING btree (ordered_at);

CREATE INDEX ix_orders_status ON public.orders USING btree (status);

CREATE INDEX ix_orders_subscription_id ON public.orders USING btree (subscription_id);

CREATE INDEX ix_orders_user_id ON public.orders USING btree (user_id);

CREATE INDEX ix_payment_methods_user_id ON public.payment_methods USING btree (user_id);

CREATE INDEX ix_persona_workspace_id ON public.persona USING btree (workspace_id);

CREATE INDEX ix_platform_admin_invitations_accepted_by_user_id ON public.platform_admin_invitations USING btree (accepted_by_user_id);

CREATE INDEX ix_platform_admin_invitations_email ON public.platform_admin_invitations USING btree (email);

CREATE UNIQUE INDEX ix_platform_admin_invitations_invitation_token ON public.platform_admin_invitations USING btree (invitation_token);

CREATE INDEX ix_platform_admin_invitations_invited_by_admin_id ON public.platform_admin_invitations USING btree (invited_by_admin_id);

CREATE INDEX ix_platform_admin_invitations_revoked_by_admin_id ON public.platform_admin_invitations USING btree (revoked_by_admin_id);

CREATE INDEX ix_platform_admin_invitations_status ON public.platform_admin_invitations USING btree (status);

CREATE INDEX ix_refund_requests_created_at ON public.refund_requests USING btree (created_at);

CREATE INDEX ix_refund_requests_ls_order_id ON public.refund_requests USING btree (lemonsqueezy_order_id);

CREATE INDEX ix_refund_requests_order_id ON public.refund_requests USING btree (order_id);

CREATE INDEX ix_refund_requests_status ON public.refund_requests USING btree (status);

CREATE INDEX ix_refund_requests_user_id ON public.refund_requests USING btree (user_id);

CREATE INDEX ix_refunds_lemonsqueezy_order_id ON public.refunds USING btree (lemonsqueezy_order_id);

CREATE INDEX ix_refunds_lemonsqueezy_refund_id ON public.refunds USING btree (lemonsqueezy_refund_id);

CREATE INDEX ix_refunds_status ON public.refunds USING btree (status);

CREATE INDEX ix_refunds_subscription_id ON public.refunds USING btree (subscription_id);

CREATE INDEX ix_refunds_user_id ON public.refunds USING btree (user_id);

CREATE INDEX ix_role_permissions_permission_id ON public.role_permissions USING btree (permission_id);

CREATE INDEX ix_role_permissions_role_id ON public.role_permissions USING btree (role_id);

CREATE INDEX ix_shopify_app_installs_shop_url ON public.shopify_app_installs USING btree (shop_url);

CREATE INDEX ix_shopify_app_installs_workspace_id ON public.shopify_app_installs USING btree (workspace_id);

CREATE INDEX ix_subscription_plans_lemonsqueezy_product_id ON public.subscription_plans USING btree (lemonsqueezy_product_id);

CREATE INDEX ix_subscription_plans_lemonsqueezy_variant_id_monthly ON public.subscription_plans USING btree (lemonsqueezy_variant_id_monthly);

CREATE INDEX ix_subscription_plans_lemonsqueezy_variant_id_yearly ON public.subscription_plans USING btree (lemonsqueezy_variant_id_yearly);

CREATE INDEX ix_text_knowledge_knowledge_base_id ON public.text_knowledge USING btree (knowledge_base_id);

CREATE INDEX ix_text_knowledge_workspace_id ON public.text_knowledge USING btree (workspace_id);

CREATE INDEX ix_text_knowledge_workspace_kb ON public.text_knowledge USING btree (workspace_id, knowledge_base_id);

CREATE INDEX ix_trial_conversions_conversion_plan_id ON public.trial_conversions USING btree (conversion_plan_id);

CREATE INDEX ix_trial_conversions_converted_at ON public.trial_conversions USING btree (converted_at);

CREATE INDEX ix_trial_conversions_subscription_id ON public.trial_conversions USING btree (subscription_id);

CREATE INDEX ix_trial_conversions_user_id ON public.trial_conversions USING btree (user_id);

CREATE INDEX ix_user_invitations_email_status ON public.user_invitations USING btree (email, status);

CREATE INDEX ix_user_onboarding_completed ON public.user_onboarding USING btree (completed);

CREATE UNIQUE INDEX ix_user_onboarding_user_id ON public.user_onboarding USING btree (user_id);

CREATE INDEX ix_user_preferences_id ON public.user_preferences USING btree (id);

CREATE INDEX ix_user_sessions_is_active ON public.user_sessions USING btree (is_active);

CREATE INDEX ix_user_sessions_last_activity_at ON public.user_sessions USING btree (last_activity_at);

CREATE INDEX ix_user_sessions_user_id ON public.user_sessions USING btree (user_id);

CREATE INDEX ix_user_subscriptions_grace_period_end ON public.user_subscriptions USING btree (grace_period_end);

CREATE INDEX ix_user_subscriptions_lemonsqueezy_customer_id ON public.user_subscriptions USING btree (lemonsqueezy_customer_id);

CREATE UNIQUE INDEX ix_user_subscriptions_lemonsqueezy_subscription_id ON public.user_subscriptions USING btree (lemonsqueezy_subscription_id);

CREATE INDEX ix_user_subscriptions_plan_id ON public.user_subscriptions USING btree (plan_id);

CREATE INDEX ix_user_subscriptions_renews_at ON public.user_subscriptions USING btree (renews_at);

CREATE INDEX ix_user_subscriptions_user_id ON public.user_subscriptions USING btree (user_id);

CREATE UNIQUE INDEX ix_users_provider_customer_id ON public.users USING btree (provider_customer_id);

CREATE INDEX ix_users_registration_device_fingerprint ON public.users USING btree (registration_device_fingerprint);

CREATE INDEX ix_webhook_events_created_at ON public.webhook_events USING btree (created_at);

CREATE UNIQUE INDEX ix_webhook_events_event_id ON public.webhook_events USING btree (event_id);

CREATE INDEX ix_webhook_events_event_name ON public.webhook_events USING btree (event_name);

CREATE INDEX ix_webhook_events_processed ON public.webhook_events USING btree (processed);

CREATE INDEX ix_website_knowledge_base_id ON public.website USING btree (knowledge_base_id);

CREATE INDEX ix_website_workspace_id ON public.website USING btree (workspace_id);

CREATE INDEX ix_website_workspace_kb ON public.website USING btree (workspace_id, knowledge_base_id);

CREATE INDEX ix_website_workspace_url ON public.website USING btree (workspace_id, url);

CREATE INDEX ix_workspace_deleted_by ON public.workspace USING btree (deleted_by);

CREATE UNIQUE INDEX ix_workspace_slug ON public.workspace USING btree (slug);

CREATE INDEX ix_workspace_user_id ON public.workspace USING btree (user_id);

CREATE UNIQUE INDEX uq_account_recovery_email_pending ON public.account_recovery_requests USING btree (email) WHERE ((status)::text = 'pending'::text);

CREATE UNIQUE INDEX uq_admin_invitation_email_pending ON public.platform_admin_invitations USING btree (email) WHERE ((status)::text = 'pending'::text);

CREATE UNIQUE INDEX uq_refund_requests_one_open_per_order ON public.refund_requests USING btree (order_id) WHERE (status = 'pending'::public.refundrequeststatus);

CREATE TRIGGER trg_single_workspace_owner BEFORE INSERT OR UPDATE OF role_id, workspace_id ON public.user_roles FOR EACH ROW EXECUTE FUNCTION public.enforce_single_workspace_owner();

ALTER TABLE ONLY public.account_creation_ip_allowlist
    ADD CONSTRAINT account_creation_ip_allowlist_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.account_recovery_requests
    ADD CONSTRAINT account_recovery_requests_reviewed_by_user_id_fkey FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.account_recovery_requests
    ADD CONSTRAINT account_recovery_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.brand_voice
    ADD CONSTRAINT brand_voice_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.content
    ADD CONSTRAINT content_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.content_publishing_results
    ADD CONSTRAINT content_publishing_results_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.content_publishing_results
    ADD CONSTRAINT content_publishing_results_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.integrations(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.content_seo_data
    ADD CONSTRAINT content_seo_data_content_id_fkey FOREIGN KEY (content_id) REFERENCES public.content(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.content
    ADD CONSTRAINT content_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.customer_notes
    ADD CONSTRAINT customer_notes_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.customer_notes
    ADD CONSTRAINT customer_notes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.discount_usage
    ADD CONSTRAINT discount_usage_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.user_subscriptions(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.discount_usage
    ADD CONSTRAINT discount_usage_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.email_events
    ADD CONSTRAINT email_events_email_log_id_fkey FOREIGN KEY (email_log_id) REFERENCES public.email_logs(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.email_logs
    ADD CONSTRAINT email_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.email_logs
    ADD CONSTRAINT email_logs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.email_templates
    ADD CONSTRAINT email_templates_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.email_templates
    ADD CONSTRAINT email_templates_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.error_logs
    ADD CONSTRAINT error_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.content
    ADD CONSTRAINT fk_content_persona_id FOREIGN KEY (persona_id) REFERENCES public.persona(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.knowledge_files
    ADD CONSTRAINT fk_knowledge_files_knowledge_base FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_base(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.text_knowledge
    ADD CONSTRAINT fk_text_knowledge_knowledge_base FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_base(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.token_blacklist
    ADD CONSTRAINT fk_token_blacklist_user_id FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.website
    ADD CONSTRAINT fk_website_knowledge_base FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_base(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.knowledge_base
    ADD CONSTRAINT knowledge_base_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.knowledge_base
    ADD CONSTRAINT knowledge_base_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.knowledge_files
    ADD CONSTRAINT knowledge_files_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.license_activations
    ADD CONSTRAINT license_activations_license_id_fkey FOREIGN KEY (license_id) REFERENCES public.licenses(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.licenses
    ADD CONSTRAINT licenses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.oauth_accounts
    ADD CONSTRAINT oauth_accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.user_subscriptions(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT payment_methods_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.persona
    ADD CONSTRAINT persona_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.platform_admin_invitations
    ADD CONSTRAINT platform_admin_invitations_accepted_by_user_id_fkey FOREIGN KEY (accepted_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.platform_admin_invitations
    ADD CONSTRAINT platform_admin_invitations_invited_by_admin_id_fkey FOREIGN KEY (invited_by_admin_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.platform_admin_invitations
    ADD CONSTRAINT platform_admin_invitations_revoked_by_admin_id_fkey FOREIGN KEY (revoked_by_admin_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.refund_requests
    ADD CONSTRAINT refund_requests_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.refund_requests
    ADD CONSTRAINT refund_requests_refund_id_fkey FOREIGN KEY (refund_id) REFERENCES public.refunds(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.refund_requests
    ADD CONSTRAINT refund_requests_reviewed_by_user_id_fkey FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.refund_requests
    ADD CONSTRAINT refund_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.user_subscriptions(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.shopify_app_installs
    ADD CONSTRAINT shopify_app_installs_linked_by_fkey FOREIGN KEY (linked_by) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.shopify_app_installs
    ADD CONSTRAINT shopify_app_installs_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.text_knowledge
    ADD CONSTRAINT text_knowledge_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.trial_conversions
    ADD CONSTRAINT trial_conversions_conversion_plan_id_fkey FOREIGN KEY (conversion_plan_id) REFERENCES public.subscription_plans(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.trial_conversions
    ADD CONSTRAINT trial_conversions_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.user_subscriptions(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.trial_conversions
    ADD CONSTRAINT trial_conversions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_invited_by_user_id_fkey FOREIGN KEY (invited_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_onboarding
    ADD CONSTRAINT user_onboarding_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_assigned_by_user_id_fkey FOREIGN KEY (assigned_by_user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id);

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.subscription_plans(id) ON DELETE RESTRICT;

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.website
    ADD CONSTRAINT website_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.workspace
    ADD CONSTRAINT workspace_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_invitation_id_fkey FOREIGN KEY (invitation_id) REFERENCES public.user_invitations(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.workspace_members
    ADD CONSTRAINT workspace_members_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspace(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.workspace
    ADD CONSTRAINT workspace_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
