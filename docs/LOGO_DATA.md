# Logo database maintenance

All main-channel and additional-channel images are delivered through the independent logo database. The integration contains the index and download/update descriptors, not channel SVGs, PNGs or image archives. Downloaded images are served through `/tv_guide/logo/…?v=<database revision>`.

The permanent `logo-data` branch holds immutable data snapshots under `custom_components/tv_guide/logo_library/`. The main branch's `downloads.json` pins a full commit SHA of that branch. `updates.json` on main is the small public update pointer; clients check it conditionally every 24 hours. Retain the data branch and published commits when cleaning up development branches.

The index's `channels` map identifies light/dark artwork by `<country>:<stable station ID>`. Its entries share content-addressed SVG objects with compatibility aliases at the existing library paths. These aliases are essential: release 1.1.3 and earlier update-capable clients do not read `channels`, but already resolve those paths through the same downloaded database after a revision change.

To publish new artwork:

1. Start from the current index. Add or replace verified SVG objects in new `logos-NNN.zip` packages; retain unchanged packages to allow local reuse without downloads. Each archive must remain below 8 MiB and each member is named by the SHA-256 of its content.
2. Update both the canonical channel entries and all compatibility aliases for the affected station. Keep source provenance and original-artwork hashes. Italian dark variants can be reproduced from the central database with `python tools/build_channel_logo_variants.py custom_components/tv_guide/catalogs/italy_logo_sources.json --check`; `--archives` selects a downloaded package directory and `--output` writes proposed variants for the next snapshot.
3. Give the changed index a new revision. Commit the index and complete archive set to the data branch, then pin that immutable commit in `downloads.json`. Do not alter published snapshots.
4. Run `python tools/build_logo_updates.py` to advance the update generation. Run all validation, logo/browser checks and Home Assistant acceptance before merging the new descriptors to main. The public pointer is activated by that merge, independently of integration releases.
5. Verify public index/package checksums and an update using the unmodified oldest supported updater. Check that unchanged packages are reused, image URLs receive the new revision, programme state is retained, failed updates preserve the previous database and restart restores the active revision.

Run `python tests/prepare_logo_fixtures.py` once before offline unit/browser tests. It fetches verified sample packages from the same immutable data snapshot into the ignored `tests/fixtures/logo-samples` directory; no broadcaster images or archive copies are committed on the code branch. CI prepares these samples explicitly before running tests. Browser fixtures expose the same public database route. They never require installed image copies. The first central main-channel update was also tested with the unchanged code from release 1.1.3: all 582 variants across eleven countries switched, only two new packages were downloaded, and the active update survived restart.
