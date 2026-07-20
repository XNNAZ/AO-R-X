import os
import re
from flask import Flask, jsonify, redirect, request

app = Flask(__name__)

M3U_FILE_PATH = "playlist.m3u"

STREAMS = {"live": {}, "vod": {}, "series": {}}
CATEGORIES = {"live": {}, "vod": {}, "series": {}}


def classify_media(group_title, name, url):
    """Smart classification using URL extensions, title patterns, and group tags."""
    gt_lower = group_title.lower()
    name_lower = name.lower()
    url_lower = url.lower()

    # 1. Check URL extensions for VOD
    vod_extensions = (".mp4", ".mkv", ".avi", ".mov", ".flv")
    if any(url_lower.endswith(ext) or ext in url_lower for ext in vod_extensions):
        # Even if it's video, check if it's a TV Series episode
        if re.search(r"s\d{1,2}\s?e\d{1,2}|season|episode|\be\d{2}\b", name_lower):
            return "series"
        return "vod"

    # 2. Check Regex for Series (e.g., S01E01, S1 E05, Season 2, Ep 10)
    series_regex = r"s\d{1,2}\s?e\d{1,2}|s\d{1,2}\b|season\s?\d|episode\s?\d|\bep?\d{2}\b"
    if re.search(series_regex, name_lower) or re.search(series_regex, gt_lower):
        return "series"

    # 3. Series Group Keywords
    series_keywords = [
        "series",
        "serie",
        "s0",
        "s1",
        "s2",
        "s3",
        "tv show",
        "shows",
        "episodes",
        "مسلسلات",
        "مسلسل",
    ]
    if any(kw in gt_lower for kw in series_keywords):
        return "series"

    # 4. VOD / Movie Group & Name Keywords
    vod_keywords = [
        "movie",
        "movies",
        "film",
        "films",
        "vod",
        "cinema",
        "4k movie",
        "box office",
        "netflix",
        "shahid",
        "disney",
        "hbo",
        "apple tv",
        "amazon",
        "documentary",
        "افلام",
        "فيلم",
        "سينما",
    ]
    if any(kw in gt_lower for kw in vod_keywords):
        return "vod"

    # Fallback to Live TV
    return "live"


