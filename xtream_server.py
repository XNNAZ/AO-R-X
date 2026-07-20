from flask import Flask, jsonify, redirect, request
import os
import re

app = Flask(__name__)

M3U_FILE_PATH = "playlist.m3u"

# In-memory storage broken down by stream type
STREAMS = {"live": {}, "vod": {}, "series": {}}

CATEGORIES = {"live": {}, "vod": {}, "series": {}}


def classify_category(group_title):
    """Determines whether an entry belongs to Live, VOD, or Series based on group tags."""
    gt = group_title.lower()
    if any(keyword in gt for keyword in ["series", "season", "s0", "tv show"]):
        return "series"
    elif any(
        keyword in gt for keyword in ["movie", "vod", "cinema", "films", "4k"]
    ):
        return "vod"
    # Default to live if no explicit movie/series hints are found
    return "live"


def load_m3u_file():
    global STREAMS, CATEGORIES
    for k in STREAMS:
        STREAMS[k].clear()
        CATEGORIES[k].clear()

    if not os.path.exists(M3U_FILE_PATH):
        print(f"[!] Warning: {M3U_FILE_PATH} not found.")
        return

    counters = {
        "live": {"cat": 1, "stream": 1},
        "vod": {"cat": 1, "stream": 1},
        "series": {"cat": 1, "stream": 1},
    }

    with open(M3U_FILE_PATH, "r", encoding="utf-8") as f:
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
            stype = classify_category(cat_name)

            # Assign Category ID within its specific type pool
            cat_dict = CATEGORIES[stype]
            if cat_name not in cat_dict.values():
                cat_id = str(counters[stype]["cat"])
                cat_dict[cat_id] = cat_name
                counters[stype]["cat"] += 1
            else:
                cat_id = [k for k, v in cat_dict.items() if v == cat_name][0]

            stream_id = str(counters[stype]["stream"])
            counters[stype]["stream"] += 1

            current_metadata = {
                "name": name,
                "stream_icon": logo,
                "category_id": cat_id,
                "stream_id": stream_id,
                "type": stype,
            }

        elif line and not line.startswith("#"):
            if current_metadata:
                stype = current_metadata["type"]
                current_metadata["target_url"] = line
                STREAMS[stype][current_metadata["stream_id"]] = (
                    current_metadata
                )
                current_metadata = {}

    print(
        f"[+] Loaded -> Live: {len(STREAMS['live'])}, VOD: {len(STREAMS['vod'])}, Series: {len(STREAMS['series'])}"
    )


@app.route("/player_api.php", methods=["GET", "POST"])
def xtream_api():
    action = request.args.get("action")
    username = request.args.get("username", "admin")

    # 1. Login / Server Handshake
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

    # 2. Category Handlers
    category_map = {
        "get_live_categories": "live",
        "get_vod_categories": "vod",
        "get_series_categories": "series",
    }
    if action in category_map:
        stype = category_map[action]
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES[stype].items()
        ])

    # 3. Stream List Handlers
    if action == "get_live_streams":
        return jsonify([
            {
                "num": idx + 1,
                "name": data["name"],
                "stream_type": "live",
                "stream_id": sid,
                "stream_icon": data["stream_icon"],
                "category_id": data["category_id"],
                "custom_sid": "",
                "direct_source": "",
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

    # Build M3U with proper route prefix for each media type
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


# 4. Universal Playback Redirect (Live, Movies, Series)
@app.route("/<stream_type>/<username>/<password>/<stream_id>")
def play_media(stream_type, username, password, stream_id):
    clean_id = re.sub(r"\D", "", stream_id.split(".")[0])

    # Convert route to internal storage key
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
