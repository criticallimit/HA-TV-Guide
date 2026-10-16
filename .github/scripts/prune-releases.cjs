/* Retain five published stable releases; never delete tags or prereleases. */
module.exports = async function pruneReleases({github, context, core, dryRun = true}) {
  const repository = {owner:context.repo.owner, repo:context.repo.repo};
  const releases = await github.paginate(github.rest.repos.listReleases, {...repository, per_page:100});
  const stable = releases.filter(release => !release.draft && !release.prerelease)
    .sort((left, right) => Date.parse(right.published_at) - Date.parse(left.published_at) || right.id - left.id);
  const retained = stable.slice(0, 5);
  const removed = stable.slice(5);
  // Refuse a surprising publication event rather than delete the triggering release.
  const published = context.payload?.release;
  if (published && !published.draft && !published.prerelease && !retained.some(release => release.id === published.id)) {
    throw new Error('The triggering release is not among the five newest stable releases');
  }
  core.info(`Retain: ${retained.map(release => release.tag_name).join(', ')}`);
  for (const release of removed) {
    core.info(`${dryRun ? 'Would remove' : 'Remove'} release ${release.tag_name}; keep its tag`);
    if (!dryRun) await github.rest.repos.deleteRelease({...repository, release_id:release.id});
  }
  return {retained:retained.map(release => release.tag_name), removed:removed.map(release => release.tag_name)};
};
