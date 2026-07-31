CREATE TYPE "public"."actor_type" AS ENUM('agent', 'human', 'system');--> statement-breakpoint
CREATE TYPE "public"."contact_kind" AS ENUM('email', 'phone');--> statement-breakpoint
CREATE TYPE "public"."deployment_kind" AS ENUM('preview', 'final');--> statement-breakpoint
CREATE TYPE "public"."deployment_state" AS ENUM('pending', 'building', 'live', 'failed', 'retired');--> statement-breakpoint
CREATE TYPE "public"."discovery_source" AS ENUM('openstreetmap', 'google_places', 'manual', 'csv_import');--> statement-breakpoint
CREATE TYPE "public"."lead_group" AS ENUM('A', 'B');--> statement-breakpoint
CREATE TYPE "public"."lead_status" AS ENUM('new', 'qualified', 'contacted', 'following_up', 'replied', 'interested', 'negotiating', 'won', 'lost', 'disqualified', 'opted_out');--> statement-breakpoint
CREATE TYPE "public"."message_direction" AS ENUM('inbound', 'outbound');--> statement-breakpoint
CREATE TYPE "public"."message_intent" AS ENUM('interested', 'question', 'objection', 'not_interested', 'opt_out', 'deal', 'automated', 'suspicious', 'review', 'other');--> statement-breakpoint
CREATE TYPE "public"."message_status" AS ENUM('queued', 'sent', 'delivered', 'bounced', 'failed', 'received');--> statement-breakpoint
CREATE TYPE "public"."payment_kind" AS ENUM('build_deposit', 'build_balance', 'build_full', 'subscription', 'refund');--> statement-breakpoint
CREATE TYPE "public"."payment_status" AS ENUM('due', 'paid', 'failed', 'refunded', 'written_off');--> statement-breakpoint
CREATE TYPE "public"."project_status" AS ENUM('briefing', 'building', 'in_review', 'revising', 'approved', 'delivered', 'cancelled');--> statement-breakpoint
CREATE TYPE "public"."revision_status" AS ENUM('draft', 'generated', 'preview_published', 'changes_requested', 'approved');--> statement-breakpoint
CREATE TYPE "public"."run_status" AS ENUM('pending', 'running', 'succeeded', 'failed', 'cancelled', 'dead_lettered');--> statement-breakpoint
CREATE TYPE "public"."subscription_status" AS ENUM('active', 'past_due', 'cancelled');--> statement-breakpoint
CREATE TYPE "public"."suppression_reason" AS ENUM('opt_out_request', 'complaint', 'hard_bounce', 'manual', 'not_a_business');--> statement-breakpoint
CREATE TYPE "public"."task_kind" AS ENUM('escalation', 'approval', 'manual_outreach', 'follow_up', 'maintenance', 'investigation');--> statement-breakpoint
CREATE TYPE "public"."task_status" AS ENUM('open', 'in_progress', 'blocked', 'done', 'cancelled');--> statement-breakpoint
CREATE TABLE "businesses" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" text NOT NULL,
	"name_normalised" text NOT NULL,
	"trade" text,
	"area" text,
	"postcode" text,
	"address" text,
	"website_url" text,
	"website_host" text,
	"latitude" double precision,
	"longitude" double precision,
	"source" "discovery_source" NOT NULL,
	"source_ref" text,
	"is_chain" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "contacts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"business_id" uuid NOT NULL,
	"kind" "contact_kind" NOT NULL,
	"value" text NOT NULL,
	"value_normalised" text NOT NULL,
	"role" text,
	"is_plausible" boolean DEFAULT true NOT NULL,
	"source" "discovery_source" NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "site_audits" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"business_id" uuid NOT NULL,
	"audited_at" timestamp with time zone DEFAULT now() NOT NULL,
	"url" text,
	"score" integer,
	"biggest_flaw" text,
	"findings" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "suppressions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"kind" "contact_kind" NOT NULL,
	"value_normalised" text NOT NULL,
	"reason" "suppression_reason" NOT NULL,
	"note" text,
	"source" text,
	"suppressed_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "conversations" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"lead_id" uuid NOT NULL,
	"contact_id" uuid,
	"channel" text DEFAULT 'email' NOT NULL,
	"external_thread_id" text,
	"subject" text,
	"last_message_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "lead_scores" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"lead_id" uuid NOT NULL,
	"score" integer NOT NULL,
	"breakdown" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"scorer_version" text NOT NULL,
	"scored_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "leads" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"business_id" uuid NOT NULL,
	"status" "lead_status" DEFAULT 'new' NOT NULL,
	"group" "lead_group",
	"score" integer,
	"biggest_flaw" text,
	"outcome_reason" text,
	"first_contacted_at" timestamp with time zone,
	"last_contacted_at" timestamp with time zone,
	"last_replied_at" timestamp with time zone,
	"next_action_at" timestamp with time zone,
	"follow_ups_sent" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "messages" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"conversation_id" uuid NOT NULL,
	"direction" "message_direction" NOT NULL,
	"status" "message_status" NOT NULL,
	"external_id" text,
	"from_address" text NOT NULL,
	"to_address" text NOT NULL,
	"subject" text,
	"body" text NOT NULL,
	"touch" integer,
	"template" text,
	"is_automated" boolean DEFAULT true NOT NULL,
	"intent" "message_intent",
	"intent_confidence" integer,
	"sent_at" timestamp with time zone,
	"received_at" timestamp with time zone,
	"failed_at" timestamp with time zone,
	"failure_reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "customers" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"business_id" uuid NOT NULL,
	"lead_id" uuid,
	"contact_name" text,
	"billing_email" text,
	"won_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "deployments" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"website_id" uuid NOT NULL,
	"revision_id" uuid NOT NULL,
	"kind" "deployment_kind" NOT NULL,
	"state" "deployment_state" DEFAULT 'pending' NOT NULL,
	"provider" text DEFAULT 'netlify' NOT NULL,
	"provider_site_id" text,
	"provider_deploy_id" text,
	"url" text,
	"verified_at" timestamp with time zone,
	"deployed_at" timestamp with time zone,
	"retired_at" timestamp with time zone,
	"error" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "projects" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"customer_id" uuid NOT NULL,
	"name" text NOT NULL,
	"status" "project_status" DEFAULT 'briefing' NOT NULL,
	"brief" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"due_at" timestamp with time zone,
	"delivered_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "revisions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"website_id" uuid NOT NULL,
	"number" integer NOT NULL,
	"status" "revision_status" DEFAULT 'draft' NOT NULL,
	"content" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"requested_changes" text,
	"approved_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "websites" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"project_id" uuid NOT NULL,
	"slug" text NOT NULL,
	"template" text NOT NULL,
	"brand_tokens" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"repo_url" text,
	"custom_domain" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "payments" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"customer_id" uuid NOT NULL,
	"subscription_id" uuid,
	"kind" "payment_kind" NOT NULL,
	"status" "payment_status" DEFAULT 'due' NOT NULL,
	"amount_pence" integer NOT NULL,
	"currency" text DEFAULT 'GBP' NOT NULL,
	"method" text,
	"reference" text,
	"due_at" timestamp with time zone,
	"paid_at" timestamp with time zone,
	"note" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "subscriptions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"customer_id" uuid NOT NULL,
	"status" "subscription_status" DEFAULT 'active' NOT NULL,
	"amount_pence" integer DEFAULT 3900 NOT NULL,
	"currency" text DEFAULT 'GBP' NOT NULL,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"next_billing_at" timestamp with time zone,
	"cancelled_at" timestamp with time zone,
	"cancellation_reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "agent_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"agent" text NOT NULL,
	"run_id" uuid,
	"model" text,
	"status" "run_status" DEFAULT 'pending' NOT NULL,
	"prompt_tokens" integer,
	"completion_tokens" integer,
	"cost_tenth_pence" integer,
	"latency_ms" integer,
	"fallback_used" text,
	"error" jsonb,
	"started_at" timestamp with time zone,
	"finished_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "audit_log" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"actor_type" "actor_type" NOT NULL,
	"actor" text NOT NULL,
	"action" text NOT NULL,
	"entity_type" text NOT NULL,
	"entity_id" uuid,
	"before" jsonb,
	"after" jsonb,
	"reason" text,
	"occurred_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"type" text NOT NULL,
	"aggregate_type" text NOT NULL,
	"aggregate_id" uuid,
	"payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"dedupe_key" text,
	"occurred_at" timestamp with time zone DEFAULT now() NOT NULL,
	"published_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "tasks" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"kind" "task_kind" NOT NULL,
	"status" "task_status" DEFAULT 'open' NOT NULL,
	"priority" integer DEFAULT 3 NOT NULL,
	"subject" text NOT NULL,
	"detail" text,
	"entity_type" text,
	"entity_id" uuid,
	"payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"assigned_to" text,
	"due_at" timestamp with time zone,
	"resolved_at" timestamp with time zone,
	"resolution" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "workflow_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"workflow" text NOT NULL,
	"idempotency_key" text NOT NULL,
	"status" "run_status" DEFAULT 'pending' NOT NULL,
	"input" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"output" jsonb,
	"error" jsonb,
	"attempt" integer DEFAULT 1 NOT NULL,
	"started_at" timestamp with time zone,
	"finished_at" timestamp with time zone,
	"heartbeat_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "workflow_steps" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"name" text NOT NULL,
	"sequence" integer NOT NULL,
	"status" "run_status" DEFAULT 'pending' NOT NULL,
	"input" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"output" jsonb,
	"error" jsonb,
	"attempt" integer DEFAULT 1 NOT NULL,
	"started_at" timestamp with time zone,
	"finished_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "contacts" ADD CONSTRAINT "contacts_business_id_businesses_id_fk" FOREIGN KEY ("business_id") REFERENCES "public"."businesses"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "site_audits" ADD CONSTRAINT "site_audits_business_id_businesses_id_fk" FOREIGN KEY ("business_id") REFERENCES "public"."businesses"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_lead_id_leads_id_fk" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "conversations" ADD CONSTRAINT "conversations_contact_id_contacts_id_fk" FOREIGN KEY ("contact_id") REFERENCES "public"."contacts"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "lead_scores" ADD CONSTRAINT "lead_scores_lead_id_leads_id_fk" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "leads" ADD CONSTRAINT "leads_business_id_businesses_id_fk" FOREIGN KEY ("business_id") REFERENCES "public"."businesses"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "messages" ADD CONSTRAINT "messages_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "customers" ADD CONSTRAINT "customers_business_id_businesses_id_fk" FOREIGN KEY ("business_id") REFERENCES "public"."businesses"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "customers" ADD CONSTRAINT "customers_lead_id_leads_id_fk" FOREIGN KEY ("lead_id") REFERENCES "public"."leads"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "deployments" ADD CONSTRAINT "deployments_website_id_websites_id_fk" FOREIGN KEY ("website_id") REFERENCES "public"."websites"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "deployments" ADD CONSTRAINT "deployments_revision_id_revisions_id_fk" FOREIGN KEY ("revision_id") REFERENCES "public"."revisions"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "projects" ADD CONSTRAINT "projects_customer_id_customers_id_fk" FOREIGN KEY ("customer_id") REFERENCES "public"."customers"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "revisions" ADD CONSTRAINT "revisions_website_id_websites_id_fk" FOREIGN KEY ("website_id") REFERENCES "public"."websites"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "websites" ADD CONSTRAINT "websites_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "payments" ADD CONSTRAINT "payments_customer_id_customers_id_fk" FOREIGN KEY ("customer_id") REFERENCES "public"."customers"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "payments" ADD CONSTRAINT "payments_subscription_id_subscriptions_id_fk" FOREIGN KEY ("subscription_id") REFERENCES "public"."subscriptions"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_customer_id_customers_id_fk" FOREIGN KEY ("customer_id") REFERENCES "public"."customers"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "agent_runs" ADD CONSTRAINT "agent_runs_run_id_workflow_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."workflow_runs"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "workflow_steps" ADD CONSTRAINT "workflow_steps_run_id_workflow_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."workflow_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "businesses_source_ref_uq" ON "businesses" USING btree ("source","source_ref") WHERE source_ref is not null;--> statement-breakpoint
