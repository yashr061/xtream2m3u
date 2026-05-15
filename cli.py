#!/usr/bin/env python3
"""xtream2m3u CLI — generate M3U playlists from an Xtream IPTV provider.

Reuses the same service layer as the Flask app, so it accepts every filter
option exposed by the /m3u endpoint. Credentials can be passed as flags or
read from environment variables (XTREAM_URL / XTREAM_USERNAME / XTREAM_PASSWORD).

Examples:
  # Configure credentials once
  export XTREAM_URL=http://iptv.example.com:8080
  export XTREAM_USERNAME=myuser
  export XTREAM_PASSWORD=mypass

  # Print playlist to stdout
  python cli.py

  # Save to file with a filter
  python cli.py --wanted-groups "Sports*,News" --enable-catchup -o playlist.m3u

  # Combine with cron for periodic refresh:
  # 0 */6 * * * python /path/to/cli.py --wanted-groups "..." -o /var/iptv/list.m3u
"""
import argparse
import logging
import os
import sys

from app.services import (
    fetch_categories_and_channels,
    generate_m3u_playlist,
    validate_xtream_credentials,
)
from app.utils import parse_group_list, setup_custom_dns


def main():
    parser = argparse.ArgumentParser(
        prog="xtream2m3u",
        description="Generate an M3U playlist from an Xtream IPTV provider.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Credentials (env vars provide defaults; flags override)
    parser.add_argument("--url", default=os.environ.get("XTREAM_URL"),
                        help="Xtream API URL (env: XTREAM_URL)")
    parser.add_argument("--username", default=os.environ.get("XTREAM_USERNAME"),
                        help="Xtream username (env: XTREAM_USERNAME)")
    parser.add_argument("--password", default=os.environ.get("XTREAM_PASSWORD"),
                        help="Xtream password (env: XTREAM_PASSWORD)")

    # Filters
    parser.add_argument("--wanted-groups", default="",
                        help="Comma-separated groups to include (supports * and ? wildcards)")
    parser.add_argument("--unwanted-groups", default="",
                        help="Comma-separated groups to exclude")

    # Content options
    parser.add_argument("--include-vod", action="store_true",
                        help="Include movies and series (slower, 2-5min)")
    parser.add_argument("--enable-catchup", action="store_true",
                        help="Emit catchup/timeshift tags for archive-enabled channels")
    parser.add_argument("--include-channel-id", action="store_true",
                        help="Include the epg_channel_id tag on each entry")
    parser.add_argument("--channel-id-tag", default="channel-id",
                        help="Custom tag name for channel ID (default: channel-id)")

    # Proxy options
    parser.add_argument("--no-stream-proxy", action="store_true",
                        help="Don't wrap stream URLs through a proxy (URLs stay raw)")
    parser.add_argument("--proxy-url", default=os.environ.get("PROXY_URL", ""),
                        help="Base URL for proxied content (env: PROXY_URL)")

    # Output
    parser.add_argument("-o", "--output", default="-",
                        help="Output file path, or '-' for stdout (default: stdout)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose progress logging to stderr")

    args = parser.parse_args()

    # All logs go to stderr so stdout stays a clean playlist when piping
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(message)s",
    )

    if not args.url or not args.username or not args.password:
        parser.error(
            "URL, username, and password are required. Provide them via "
            "--url/--username/--password or the XTREAM_URL/XTREAM_USERNAME/"
            "XTREAM_PASSWORD environment variables."
        )

    # Same DNS hardening the server uses
    setup_custom_dns()

    user_data, error_json, error_code = validate_xtream_credentials(
        args.url, args.username, args.password
    )
    if error_json:
        print(f"Authentication failed: {error_json}", file=sys.stderr)
        sys.exit(1)

    categories, streams, error_json, error_code = fetch_categories_and_channels(
        args.url, args.username, args.password, args.include_vod, for_m3u=True
    )
    if error_json:
        print(f"Failed to fetch data: {error_json}", file=sys.stderr)
        sys.exit(1)

    server_url = (
        f"http://{user_data['server_info']['url']}:{user_data['server_info']['port']}"
    )

    m3u = generate_m3u_playlist(
        url=args.url,
        username=user_data["user_info"]["username"],
        password=user_data["user_info"]["password"],
        server_url=server_url,
        categories=categories,
        streams=streams,
        wanted_groups=parse_group_list(args.wanted_groups),
        unwanted_groups=parse_group_list(args.unwanted_groups),
        no_stream_proxy=args.no_stream_proxy,
        include_vod=args.include_vod,
        include_channel_id=args.include_channel_id,
        channel_id_tag=args.channel_id_tag,
        enable_catchup=args.enable_catchup,
        proxy_url=args.proxy_url,
    )

    if args.output == "-":
        sys.stdout.write(m3u)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(m3u)
        print(f"Wrote playlist to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