def load_m3u_file():
    global STREAMS, CATEGORIES
    for k in STREAMS:
        STREAMS[k].clear()
        CATEGORIES[k].clear()

    if not os.path.exists(M3U_FILE_PATH):
        print(
            f"[!] Warning: {M3U_FILE_PATH} not found. Place it in the server folder."
        )
        return

    counters = {
        "live": {"cat": 1, "stream": 1},
        "vod": {"cat": 1, "stream": 1},
        "series": {"cat": 1, "stream": 1},
    }

    with open(M3U_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    current_metadata = {}

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF"):
            logo_match = re.search(r'tvg-logo="(.*?)"', line)
            logo = logo_match.group(1) if logo_match else ""

            group_match = re.search(r'group-title="(.*?)"', line)
            cat_name = (
                group_match.group(1) if group_match else "Uncategorized"
            )

            name = line.split(",")[-1].strip()

            current_metadata = {
                "name": name,
                "stream_icon": logo,
                "cat_name": cat_name,
            }

        elif line and not line.startswith("#"):
            if current_metadata:
                target_url = line
                cat_name = current_metadata["cat_name"]
                name = current_metadata["name"]

                # Perform classification with full context
                stype = classify_media(cat_name, name, target_url)

                # Assign isolated Category ID
                cat_dict = CATEGORIES[stype]
                if cat_name not in cat_dict.values():
                    cat_id = str(counters[stype]["cat"])
                    cat_dict[cat_id] = cat_name
                    counters[stype]["cat"] += 1
                else:
                    cat_id = [k for k, v in cat_dict.items() if v == cat_name][0]

                stream_id = str(counters[stype]["stream"])
                counters[stype]["stream"] += 1

                STREAMS[stype][stream_id] = {
                    "name": name,
                    "stream_icon": current_metadata["stream_icon"],
                    "category_id": cat_id,
                    "stream_id": stream_id,
                    "target_url": target_url,
                    "type": stype,
                }
                current_metadata = {}

    print("\n==========================================")
    print(f"[+] Total Streams Parsed:")
    print(f"    - Live TV Categories : {len(CATEGORIES['live'])}")
    print(f"    - Live TV Channels   : {len(STREAMS['live'])}")
    print(f"    - VOD Movies         : {len(STREAMS['vod'])}")
    print(f"    - TV Series          : {len(STREAMS['series'])}")
    print("==========================================\n")


@app.route("/player_api.php", methods=["GET", "POST"])
def xtream_api():
    action = request.args.get("action")
    username = request.args.get("username", "admin")

    # 1. Login Authentication
    if not action:
        return jsonify({
            "user_info": {
                "auth": 1,
                "status": "Active",
                "username": username,
                "exp_date": "null",
                "is_trial": "0",
            },
            "server_info": {
                "url": request.host.split(":")[0],
                "port": (
                    request.host.split(":")[1]
                    if ":" in request.host
                    else "80"
                ),
                "server_protocol": "http",
            },
        })

    # 2. Filtered Category Endpoints
    if action == "get_live_categories":
        active_ids = {data["category_id"] for data in STREAMS["live"].values()}
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["live"].items()
            if cid in active_ids
        ])

    if action == "get_vod_categories":
        active_ids = {data["category_id"] for data in STREAMS["vod"].values()}
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["vod"].items()
            if cid in active_ids
        ])

    if action == "get_series_categories":
        active_ids = {
            data["category_id"] for data in STREAMS["series"].values()
        }
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["series"].items()
            if cid in active_ids
        ])

    # 3. Stream List Endpoints
    if action == "get_live_streams":
        return jsonify([
            {
                "num": idx + 1,
                "name": data["name"],
                "stream_type": "live",
                "stream_id": sid,
                "stream_icon": data["stream_icon"],
                "category_id": data["category_id"],
            }
            for idx, (sid, data) in enumerate(STREAMS["live"].items())
        ])

    if action == "get_vod_streams":
        return jsonify([
            {
                "num": idx + 1,
                "name": data["name"],
                "stream_type": "movie",
                "stream_id": sid,
                "stream_icon": data["stream_icon"],
                "category_id": data["category_id"],
                "container_extension": "m3u8",
            }
            for idx, (sid, data) in enumerate(STREAMS["vod"].items())
        ])

    if action == "get_series":
        return jsonify([
            {
                "num": idx + 1,
                "name": data["name"],
                "series_id": sid,
                "cover": data["stream_icon"],
                "category_id": data["category_id"],
            }
            for idx, (sid, data) in enumerate(STREAMS["series"].items())
        ])

    return jsonify([])


@app.route("/get.php", methods=["GET", "POST"])
def get_m3u_playlist():
    username = request.args.get("username", "admin")
    password = request.args.get("password", "admin")

    lines = ["#EXTM3U"]
    base_url = request.host_url.rstrip("/")

    for stype in ["live", "vod", "series"]:
        route_prefix = (
            "live"
            if stype == "live"
            else ("movie" if stype == "vod" else "series")
        )
        for sid, data in STREAMS[stype].items():
            name = data.get("name", "Unknown")
            logo = data.get("stream_icon", "")
            cat_id = data.get("category_id", "")
            category = CATEGORIES[stype].get(cat_id, "Uncategorized")

            playback_url = (
                f"{base_url}/{route_prefix}/{username}/{password}/{sid}.m3u8"
            )
            extinf = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{category}", {name}'
            lines.append(extinf)
            lines.append(playback_url)

    return "\n".join(lines), 200, {"Content-Type": "application/x-mpegurl"}


@app.route("/<stream_type>/<username>/<password>/<stream_id>")
def play_media(stream_type, username, password, stream_id):
    clean_id = re.sub(r"\D", "", stream_id.split(".")[0])

    type_map = {"live": "live", "movie": "vod", "series": "series"}
    stype = type_map.get(stream_type, "live")

    if clean_id in STREAMS[stype]:
        target_url = STREAMS[stype][clean_id]["target_url"]
        print(f"[*] App requested [{stype}] ID {clean_id} -> {target_url}")
        return redirect(target_url, code=302)

    return "Stream not found", 404


load_m3u_file()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
