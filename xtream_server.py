from flask import Flask, jsonify, redirect, request
import os
import re

app = Flask(__name__)

# Define file paths for the three separate M3U files
M3U_FILES = {
    "live": "xtream_live.m3u",
    "vod": "xtream_vod.m3u",
    "series": "xtream_series.m3u",
}

STREAMS = {"live": {}, "vod": {}, "series": {}}
CATEGORIES = {"live": {}, "vod": {}, "series": {}}


def load_m3u_file(file_path, stype):
    """Parses a specific M3U file into its designated stream type."""
    if not os.path.exists(file_path):
        print(f"[!] File not found: {file_path} (Skipping...)")
        return

    cat_counter = 1
    stream_counter = 1

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
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

                # Assign Category ID within this specific category pool
                cat_dict = CATEGORIES[stype]
                if cat_name not in cat_dict.values():
                    cat_id = str(cat_counter)
                    cat_dict[cat_id] = cat_name
                    cat_counter += 1
                else:
                    cat_id = [k for k, v in cat_dict.items() if v == cat_name][0]

                stream_id = str(stream_counter)
                stream_counter += 1

                STREAMS[stype][stream_id] = {
                    "name": current_metadata["name"],
                    "stream_icon": current_metadata["stream_icon"],
                    "category_id": cat_id,
                    "stream_id": stream_id,
                    "target_url": target_url,
                }
                current_metadata = {}

    print(
        f"[+] Loaded {file_path}: {len(STREAMS[stype])} items, {len(CATEGORIES[stype])} categories"
    )


def load_all_m3u_files():
    """Clears memory and loads all 3 M3U playlists."""
    global STREAMS, CATEGORIES
    for k in STREAMS:
        STREAMS[k].clear()
        CATEGORIES[k].clear()

    print("\n==========================================")
    print("Loading Media Playlists...")
    print("==========================================")
    for stype, file_path in M3U_FILES.items():
        load_m3u_file(file_path, stype)
    print("==========================================\n")


@app.route("/player_api.php", methods=["GET", "POST"])
def xtream_api():
    action = request.args.get("action")
    username = request.args.get("username", "admin")
    password = request.args.get("password", "admin")

    # 1. Login Authentication (Fixed for IPTV Smarters, TiviMate, and XCIPTV compatibility)
    if not action:
        host = request.host.split(":")[0]
        return jsonify({
            "user_info": {
                "auth": 1,
                "status": "Active",
                "username": username,
                "password": password,
                "message": "Welcome",
                "auth_date": 1600000000,
                "exp_date": "1988121600",  # Timestamp in far future to mark account as Active
                "is_trial": "0",
                "active_cons": "0",
                "created_at": "1600000000",
                "max_connections": "100",
                "allowed_output_formats": ["m3u8", "ts", "mp4", "mkv"],
            },
            "server_info": {
                "url": host,
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "8880",
                "timezone": "UTC",
                "timestamp_now": 1600000000,
                "time_now": "2026-07-20 05:00:00",
            },
        })

    # 2. Category Endpoints
    if action == "get_live_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["live"].items()
        ])

    if action == "get_vod_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["vod"].items()
        ])

    if action == "get_series_categories":
        return jsonify([
            {"category_id": cid, "category_name": cname, "parent_id": 0}
            for cid, cname in CATEGORIES["series"].items()
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


load_all_m3u_files()

if __name__ == "__main__":
    # Railway passes the assigned port in the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
