#!/usr/bin/env python3
"""Regenerate apps.json (AltStore format) from the GitHub releases of the
repos listed in sources.json. Stdlib only; run by GitHub Actions daily and
on demand. Each app entry tracks the newest matching .ipa asset of its repo.
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "ios-source-updater",
        "Accept": "application/vnd.github+json",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def build_app(cfg):
    repo = cfg["repo"]
    include = re.compile(cfg.get("assetPattern", r"\.ipa$"))
    exclude = cfg.get("assetExclude")
    exclude_re = re.compile(exclude) if exclude else None
    max_versions = int(cfg.get("maxVersions", 5))

    releases = fetch_json(f"{API}/repos/{repo}/releases?per_page=15")
    versions = []
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        asset = None
        for a in rel.get("assets", []):
            name = a["name"]
            if include.search(name) and not (exclude_re and exclude_re.search(name)):
                asset = a
                break
        if asset is None:
            continue
        version = rel["tag_name"].lstrip("v")
        versions.append({
            "version": version,
            "date": rel["published_at"],
            "downloadURL": asset["browser_download_url"],
            "size": asset["size"],
            "localizedDescription": f"{cfg['name']} {version} ({asset['name']})",
        })
        if len(versions) >= max_versions:
            break
    if not versions:
        raise RuntimeError(f"no matching IPA asset found in releases of {repo}")

    latest = versions[0]
    app = {
        "name": cfg["name"],
        "bundleIdentifier": cfg["bundleIdentifier"],
        "developerName": cfg.get("developerName", repo.split("/")[0]),
        "version": latest["version"],
        "versionDate": latest["date"],
        "downloadURL": latest["downloadURL"],
        "size": latest["size"],
        "versions": versions,
    }
    for key in ("subtitle", "localizedDescription", "iconURL", "tintColor"):
        if cfg.get(key):
            app[key] = cfg[key]
    return app


def main():
    with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
        config = json.load(f)
    source = dict(config["source"])
    source["apps"] = [build_app(cfg) for cfg in config["apps"]]
    source["news"] = []
    out = os.path.join(ROOT, "apps.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(source, f, ensure_ascii=False, indent=2)
        f.write("\n")
    for app in source["apps"]:
        print(f"{app['name']}: {app['version']} -> {app['downloadURL']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
