# Community releases

Festavia Studio uses one project release stream, tagged `v<integration-version>`.
Each release contains the Home Assistant edition and the standalone Hue-only
edition. Direct firmware keeps its independent image version. Never publish a
separate `hue-direct-v...` release in this repository: HACS reads the shared feed
and would offer the wrong product tag as an integration version.

## Prepare and validate

1. Align the integration manifest, const.py and card header. Keep the image version
   unchanged when firmware source is unchanged. Update release notes and guides.
2. Run `bash tools/check.sh` with the developer requirements, Chromium and cJSON.
   Both editions must pass in the same checkout. The full Studio source archive
   contains the Hue-only source/tests too; the small integration ZIP contains only
   HA runtime files and installation documentation.
3. Extract the full source archive into a fresh folder and run its checks using a
   clean environment. Repackaged archives must match byte for byte. Run the
   standalone ZIP's launchers and CLI dry runs from an extracted folder too.
4. Run `python tools/compatibility.py --source <extracted-source> --output <evidence>`.
   These real-HA containers simulate the network and Zigbee peers; they do not
   establish physical hardware compatibility. Keep physical test records separate.
5. Require desktop USB-tool jobs, both editions' tests, the HA matrix and hassfest
   on the final commit. HACS validation must pass when public. Never suppress a
   validator failure to qualify a release.
6. Review intended Git history and all download assets for private information.
   Keep setup folders, device files and household evidence outside the repository.
7. Record fresh-install and hardware coverage honestly. Native qualification is
   LCX030 / 1.163.5 at 27 detected positions on BSB003; counts 1–48 and BSB002
   responses have software coverage. Additional physical combinations remain beta
   testing, not blanket certification. Keep controlled physical tests below 20%.

## Build a combined release

The manual **Prepare combined release draft** workflow requires a successful
Validate package run on its exact commit. It builds Direct with ESP-IDF 5.3.2,
verifies source/image identities, then packages both editions. Rerunning updates
an existing draft and refuses to replace a published release. It never changes
repository visibility or publishes by itself.

To package locally with a completed Direct build:

```sh
python tools/release.py --tag v0.13.0 --direct-build /path/to/build-direct --output /path/to/release
```

For unchanged qualified firmware, `--direct-archive /path/to/verified-direct.zip`
can replace `--direct-build`. Every source hash, image hash, archive checksum and
image identity is verified before reuse. SDK/library license notices travel with
those images. It never substitutes a different image for changed firmware source.

The output contains the full Studio source ZIP, smaller HA integration ZIP,
standalone Direct ZIP, Direct app/factory images and image manifest, plus a
combined `SHA256SUMS` and `release-manifest.json`. All artifact names distinguish
editions. The integration ZIP includes its `custom_components/` path for manual
copying. HACS installs the component from the project tag; `zip_release` remains
false because that manual ZIP is not laid out as a HACS runtime-only ZIP.

## Publish a beta

After reviewing the source, make the repository public and rerun validation so
the HACS job actually executes. Publish the matching draft as a prerelease only
after that passes. Verify signed-out documentation and downloads, every asset's
checksum, clean HACS/Marketplace/manual installation, and version selection with
prereleases enabled. Check an update from actual public assets preserves settings.
Do not call a draft or tag alone an installable GitHub release.

Use a small volunteer beta across actual quantities 1–48, shortened strings,
square/Pro bridges and different computer/network combinations. Use the hardware
issue form; mark untested items. Stable release needs independent installations,
longer hardware reliability evidence and resolution of significant pairing,
restoration, ownership, configuration-loss and update/recovery failures.

Default catalog submission can follow successful beta feedback. Core inclusion
is a separate review and is not required for custom-repository installation.
Neither official Hue certification nor an HA quality tier is claimed.

Publisher references: [integration validation](https://contributors.home-assistant.io/marketplace/guides/integrations/),
[releases and prereleases](https://contributors.home-assistant.io/marketplace/guides/releases/),
[HACS release selection](https://www.hacs.xyz/docs/publish/integration/).
