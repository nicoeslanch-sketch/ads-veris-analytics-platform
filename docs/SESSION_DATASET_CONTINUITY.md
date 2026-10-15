# Dataset continuity during session renewal

## Reproduced failure

The authenticated browser showed an empty workspace after being left open;
reloading restored the saved workbook. Code inspection found that every changed
access token makes SecurityGate temporarily unmount its children to revalidate
the session. DatasetProvider was one of those children, so its in-memory file,
cleaning and period were lost. The restoration module's attempted-user cache
could then prevent another automatic restore until a reload.

An isolated browser fixture reproduced the loss both after a successful token
renewal and after a failed security check followed by a successful retry. Both
tests failed with the original provider order. This demonstrates a real failure
path; it does not claim all earlier empty-workspace reports had this cause.

## Fix and boundary

DatasetProvider now surrounds SecurityGate. It retains in-memory work for the
same user while the gate still unmounts the private interface and verifies the
new token with the server. No bypass, token reuse, MFA relaxation, extra storage
or new persistence is introduced. Identity changes and sign-out retain the
existing dataset and cache reset. The real composition lives in
WorkspaceProviders and is imported by both the application and regression fixture.

Browser regressions check successful renewal (including original unsaved File
bytes), delayed/failed verification, retry, account changes, sign-out and a new
MFA requirement. Real reloads still discard unsaved work: this change only
preserves state during in-page revalidation, not browser closure or crashes.

Supabase's authentication event reference:
https://supabase.com/docs/reference/javascript/auth-onauthstatechange
