# Downloaded test data

Run `python tests/prepare_logo_fixtures.py` before offline unit and browser tests. The script downloads and verifies selected immutable packages from the central logo database. Package files are ignored by Git and are not shipped in the integration or copied into the code branch. The authoritative index and checksums are in `custom_components/tv_guide/logo_library/`.
