# Cloud9-OmniRoute — private upstream maintenance

**Private control repository** for the Cloud9 production distribution of [OmniRoute](https://github.com/cheaper-inference/OmniRoute). This is **not** a second 2.4 GB source mirror or an application source fork; the production build starts from each official stable upstream tag.

- Last certified upstream baseline: `v3.8.53`.
- **Canonical code patch files (4)** live only in [Cloud9-local-Patches](https://github.com/GodsQuantum/Cloud9-local-Patches), under `OmniRoute/production/`. This repository records their SHA256 in `upstream-lock.json` but does not duplicate their bytes.
- CT700 applies those patches via the existing canonical builder and runs compatibility tests before production deployment. The current runtime must never be replaced by a raw upstream image if Gemini multi-image, strict 1min.AI tools, Codex imagery or Cleanroom/CSP behavior would regress.
- A weekly GitHub Actions check reports new upstream releases as an issue. Upstream updates are **not** blindly merged and no private Cloud9 secrets are needed.
- A future CI→GHCR publishing pipeline must prove the same feature parity and OCI provenance before replacing the existing CT700 path. **Not certified yet.**

The separate public native fork `GodsQuantum/OmniRoute` cannot change to private directly while it belongs to GitHub's public fork network. It is not the current Cloud9 production source of truth.

No application binaries, credentials, custom domains or local deployment files are published here.
