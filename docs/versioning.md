# Versioning

Modbus Tap uses [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`. Every release is a GitHub release with notes from the [changelog](../CHANGELOG.md), so the Marketplace shows which version you have, what's new and whether an update breaks anything.

## What counts as breaking

An update is **breaking** when you have to do something after installing it, or something you rely on changes:

- Entities or devices are removed, renamed in their unique ID, or change what they measure.
- The register map format changes in a way that rejects maps that used to work.
- Community map entries change address, type or scale in a way that changes values you already record. Fixing a wrong guess counts too: it's a fix, but your history changes.
- Actions, events or the recording format change incompatibly.
- The minimum Home Assistant version goes up.

Breaking changes are listed under **⚠️ Breaking** in the release notes, with what to do.

## Before 1.0

While the version starts with `0.`, Modbus Tap is still settling:

- **0.MINOR** bumps may be breaking. Read the notes before updating.
- **0.x.PATCH** bumps are always safe: fixes only.

From 1.0 on, only MAJOR bumps break things. MINOR adds features, PATCH fixes bugs.

## Releasing (maintainers)

1. Move the `Unreleased` changelog entries under a new version heading, and mark breaking changes with **⚠️ Breaking**.
2. Set the same version in `custom_components/modbus_tap/manifest.json`.
3. Commit to `main`. The release workflow sees a version without a release, tags it `vX.Y.Z` and publishes the GitHub release with that changelog section as notes.
