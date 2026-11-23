# ios-source

Personal AltStore-format source that tracks IPA releases published on GitHub.
A GitHub Action regenerates `apps.json` daily (and on demand) from the repos
listed in `sources.json`.

## Register this source

Add this URL in your signing app (AllSign / ESign / Feather / SideStore):

```
https://raw.githubusercontent.com/thatkyoww/ios-source/main/apps.json
```

## Included apps

- **YTKACE** — tracks [itzzace/ytkace](https://github.com/itzzace/ytkace)
  releases (standard IPA only; the iOS16 variant is excluded)

## Add another app

Add an entry to `sources.json` with the GitHub repo, the app's bundle ID and
an asset pattern, then push. The next workflow run (or a manual run from the
Actions tab) picks it up.
