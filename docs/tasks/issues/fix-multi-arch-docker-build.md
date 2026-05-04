---
title: Add linux/arm64 to release workflow Docker build platforms for Raspberry Pi support
status: backlog
area: ops
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add linux/arm64 to release workflow Docker build platforms for Raspberry Pi support #repo/ratatoskr #area/ops #status/backlog 🔽

## Objective

The monitoring stack in `ops/docker/docker-compose.monitoring.yml` targets Raspberry Pi 5 (`linux/arm64`). QEMU is already set up in the release workflow but no `platforms:` argument is passed to `docker/build-push-action`, so only `linux/amd64` is built. The published image cannot run on the Raspberry Pi target.

## Context

- `.github/workflows/release.yml` — `docker/setup-qemu-action` present, but `docker/build-push-action` has no `platforms:` key
- `ops/docker/docker-compose.monitoring.yml` — comment references Raspberry Pi 5 deployment

## Acceptance criteria

- [ ] `platforms: linux/amd64,linux/arm64` added to the `docker/build-push-action` step in `release.yml`
- [ ] Build succeeds for both platforms (QEMU emulation for arm64)
- [ ] Published GHCR image manifests show both architectures via `docker manifest inspect`

## Definition of done

`docker pull ghcr.io/<owner>/ratatoskr:<tag>` on a Raspberry Pi 5 pulls the `linux/arm64` image successfully.
