# Programme and logo preparation

TV Guide includes prepared main-channel SVG logos and a complete logo index. Large logo archives are downloaded separately into the entry-owned `.storage/tv_guide_store/<entry>/logos/<revision>` cache. Downloads use immutable commits of this repository, bounded transfers and SHA-256 verification. Individual broadcaster/logo URLs and installed add-ons are not queried.

On first opening, a translated preparation dialog shows programme activity and installed logo packages. It can be closed while work continues, and closes automatically after successful completion. Failed initial downloads remain retryable; completed packages survive interruptions, restarts and integration updates. Removing the integration removes its owned cache.

The five-minute maintenance cycle repairs missing or changed installed packages. Explicit retries also verify packages whose timestamps and sizes have not changed. Healthy programme data are retained. Initial download failures retry on maintenance; failed checks for a new version retry the next day.

A separate, persisted daily check fetches a small conditional version descriptor. New library versions reuse unchanged local archives, download changed packages and verify the complete staged library before atomic activation. Failed updates retain installed artwork. Revisioned image URLs update open cards without restarting Home Assistant or rebuilding programme rows. Routine checks do not reopen initial preparation. See [publishing logo updates](logo-updates.md) for descriptor generation and version ordering.

Offline tests cover downloads, integrity, interruption, retries, restart recovery, concurrent reads, update ordering and failure rollback. Browser tests verify preparation, completion and image replacement while retaining programme DOM. The real Home Assistant smoke test uses deterministic fixtures instead of live providers.
