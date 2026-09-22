# Supabase migration source

Phase B2 prepares source only. Do not run these files against any Supabase
project until the migration set and verification SQL receive owner approval.

Apply migrations in lexical order. Each migration is transactional and must
leave every new object private, revoked, and RLS-protected before commit.
`verification/phase_b2_verification.sql` is read-only/rollback verification,
not an installed migration.

Initial factors are seeded as `draft`; production activation is blocked until
the institution confirms the official source and jurisdiction.