CREATE INDEX "businesses_name_normalised_idx" ON "businesses" USING btree ("name_normalised");--> statement-breakpoint
CREATE INDEX "businesses_website_host_idx" ON "businesses" USING btree ("website_host");--> statement-breakpoint
CREATE INDEX "businesses_area_idx" ON "businesses" USING btree ("area");--> statement-breakpoint
CREATE UNIQUE INDEX "contacts_business_value_uq" ON "contacts" USING btree ("business_id","kind","value_normalised");--> statement-breakpoint
CREATE INDEX "contacts_value_normalised_idx" ON "contacts" USING btree ("kind","value_normalised");--> statement-breakpoint
CREATE INDEX "site_audits_business_idx" ON "site_audits" USING btree ("business_id","audited_at");--> statement-breakpoint
CREATE UNIQUE INDEX "suppressions_kind_value_uq" ON "suppressions" USING btree ("kind","value_normalised");--> statement-breakpoint
CREATE INDEX "conversations_lead_idx" ON "conversations" USING btree ("lead_id");--> statement-breakpoint
CREATE UNIQUE INDEX "conversations_external_thread_uq" ON "conversations" USING btree ("channel","external_thread_id");--> statement-breakpoint
CREATE INDEX "lead_scores_lead_idx" ON "lead_scores" USING btree ("lead_id","scored_at");--> statement-breakpoint
CREATE UNIQUE INDEX "leads_business_uq" ON "leads" USING btree ("business_id");--> statement-breakpoint
CREATE INDEX "leads_status_idx" ON "leads" USING btree ("status");--> statement-breakpoint
CREATE INDEX "leads_next_action_idx" ON "leads" USING btree ("next_action_at");--> statement-breakpoint
CREATE UNIQUE INDEX "messages_external_id_uq" ON "messages" USING btree ("external_id");--> statement-breakpoint
CREATE INDEX "messages_conversation_idx" ON "messages" USING btree ("conversation_id","created_at");--> statement-breakpoint
CREATE INDEX "messages_direction_status_idx" ON "messages" USING btree ("direction","status");--> statement-breakpoint
CREATE UNIQUE INDEX "customers_business_uq" ON "customers" USING btree ("business_id");--> statement-breakpoint
CREATE INDEX "deployments_website_idx" ON "deployments" USING btree ("website_id","created_at");--> statement-breakpoint
CREATE INDEX "deployments_state_idx" ON "deployments" USING btree ("state");--> statement-breakpoint
CREATE UNIQUE INDEX "deployments_provider_deploy_uq" ON "deployments" USING btree ("provider","provider_deploy_id");--> statement-breakpoint
CREATE INDEX "projects_customer_idx" ON "projects" USING btree ("customer_id");--> statement-breakpoint
CREATE INDEX "projects_status_idx" ON "projects" USING btree ("status");--> statement-breakpoint
CREATE UNIQUE INDEX "revisions_website_number_uq" ON "revisions" USING btree ("website_id","number");--> statement-breakpoint
CREATE UNIQUE INDEX "websites_slug_uq" ON "websites" USING btree ("slug");--> statement-breakpoint
CREATE INDEX "websites_project_idx" ON "websites" USING btree ("project_id");--> statement-breakpoint
CREATE INDEX "payments_customer_idx" ON "payments" USING btree ("customer_id","created_at");--> statement-breakpoint
CREATE INDEX "payments_status_idx" ON "payments" USING btree ("status");--> statement-breakpoint
CREATE UNIQUE INDEX "payments_reference_uq" ON "payments" USING btree ("reference");--> statement-breakpoint
CREATE INDEX "subscriptions_customer_idx" ON "subscriptions" USING btree ("customer_id");--> statement-breakpoint
CREATE INDEX "subscriptions_next_billing_idx" ON "subscriptions" USING btree ("status","next_billing_at");--> statement-breakpoint
CREATE INDEX "agent_runs_agent_idx" ON "agent_runs" USING btree ("agent","created_at");--> statement-breakpoint
CREATE INDEX "agent_runs_run_idx" ON "agent_runs" USING btree ("run_id");--> statement-breakpoint
CREATE INDEX "audit_log_entity_idx" ON "audit_log" USING btree ("entity_type","entity_id","occurred_at");--> statement-breakpoint
CREATE INDEX "audit_log_actor_idx" ON "audit_log" USING btree ("actor","occurred_at");--> statement-breakpoint
CREATE UNIQUE INDEX "events_dedupe_key_uq" ON "events" USING btree ("dedupe_key");--> statement-breakpoint
CREATE INDEX "events_unpublished_idx" ON "events" USING btree ("occurred_at") WHERE published_at is null;--> statement-breakpoint
CREATE INDEX "events_aggregate_idx" ON "events" USING btree ("aggregate_type","aggregate_id");--> statement-breakpoint
CREATE INDEX "tasks_status_priority_idx" ON "tasks" USING btree ("status","priority","created_at");--> statement-breakpoint
CREATE INDEX "tasks_entity_idx" ON "tasks" USING btree ("entity_type","entity_id");--> statement-breakpoint
CREATE UNIQUE INDEX "workflow_runs_idempotency_uq" ON "workflow_runs" USING btree ("workflow","idempotency_key");--> statement-breakpoint
CREATE INDEX "workflow_runs_status_idx" ON "workflow_runs" USING btree ("status","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "workflow_steps_run_name_uq" ON "workflow_steps" USING btree ("run_id","name");--> statement-breakpoint
CREATE INDEX "workflow_steps_run_seq_idx" ON "workflow_steps" USING btree ("run_id","sequence");