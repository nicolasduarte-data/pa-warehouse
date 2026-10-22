# Snowflake Key-Pair Authentication — Setup

dbt-snowflake uses RSA key-pair auth by convention for service accounts. The
private key lives locally (`~/.ssh/`), the public key gets registered on the
Snowflake user via `ALTER USER ... SET RSA_PUBLIC_KEY`. The private key never
leaves your machine; the repo only knows the path.

## Why key-pair (not password)?

| Concern | Password | Key-pair |
|---|---|---|
| Credential leak via committed `profiles.yml` | High (string-in-yaml) | None (only the file path is in yaml) |
| Rotation | Must coordinate with every consumer | Re-register new public key, done |
| MFA compatibility | Manual workaround | Native |
| Industry convention for dbt-snowflake | Discouraged | Standard |

## Generate the key-pair (one-time)

Run these commands in **Git Bash** (or any Unix-like shell) on Windows:

```bash
# Create the keys in ~/.ssh — on Windows that is %USERPROFILE%\.ssh\
mkdir -p ~/.ssh

# 1. Generate a 2048-bit RSA private key, encrypted with a passphrase.
#    -aes256: encrypts the private key file at rest (so a stolen laptop
#    doesn't immediately leak Snowflake access).
openssl genrsa -aes256 -out ~/.ssh/snowflake_rsa_key.p8 2048
# When prompted: choose a passphrase. You'll need it in profiles.yml.

# 2. Extract the public key in the format Snowflake's ALTER USER expects.
#    -pubout writes the public key only (no private bits).
openssl rsa -in ~/.ssh/snowflake_rsa_key.p8 -pubout -out ~/.ssh/snowflake_rsa_key.pub
# This will prompt for the passphrase you chose in step 1.

# 3. Print the public key body (without the BEGIN/END headers) — this is
#    what you paste into the snowflake_bootstrap.sql ALTER USER statement.
cat ~/.ssh/snowflake_rsa_key.pub \
  | grep -v 'PUBLIC KEY' \
  | tr -d '\n'
# Copy that single-line output. Paste it into snowflake_bootstrap.sql Step 6,
# replacing <<PASTE_PUBLIC_KEY_BODY_HERE>>. Then run that one ALTER USER
# statement in Snowsight.

# 4. Lock down the permissions so only you can read the private key.
chmod 600 ~/.ssh/snowflake_rsa_key.p8
```

## What you end up with

- `~/.ssh/snowflake_rsa_key.p8` — your encrypted private key (referenced in `profiles.yml`)
- `~/.ssh/snowflake_rsa_key.pub` — the public key (one-time paste into Snowflake)
- A passphrase you remember — required to decrypt the private key on each dbt run

## Trial expiry note

These keys outlive the 30-day Snowflake trial — you can reuse the SAME key-pair
if you sign up for a new trial later. Just paste the same public key into the
new account's ALTER USER statement.
