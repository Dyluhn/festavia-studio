# Community releases

The first community release is a **preview**. The repository is currently private;
preparing a draft does not make it public. Native hardware coverage is LCX030 /
1.163.5 at 27 detected positions. Every count 1–48 is covered in production
software tests. A square BSB002 bridge and a fresh-board first installation still
need independent physical evidence. Preserve those distinctions in release notes.

## Prepare a candidate

1. Keep the manifest version, `const.py` version and card header aligned. Add
   release notes describing behavior and actual validation. Keep firmware versions
   separate; do not rebuild or reflash an unchanged image for a documentation update.
2. Run `bash tools/check.sh` in the documented developer environment. The packager
   verifies firmware/source hashes and rejects private runtime files and symlinks.
3. Extract the resulting full-source ZIP into a fresh directory. Install its pinned
   dependencies in a new environment and run its check script there. Its repackaged
   archives should match the originals byte for byte.
4. Run `python tools/compatibility.py --source <extracted-source> --output <evidence>`.
   This runs actual HA in isolated containers, with network peers and Zigbee
   simulated, on the minimum/current/regression versions and both bridge models.
   A zero exit status requires explicit success reports from every suite.
5. Require the three desktop USB-tool jobs, HA matrix, hassfest and HACS metadata
   validation to pass. The USB jobs never open hardware. Record new physical
   results separately; no physical capability is inferred from a simulator.

## Build and draft

`python tools/package.py --output <directory>/festavia-studio-<version>.zip`
produces:

- `festavia-studio-<version>.zip`: complete source, guide and first-install image.
- `festavia-studio-integration-<version>.zip`: manual HA installation.
- `festavia-studio-<version>-SHA256SUMS`: checksums of both download archives.

The integration ZIP includes its `custom_components/` path for manual copying.
Marketplace/HACS installs `custom_components/festavia_studio` directly from the
tagged repository; `zip_release` is intentionally not enabled for that ZIP layout.
User data stays in HA storage, not in the replaced component folder.

The **Prepare release draft** workflow is manual. Run it on the reviewed commit
with a tag matching the integration version. It refuses a commit whose Validate
package workflow has not passed, builds the artifacts, and creates a **draft
prerelease** with the commit pinned. It never changes repository visibility or
publishes the draft. Attach a concise human-reviewed note with the compatibility
scope, limitations and link to the install guide before publishing.

## Public beta and catalog

The repository needs to be public before other users can use Marketplace custom
repositories. Review the tracked source and intended history before changing
visibility. Do not publish household profiles, device connection files or private
test evidence. A source archive with valid checksums does not audit old Git history.

Once public, use a small volunteer beta with different detected lengths, square
and Pro bridges, desktop USB hosts and network layouts. Request the structured
hardware report in the issue templates. Keep native model/firmware qualification
strict until readback, direction/order and restoration are verified on each new
profile. A support statement for every physical Festavia variant would be premature.

Users can then add the repository themselves. Do not wait for catalog acceptance
to offer a public custom-repository install. After a stable release and user
feedback, submit to the shared Marketplace/HACS catalog with passing metadata
and hassfest checks. Catalog inclusion and HA Core inclusion are separate reviews;
this project claims neither a Core quality tier nor official Hue certification.

Publisher references: [integration structure and validation](https://contributors.home-assistant.io/marketplace/guides/integrations/),
[releases and prereleases](https://contributors.home-assistant.io/marketplace/guides/releases/),
[catalog submission](https://contributors.home-assistant.io/marketplace/guides/catalog/).
