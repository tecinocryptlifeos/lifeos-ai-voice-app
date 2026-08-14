# LOSAI Android Trusted Web Activity

This directory contains the Android wrapper configuration for the existing
LOSAI web application.

## Permanent identity

- Android package ID: `losia.htc.com`
- Trusted host: `losai.ng.eu.org`
- Initial route: `/chat?source=android-twa`

## Interface boundary

The wrapper does not copy, replace or redesign the existing Chat or Voice
interface. It opens the existing HTTPS application as a Trusted Web Activity.

## Step boundary

Step 5 creates and validates the wrapper configuration.

Step 6 will:

- create or load the protected signing key;
- generate the certificate fingerprint;
- generate the final Digital Asset Links file;
- build the signed APK and Android App Bundle.

No signing key or generated application package may be committed to Git.
