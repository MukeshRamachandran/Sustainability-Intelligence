begin;

create extension if not exists pgcrypto with schema extensions;

create schema if not exists app_private;
create schema if not exists api;
revoke all on schema app_private from public, anon, authenticated;
revoke all on schema api from public, anon, authenticated;

create type app_private.app_role as enum
  ('scope1_manager','scope2_manager','renewable_manager','administrator');
create type app_private.data_domain as enum ('scope1','scope2','renewable');
create type app_private.submission_status as enum
  ('draft','submitted','under_review','correction_requested','approved');
create type app_private.submission_granularity as enum ('monthly','period_total');
create type app_private.review_action as enum
  ('submitted','review_started','correction_requested','resubmitted','approved','superseded');
create type app_private.factor_set_status as enum ('draft','active','retired');
create type app_private.release_status as enum ('candidate','active','superseded','revoked');
create type app_private.evidence_status as enum
  ('pending','uploading','quarantined','clean','failed','infected','deleted');

revoke all on all types in schema app_private from public, anon, authenticated;
commit;
