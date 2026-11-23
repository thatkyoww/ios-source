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
        # Browser-like UA: some sources (fastsign.dev) reject bot agents.
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                      "Version/18.0 Mobile/15E148 Safari/604.1",
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


def _norm_date(value):
    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value + "T00:00:00+00:00"
    return value


def build_app_from_source(cfg):
    """Track an app mirrored from another AltStore-format source: copy the
    newest entries for the bundle ID, keeping the original downloadURLs."""
    bundle = cfg["bundleIdentifier"]
    max_versions = int(cfg.get("maxVersions", 1))
    remote = fetch_json(cfg["sourceURL"])
    entries = [a for a in remote.get("apps", [])
               if a.get("bundleIdentifier") == bundle and a.get("downloadURL")]
    if cfg.get("namePattern"):
        name_re = re.compile(cfg["namePattern"])
        entries = [a for a in entries if name_re.search(a.get("name", ""))]
    if cfg.get("urlPattern"):
        url_re = re.compile(cfg["urlPattern"])
        entries = [a for a in entries if url_re.search(a.get("downloadURL", ""))]
    if not entries:
        raise RuntimeError(f"no entry for {bundle} in source {cfg['sourceURL']}")

    def entry_date(a):
        return a.get("versionDate") or a.get("date") or ""

    def version_key(a):
        parts = []
        for p in str(a.get("version", "")).split("."):
            parts.append((0, int(p), "") if p.isdigit() else (1, 0, p))
        return parts

    entries.sort(key=lambda a: (entry_date(a), version_key(a)), reverse=True)
    versions = []
    seen = set()
    for a in entries:
        ver = str(a.get("version", ""))
        if not ver or ver in seen:
            continue
        seen.add(ver)
        versions.append({
            "version": ver,
            "date": _norm_date(entry_date(a)),
            "downloadURL": a["downloadURL"],
            "size": a.get("size", 0),
            "localizedDescription": a.get("localizedDescription")
                or f"{cfg['name']} {ver}",
        })
        if len(versions) >= max_versions:
            break
    if not versions:
        raise RuntimeError(f"no usable version for {bundle} in source")
    latest = versions[0]
    first = entries[0]
    app = {
        "name": cfg["name"],
        "bundleIdentifier": bundle,
        "developerName": cfg.get("developerName") or first.get("developerName", ""),
        "version": latest["version"],
        "versionDate": latest["date"],
        "downloadURL": latest["downloadURL"],
        "size": latest["size"],
        "versions": versions,
    }
    for key in ("subtitle", "localizedDescription", "iconURL", "tintColor"):
        if cfg.get(key):
            app[key] = cfg[key]
    if "iconURL" not in app and first.get("iconURL"):
        app["iconURL"] = first["iconURL"]
    return app


def build(cfg):
    if cfg.get("type") == "source":
        return build_app_from_source(cfg)
    return build_app(cfg)


def main():
    with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
        config = json.load(f)
    out = os.path.join(ROOT, "apps.json")
    previous = {}
    if os.path.exists(out):
        try:
            with open(out, encoding="utf-8") as f:
                for a in json.load(f).get("apps", []):
                    previous[a.get("bundleIdentifier")] = a
        except Exception:
            previous = {}
    source = dict(config["source"])
    apps = []
    failures = []
    for cfg in config["apps"]:
        try:
            apps.append(build(cfg))
        except Exception as e:
            old = previous.get(cfg["bundleIdentifier"])
            if old is not None:
                print(f"WARN: {cfg['name']}: {e} -- keeping previous entry")
                apps.append(old)
            else:
                print(f"ERROR: {cfg['name']}: {e}")
                failures.append(cfg["name"])
    source["apps"] = apps
    source["news"] = []
    with open(out, "w", encoding="utf-8") as f:
        json.dump(source, f, ensure_ascii=False, indent=2)
        f.write("\n")
    for app in source["apps"]:
        print(f"{app['name']}: {app['version']} -> {app['downloadURL']}")
    if failures:
        print("FAILED apps:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
