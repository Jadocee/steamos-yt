#!/usr/bin/env python3
"""Assertions for one smoke-test launch; exits non-zero with a list of failures."""

import json
import re
import sys
from pathlib import Path

from server import BLOCKED_HOST, BROKEN, DOWNVOTED, ORIGINAL, PLAYER_ADS, RUNS, SKIPPED

STARBOARD = 0x8000
DOWN, UP = STARBOARD + 13, STARBOARD + 12
STICK_UP = STARBOARD + 17
DEARROW_THUMBNAIL = f"https://dearrow-thumb.ajay.app/api/v1/getThumbnail?videoID={SKIPPED}&time=42.5"


def main() -> int:
    output, scenario, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    expected_cookie = sys.argv[4] if len(sys.argv) > 4 else "*"
    failures = []

    def expect(condition, message):
        if not condition:
            failures.append(message)

    if (output / "error.txt").exists():
        failures.append("page error: " + (output / "error.txt").read_text())
    expect(not (output / "leaks.log").exists(), f"{BLOCKED_HOST} was loaded despite the site lock")
    if scenario == "site-lock":
        lock = json.loads((output / "lock.json").read_text())
        expect(lock["popupOpened"], "the pop-up never opened, so closing it was not tested")
        expect(lock["popupClosed"], "the pop-up window stayed open")
        expect(lock["returned"], f"the kiosk did not return to YouTube after the blocked page: {lock}")
        return report_failures(failures)
    report = json.loads((output / "report.json").read_text())
    page_headers = json.loads((output / "page-headers.json").read_text())

    expect(report["exitMode"] == mode, f"page opened with exit={report['exitMode']}, not the launched {mode}: stale settings")
    expect(report["companion"], "companion page script did not run on the first page load")
    expect("Cobalt/" in report["userAgent"], f"navigator.userAgent is not Cobalt: {report['userAgent']}")
    ua_data = report.get("uaData") or {}
    expect(ua_data.get("platform") == "Starboard", f"userAgentData.platform: {ua_data.get('platform')}")
    expect([brand["brand"] for brand in ua_data.get("brands", [])] == ["SteamOSYT"], f"userAgentData.brands: {ua_data.get('brands')}")
    expect(ua_data.get("high", {}).get("architecture") in ("x86", "arm"), f"high entropy values: {ua_data.get('high')}")

    for label, headers in (("navigation", page_headers), ("fetch", report["headers"])):
        expect("Cobalt/" in headers.get("user-agent", ""), f"{label} User-Agent header: {headers.get('user-agent')}")
        expect(headers.get("sec-ch-ua") == '"SteamOSYT";v="27"', f"{label} sec-ch-ua header: {headers.get('sec-ch-ua')}")
        expect(headers.get("sec-ch-ua-platform") == '"Starboard"', f"{label} sec-ch-ua-platform: {headers.get('sec-ch-ua-platform')}")

    mse = report["mse"]
    expect(mse["vp9AbsurdFramerate"] is False, "framerate=9999 should be rejected")
    expect(mse["vp9AbsurdWidth"] is False, "width=99999 should be rejected")
    expect(mse["hdrOnSdrDisplay"] is False, "HDR should be rejected on an SDR display")
    expect(mse["vp9At1080p60"] == mse["vp9"], "1080p60 VP9 should follow the native VP9 answer")

    expect(report["wheelKeys"] == [["down", DOWN], ["up", DOWN]], f"wheel mapping: {report['wheelKeys']}")
    expect(report["cursorHidden"], "cursor should start hidden")
    expect(report["tapA"] == [["down", STARBOARD], ["up", STARBOARD]], f"A button: {report['tapA']}")
    downs = [event for event in report["holdDown"] if event == ["down", DOWN]]
    expect(len(downs) >= 3 and report["holdDown"][-1] == ["up", DOWN], f"held D-pad should repeat: {report['holdDown']}")
    expect(report["stickUp"] == [["down", STICK_UP], ["up", STICK_UP]], f"left stick up: {report['stickUp']}")

    ads = report["ads"]
    if scenario == "close":
        expect(ads["sections"] == ["tvMastheadRenderer", "adSlotRenderer", "promoShelfRenderer", "shelfRenderer"],
               f"with ad blocking off, the home page must keep its ads: {ads['sections']}")
        expect("adSlotRenderer" in ads["shelfItems"], f"with ad blocking off, the shelf must keep its ad: {ads['shelfItems']}")
        expect(ads["player"] == ads["fetchedPlayer"] == list(PLAYER_ADS), f"with ad blocking off, video ads must stay: {ads}")
    else:
        expect(ads["sections"] == ["shelfRenderer"], f"masthead, ad and promoted sections must go: {ads['sections']}")
        expect(set(ads["shelfItems"]) == {"tileRenderer"}, f"sponsored tiles must go: {ads['shelfItems']}")
        expect(ads["player"] == [], f"video ads must go from player responses read with JSON.parse: {ads['player']}")
        expect(ads["fetchedPlayer"] == [], f"video ads must go from player responses read with fetch: {ads['fetchedPlayer']}")
        expect(ads["shorts"] == ["video"], f"ads among Shorts must go: {ads['shorts']}")

    tiles = {tile["id"]: tile for tile in report["deArrow"]}
    expect(tiles[SKIPPED]["title"] == "An Honest Title", f"DeArrow title: {tiles[SKIPPED]['title']}")
    expect(all("i.ytimg.com" in url for url in tiles[SKIPPED]["thumbnails"]), "YouTube's thumbnail URLs must stay in its data")
    violations = report["cspViolations"]
    expect(not report["thumbnailLoads"], "the page itself must still be unable to load DeArrow images")
    expect(any(item["directive"] == "img-src" and "dearrow-thumb" in item["uri"] for item in violations), f"policy not enforced: {violations}")
    expect(not any(item["directive"] == "require-trusted-types-for" for item in violations), f"Trusted Types violations: {violations}")
    overlays = report["overlays"]
    if scenario == "titles-only":
        expect(not any(overlays.values()) and not report["recycledBack"], f"titles-only mode must not lay thumbnails: {overlays}")
    else:
        laid = {"src": DEARROW_THUMBNAIL, "shown": True, "covers": True}
        expect(overlays[SKIPPED] == laid, f"DeArrow thumbnail over YouTube's: {overlays[SKIPPED]}")
        expect(overlays[ORIGINAL] is None and overlays[DOWNVOTED] is None, f"no DeArrow thumbnail expected: {overlays}")
        expect(overlays[BROKEN] is None, f"a DeArrow thumbnail that fails to load must leave YouTube's: {overlays[BROKEN]}")
        expect(report["recycledToOther"] is None, f"a recycled thumbnail kept the old DeArrow image: {report['recycledToOther']}")
        expect(report["recycledBack"] == laid, f"DeArrow thumbnail after recycling: {report['recycledBack']}")
    expect(tiles[RUNS]["title"] == "Calm runs title", f"DeArrow title in runs: {tiles[RUNS]['title']}")
    expect(tiles[ORIGINAL]["title"] == "Original title stays", "an 'original' DeArrow vote must keep the title")
    expect(all("i.ytimg.com" in url for url in tiles[ORIGINAL]["thumbnails"]), "an 'original' vote must keep the thumbnail")
    expect(tiles[DOWNVOTED]["title"] == "Downvoted stays", "a downvoted DeArrow title must be ignored")
    expect(report["passthrough"], "an unrelated XHR must be untouched")

    dislikes = report["dislikes"]
    expect(dislikes["button"] == "1.2K", f"dislike button text: {dislikes['button']}")
    expect(dislikes["factoids"] == [["Likes", "10K"], ["Dislikes", "1.2K"]], f"description factoids: {dislikes['factoids']}")

    sponsor = report["sponsorBlock"]
    expect(sponsor["afterSkip"] == 25, f"sponsor segment should skip to 25 s, got {sponsor['afterSkip']}")
    expect(sponsor["midSegment"] == 15, "seeking into the middle of a segment must not skip it")
    expect(sponsor["toasts"] == ["Skipped sponsor"], f"SponsorBlock toasts: {sponsor['toasts']}")

    api_log = (output / "api.log").read_text().splitlines() if (output / "api.log").exists() else []
    lookups = [line for line in api_log if line.startswith("sponsor.ajay.app")]
    expect(any(re.search(r"/api/skipSegments/[0-9a-f]{4}\?", line) for line in lookups), f"SponsorBlock lookup: {lookups}")
    expect(any(re.search(r"/api/branding/[0-9a-f]{4}\?", line) for line in lookups), f"DeArrow lookup: {lookups}")
    expect(not any(SKIPPED in line for line in lookups), "SponsorBlock/DeArrow lookups must use hash prefixes, not video IDs")
    if scenario != "titles-only":
        images = [line for line in api_log if line.startswith("dearrow-thumb.ajay.app")]
        expect(any(f"videoID={BROKEN}" in line for line in images), f"the failing DeArrow thumbnail was never requested: {images}")

    if expected_cookie != "*":
        cookies = dict(part.strip().split("=", 1) for part in page_headers.get("cookie", "").split(";") if "=" in part)
        actual = cookies.get("probe", "-")
        loads = (output / "tv-requests.log").read_text().splitlines()
        expect(actual == expected_cookie, f"profile cookie: expected {expected_cookie!r}, got {actual!r} (TV page requests: {loads})")

    if mode == "leanback":
        hook = json.loads((output / "hook.json").read_text())
        expect(hook["wrapped"], "Leanback resolveCommand was not wrapped")
        expect(hook["passthrough"] == "native:browseEndpoint", f"other commands must pass through: {hook}")
    return report_failures(failures)


def report_failures(failures) -> int:
    for failure in failures:
        print(f"    FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
