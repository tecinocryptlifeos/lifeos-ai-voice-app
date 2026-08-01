# Backup checkpoint

Before provider changes, record the reviewed Git commit SHA, current Pages and Worker deployment IDs, Render deploy ID and environment-variable names, Northflank deployment revision and variable names, Supabase migration list, DNS records, KV namespace ID, and rate-limit namespace ID. Store values in the owner's encrypted provider/password vault; store no secret values in Git or command output.

Provider rollback versions and Git commits are the recoverable backup. Large media is not copied into Supabase as part of this architecture change.
