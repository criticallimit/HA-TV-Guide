const assert = require('node:assert/strict');
const prune = require('../.github/scripts/prune-releases.cjs');
(async () => {
  const stable = Array.from({length:8}, (_, index) => ({id:index+1, tag_name:`v1.0.${index}`, published_at:`2026-10-${String(index+1).padStart(2,'0')}T12:00:00Z`, draft:false, prerelease:false}));
  const releases = [stable[3], {id:100,draft:true}, ...stable.filter(release => release.id !== 4).reverse(), {id:101,prerelease:true}];
  let deleted = [];
  const github = {
    paginate:async (endpoint, args) => {assert.equal(args.per_page,100);assert.equal(args.repo,'example');return releases;},
    rest:{repos:{listReleases:()=>{},deleteRelease:async args => deleted.push(args.release_id)}}
  };
  const context = {repo:{owner:'owner',repo:'example'},payload:{release:stable[7]}};
  const core = {info:()=>{}};
  const preview = await prune({github,context,core});
  assert.deepEqual(preview.retained,['v1.0.7','v1.0.6','v1.0.5','v1.0.4','v1.0.3']);
  assert.deepEqual(preview.removed,['v1.0.2','v1.0.1','v1.0.0']);
  assert.deepEqual(deleted,[],'Dry runs must not delete anything');
  await prune({github,context,core,dryRun:false});
  assert.deepEqual(deleted,[3,2,1],'Only older stable release IDs may be deleted');
  deleted=[];
  await assert.rejects(prune({github,context:{...context,payload:{release:stable[0]}},core,dryRun:false}),/triggering release/);
  assert.deepEqual(deleted,[]);
  github.paginate=async()=>stable.slice(0,5);
  await prune({github,context:{...context,payload:{}},core,dryRun:false});
  assert.deepEqual(deleted,[],'Repositories with five releases need no cleanup');
  console.log('PASS stable release retention, dry run, pagination and publication guard');
})().catch(error=>{console.error(error);process.exitCode=1;});
