# Publishing logo updates

Clients read `custom_components/tv_guide/logo_library/updates.json` from `main` at most once every 24 hours. The check time and successful ETag survive Home Assistant restarts. Older descriptor generations are ignored, including stale CDN responses; an intentional artwork rollback must be published as a newer generation. Explicit preparation retries can also check immediately. Failed checks retry the next day and retain the active library.

The descriptor contains a monotonically increasing generation, a unique hexadecimal revision, the size and SHA-256 of `index.json`, and the existing immutable package manifest. The large index is fetched only for a different revision. Unchanged archives are reused locally; changed archives are downloaded and verified in a separate revision directory. Index/member checks and complete package downloads must succeed before the active pointer changes. The bundled fallback and current version are retained; obsolete managed revisions are removed after successful activation.

To publish a new library:

1. Prepare the logo archives, updated `index.json` and a new, unique `revision`. Keep existing source names for replaced artwork. Publish the archives and index in an immutable commit of this repository.
2. Set `downloads.json` to that commit's `base_url`, package sizes and SHA-256 values. The committed index must match the one at that immutable URL.
3. Run `python tools/build_logo_updates.py` to regenerate `updates.json` (the generation increases automatically for a new revision). Commit the index, package manifest and generated descriptor together, pass CI, then merge to `main`.

CI checks the descriptor against the repository's index and package manifest. Clients accept package/index URLs only from immutable commits of this repository and reject unsupported schema versions, unexpected sizes, checksums and paths. Publishing these metadata changes makes the library available to integrations supporting background logo updates without a new integration release.

Activation changes the logo URL revision, clears rendered-image caches and invalidates only the guide presentation cache. Open cards pick up the new URLs on their regular guide refresh (within five minutes); programme DOM and the shared EPG snapshot are retained. Initial preparation is not reopened by routine background update checks.
