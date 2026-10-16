# Third-party notices and rights

TV Guide is an independent open-source project and is not affiliated with,
endorsed by, or sponsored by any television broadcaster, network, programme
provider, EPG provider, or Home Assistant.

## Licence scope

The MIT License in this repository applies to project-authored source code and
project-authored documentation unless a file states otherwise.

It does **not** grant any rights in third-party material, including:

- television channel names, trademarks and logos;
- programme titles, descriptions, images or other editorial content;
- EPG/XMLTV databases or data obtained from external providers;
- material fetched from broadcaster websites, APIs or teletext services.

Rights in such material remain with their respective owners and may be subject
to separate licences, terms of use, database rights, copyright, trademark law,
or other restrictions.

## Programme data

TV Guide retrieves programme information from external public sources at
runtime. Source availability does not by itself mean that the source or its
content is licensed for unrestricted reuse or redistribution.

Configured source families currently include, depending on country and
availability:

- Open-EPG XMLTV feeds;
- EPGshare XMLTV feeds;
- iptv-epg.org country feeds;
- the public TDTChannels XMLTV guide;
- public programme pages, APIs and teletext services operated by broadcasters;
- secondary public programme pages used to fill gaps.

Source URLs and country mappings are documented in
`custom_components/tv_guide/countries.json` and its registered channel catalogues.

No external programme data is relicensed under the MIT License by this project.
Users and distributors remain responsible for complying with the applicable
terms of the external source and the rights in the underlying programme
content.

## Channel logos and trademarks

Channel logos and wordmarks are third-party trademarks and/or
copyrighted brand assets. They are not covered by the MIT License.

Some assets were derived from or based on material obtained from broadcaster
websites, programme feeds, or the public `tv-logo/tv-logos` collection.
Current artwork provenance is recorded in `custom_components/tv_guide/catalogs/*_logo_sources.json`; inherited artwork retains its pinned upstream provenance in the logo database.

The upstream `tv-logo/tv-logos` project describes its collection as free for
personal use, asks for attribution when redistributing, and refers to a mixture
of Creative Commons ShareAlike licences. It does not provide one repository-wide
LICENSE file or a per-logo licence map. Accordingly, this project does not claim
that every third-party logo has a uniform open-source licence.

The repository also contains a generated Europe-wide offline logo pack built
from a pinned snapshot of `tv-logo/tv-logos`. That pack is distributed only as
third-party branding material and is not covered by this project's MIT licence.
The upstream project's attribution and redistribution statements therefore
continue to apply in addition to the rights of each broadcaster or trademark
holder.

If you are a rights holder and believe that a logo or other third-party asset
should be removed, corrected or attributed differently, please open an issue in
this repository.

## Project branding

The TV Guide project name, project-specific icon, project-specific logo and
other original project branding are not intended to grant trademark rights
under the MIT License. The MIT licence covers the copyright in project-authored
software; it does not grant rights to impersonate the project or suggest
endorsement.

## No warranty for external data

Programme information may be incomplete, delayed, changed or unavailable.
TV Guide does not guarantee the accuracy, completeness or continued
availability of third-party programme data.


## Additional reviewed sender artwork

The channel-specific additions recorded in `tv-guide/data/logo_updates.json`
include images supplied by the XMLTV feeds and public broadcaster/distributor
image servers. Some missing sources were discovered through the public
[iptv-org/api catalogue](https://github.com/iptv-org/api). Source URLs and hashes
are recorded per channel; embedded image hashes and preparation details are in
`tv-guide/data/logo_library.json` and the prepared-library parts indexed by
`tv-guide/data/logo_updates.json`. The catalogue's software/data licence does not
grant trademark or copyright rights to broadcaster artwork. These additional
third-party marks are not covered by this project's MIT licence.

E4, Film4, More4 and 5USA now use broadcaster artwork from the downloaded database. The main channel catalogue resolves its artwork through the current logo database. Channel names and marks belong to their respective owners.

## Native integration import scope

This native integration imports the original presentation code, Source Sans Pro fonts (licence in `custom_components/tv_guide/frontend/app/fonts/LICENSE.md`) and metadata referencing the separately downloaded logo database for its registered main-channel catalogues. Broadcaster image files are distributed in the independent logo database, outside the integration installation directory. It does not import the whole add-on server or whole Europe logo pack. The original rights and attribution statements above apply to these reused third-party assets. Provenance for the reference code is recorded in `custom_components/tv_guide/frontend/app/REFERENCE.json`.

Italian main-channel artwork reuses the verified broadcaster images already indexed by the logo library. Source URLs and SHA-256 hashes are recorded in `custom_components/tv_guide/catalogs/italy_logo_sources.json`. Dark variants use transparency, preserve coloured brand panels and render designated wordmarks in white. These marks remain the property of their respective owners.

## Spanish channel artwork

Spanish theme variants use verified original files from the pinned `tv-logo/tv-logos` collection and the official 3Cat and Squirrel broadcaster websites. URLs, original SHA-256 checksums and theme treatments are recorded in `custom_components/tv_guide/catalogs/spain_logo_sources.json`. Artwork is delivered through the separate logo database, not bundled in the integration. No rights in the broadcasters’ names or artwork are granted by this project.

## Polish channel artwork

Polish theme variants use original artwork from the pinned `tv-logo/tv-logos` collection and images supplied by the public XMLTV image service. Source URLs, original SHA-256 checksums and theme treatments are recorded in `custom_components/tv_guide/catalogs/poland_logo_sources.json`. Images are delivered through the independent logo database, outside the integration package. Broadcaster names and artwork remain the property of their respective owners.
