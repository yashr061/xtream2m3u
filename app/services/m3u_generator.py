"""M3U playlist generation service"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.xtream_api import fetch_series_episodes
from app.utils import encode_url, group_matches

logger = logging.getLogger(__name__)


def generate_m3u_playlist(
    url,
    username,
    password,
    server_url,
    categories,
    streams,
    wanted_groups=None,
    unwanted_groups=None,
    no_stream_proxy=False,
    include_series=False,
    include_channel_id=False,
    channel_id_tag="channel-id",
    enable_catchup=False,
    proxy_url=None,
):
    """
    Generate an M3U playlist from Xtream API data

    Args:
        url: Xtream API base URL
        username: Xtream API username
        password: Xtream API password
        server_url: Server URL for streaming
        categories: List of categories
        streams: List of streams
        wanted_groups: List of group patterns to include (optional)
        unwanted_groups: List of group patterns to exclude (optional)
        no_stream_proxy: Whether to disable stream proxying
        include_series: Whether series content is present in `streams` (gates per-series episode fetching)
        include_channel_id: Whether to include channel IDs
        channel_id_tag: Tag name for channel IDs
        enable_catchup: Whether to emit catchup/timeshift tags for archive-enabled channels
        proxy_url: Proxy URL for images and streams

    Returns:
        M3U playlist string
    """
    # Create category name lookup
    category_names = {cat["category_id"]: cat["category_name"] for cat in categories}

    # Log all available groups
    all_groups = set(category_names.values())
    logger.info(f"All available groups: {sorted(all_groups)}")

    # Generate M3U playlist
    m3u_playlist = "#EXTM3U\n"

    # Track included groups
    included_groups = set()
    processed_streams = 0
    catchup_count = 0
    total_streams = len(streams)

    # Pre-compile filter patterns for massive filter lists (performance optimization)
    wanted_patterns = (
        [pattern.lower() for pattern in wanted_groups] if wanted_groups else []
    )
    unwanted_patterns = (
        [pattern.lower() for pattern in unwanted_groups] if unwanted_groups else []
    )

    logger.info(f"🔍 Starting to filter {total_streams} streams...")
    batch_size = 10000  # Process streams in batches for better performance

    # Filter series to fetch episodes for (optimization to avoid fetching episodes for excluded series)
    series_episodes_map = {}
    if include_series:
        series_streams = [s for s in streams if s.get("content_type") == "series"]
        if series_streams:
            logger.info(
                f"Found {len(series_streams)} series. Filtering to determine which need episodes..."
            )

            series_to_fetch = []
            for stream in series_streams:
                # Get raw category name for filtering
                category_name = category_names.get(
                    stream.get("category_id"), "Uncategorized"
                )

                # Calculate group_title (prefixed)
                group_title = f"Series - {category_name}"

                # Check filter against both raw category name and prefixed name
                # This ensures we match "Action" (raw) AND "Series - Action" (prefixed)
                should_fetch = True
                if wanted_patterns:
                    should_fetch = any(
                        group_matches(category_name, w) or group_matches(group_title, w)
                        for w in wanted_groups
                    )
                elif unwanted_patterns:
                    should_fetch = not any(
                        group_matches(category_name, u) or group_matches(group_title, u)
                        for u in unwanted_groups
                    )

                if should_fetch:
                    series_to_fetch.append(stream)

            if series_to_fetch:
                logger.info(
                    f"Fetching episodes for {len(series_to_fetch)} series (this might take a while)..."
                )

                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_series = {
                        executor.submit(
                            fetch_series_episodes,
                            url,
                            username,
                            password,
                            s.get("series_id"),
                        ): s.get("series_id")
                        for s in series_to_fetch
                    }

                    completed_fetches = 0
                    for future in as_completed(future_to_series):
                        s_id, episodes = future.result()
                        if episodes:
                            series_episodes_map[s_id] = episodes

                        completed_fetches += 1
                        if completed_fetches % 50 == 0:
                            logger.info(
                                f"  Fetched episodes for {completed_fetches}/{len(series_to_fetch)} series"
                            )

                logger.info(
                    f"✅ Fetched episodes for {len(series_episodes_map)} series"
                )

    for stream in streams:
        content_type = stream.get("content_type", "live")
        skip_proxy_for_stream = False

        # Get raw category name
        category_name = category_names.get(stream.get("category_id"), "Uncategorized")

        # Determine group title based on content type
        if content_type == "series":
            # For series, use series name as group title
            group_title = f"Series - {category_name}"
            stream_name = stream.get("name", "Unknown Series")
        else:
            # For live and VOD content
            group_title = category_name
            stream_name = stream.get("name", "Unknown")

            # Add content type prefix for VOD
            if content_type == "vod":
                group_title = f"VOD - {category_name}"

        # Optimized filtering logic using pre-compiled patterns
        include_stream = True

        if wanted_patterns:
            # Only include streams from specified groups (optimized matching)
            # Check both raw category name and final group title to support flexible filtering
            include_stream = any(
                group_matches(category_name, wanted_group)
                or group_matches(group_title, wanted_group)
                for wanted_group in wanted_groups
            )
        elif unwanted_patterns:
            # Exclude streams from unwanted groups (optimized matching)
            include_stream = not any(
                group_matches(category_name, unwanted_group)
                or group_matches(group_title, unwanted_group)
                for unwanted_group in unwanted_groups
            )

        processed_streams += 1

        # Progress logging for large datasets
        if processed_streams % batch_size == 0:
            logger.info(
                f"  📊 Processed {processed_streams}/{total_streams} streams ({(processed_streams/total_streams)*100:.1f}%)"
            )

        if include_stream:
            included_groups.add(group_title)

            tags = [
                f'tvg-name="{stream_name}"',
                f'group-title="{group_title}"',
            ]

            # Handle logo URL - proxy only if stream proxying is enabled
            original_logo = stream.get("stream_icon", "")
            if original_logo and not no_stream_proxy:
                logo_url = f"{proxy_url}/image-proxy/{encode_url(original_logo)}"
            else:
                logo_url = original_logo
            tags.append(f'tvg-logo="{logo_url}"')

            # Handle channel id if enabled
            if include_channel_id:
                channel_id = stream.get("epg_channel_id")
                if channel_id:
                    tags.append(f'{channel_id_tag}="{channel_id}"')

            # Create the stream URL based on content type
            if content_type == "live":
                # Live TV streams
                stream_url = (
                    f"{server_url}/live/{username}/{password}/{stream['stream_id']}.ts"
                )

                # Catchup (timeshift) tags for archive-enabled channels.
                # Kodi IPTV Simple Client and similar players parse the live URL to
                # build timeshift URLs, so the URL must stay raw (no proxy wrap).
                if enable_catchup and str(stream.get("tv_archive", 0)) == "1":
                    try:
                        days = int(stream.get("tv_archive_duration", 0))
                    except (ValueError, TypeError):
                        days = 0
                    if days > 0:
                        tags.append('catchup="xtream-codes"')
                        tags.append(f'catchup-days="{days}"')
                        catchup_count += 1
                        skip_proxy_for_stream = True
            elif content_type == "vod":
                # VOD streams
                stream_url = f"{server_url}/movie/{username}/{password}/{stream['stream_id']}.{stream.get('container_extension', 'mp4')}"
            elif content_type == "series":
                # Series streams - check if we have episodes
                episodes_data = series_episodes_map.get(stream.get("series_id"))

                if episodes_data:
                    if isinstance(episodes_data, dict):
                        # Sort seasons numerically if possible
                        try:
                            sorted_seasons = sorted(
                                episodes_data.items(),
                                key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to sort seasons for series {stream.get('series_id')}: {e}"
                            )
                            sorted_seasons = list(episodes_data.items())
                    elif isinstance(episodes_data, list):
                        # If it's a list, it might be:
                        # 1. A list of seasons (each season is a list of episodes)
                        # 2. A flat list of episodes (treat as season 1)
                        logger.warning(
                            f"Series {stream.get('series_id')} has episodes as list, processing..."
                        )
                        sorted_seasons = []
                        for idx, item in enumerate(episodes_data):
                            if isinstance(item, list):
                                # It's a list of lists (seasons)
                                sorted_seasons.append((idx + 1, item))
                            elif isinstance(item, dict):
                                # It's a flat list of episodes, treat as season 1
                                sorted_seasons = [(1, episodes_data)]
                                break
                            else:
                                logger.error(
                                    f"Unexpected item type in episodes list: {type(item)}"
                                )
                                continue
                    else:
                        logger.error(
                            f"Unexpected episodes_data type for series {stream.get('series_id')}: {type(episodes_data)}"
                        )
                        continue

                    for season_num, episodes in sorted_seasons:
                        # Ensure episodes is a list
                        if not isinstance(episodes, list):
                            logger.error(
                                f"Expected list of episodes for season {season_num}, got {type(episodes)}"
                            )
                            continue

                        for episode in episodes:
                            # Ensure episode is a dict
                            if not isinstance(episode, dict):
                                logger.error(
                                    f"Expected dict for episode, got {type(episode)}"
                                )
                                continue

                            episode_id = episode.get("id")
                            episode_num = episode.get("episode_num")
                            episode_title = episode.get("title")
                            container_ext = episode.get("container_extension", "mp4")

                            # Format title: Series Name - S01E01 - Episode Title
                            full_title = f"{stream_name} - S{str(season_num).zfill(2)}E{str(episode_num).zfill(2)} - {episode_title}"

                            # Build stream URL for episode
                            ep_stream_url = f"{server_url}/series/{username}/{password}/{episode_id}.{container_ext}"

                            # Apply stream proxying if enabled
                            if not no_stream_proxy:
                                ep_stream_url = f"{proxy_url}/stream-proxy/{encode_url(ep_stream_url)}"

                            # Add to playlist
                            m3u_playlist += f'#EXTINF:0 {" ".join(tags)},{full_title}\n'
                            m3u_playlist += f"{ep_stream_url}\n"

                    # Continue to next stream as we've added all episodes
                    continue
                else:
                    # Fallback for series without episode data
                    series_id = stream.get("series_id", stream.get("stream_id", ""))
                    stream_url = (
                        f"{server_url}/series/{username}/{password}/{series_id}.mp4"
                    )

            # Apply stream proxying if enabled (for non-series, or series fallback)
            if not no_stream_proxy and not skip_proxy_for_stream:
                stream_url = f"{proxy_url}/stream-proxy/{encode_url(stream_url)}"

            # Add stream to playlist
            m3u_playlist += f'#EXTINF:0 {" ".join(tags)},{stream_name}\n'
            m3u_playlist += f"{stream_url}\n"

    # Log included groups after filtering
    logger.info(f"Groups included after filtering: {sorted(included_groups)}")
    logger.info(
        f"Groups excluded after filtering: {sorted(all_groups - included_groups)}"
    )
    logger.info(
        f"✅ M3U generation complete! Generated playlist with {len(included_groups)} groups"
    )
    if enable_catchup:
        logger.info(f"📼 Emitted catchup tags for {catchup_count} channels (proxy bypassed for those)")

    return m3u_playlist


def generate_episodes_playlist(
    url,
    username,
    password,
    server_url,
    series_ids,
    series_meta,
    category_names,
    no_stream_proxy=False,
    proxy_url=None,
):
    """Generate an M3U playlist of episodes for a specific set of series IDs.

    Backs the /episodes API endpoint. Fetches episode lists concurrently for the
    requested series only, so it stays fast even when the provider catalog is huge.

    Args:
        series_ids: list of series IDs to fetch episodes for
        series_meta: dict mapping series_id -> {"name": ..., "category_id": ...}
        category_names: dict mapping category_id -> category_name
    """
    if not series_ids:
        return "#EXTM3U\n"

    logger.info(f"Fetching episodes for {len(series_ids)} series concurrently...")
    episodes_map = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_series_episodes, url, username, password, sid): sid
            for sid in series_ids
        }
        for future in as_completed(futures):
            sid, episodes = future.result()
            if episodes:
                episodes_map[sid] = episodes

    m3u = "#EXTM3U\n"
    episode_count = 0

    for sid in series_ids:
        # Series IDs can come as ints or strings; normalize for lookup
        meta = series_meta.get(str(sid)) or series_meta.get(sid) or {}
        series_name = meta.get("name", f"Series {sid}")
        category_id = meta.get("category_id")
        category_name = category_names.get(category_id, "Uncategorized")
        group_title = f"Series - {category_name}"
        series_cover = meta.get("cover") or ""

        episodes_data = episodes_map.get(sid)
        if not episodes_data:
            logger.warning(f"No episodes found for series {sid} ({series_name})")
            continue

        # Same defensive shape handling as the main generator
        if isinstance(episodes_data, dict):
            try:
                sorted_seasons = sorted(
                    episodes_data.items(),
                    key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999,
                )
            except Exception:
                sorted_seasons = list(episodes_data.items())
        elif isinstance(episodes_data, list):
            sorted_seasons = []
            for idx, item in enumerate(episodes_data):
                if isinstance(item, list):
                    sorted_seasons.append((idx + 1, item))
                elif isinstance(item, dict):
                    sorted_seasons = [(1, episodes_data)]
                    break
        else:
            logger.warning(f"Unexpected episodes shape for series {sid}: {type(episodes_data)}")
            continue

        for season_num, episodes in sorted_seasons:
            if not isinstance(episodes, list):
                continue
            for episode in episodes:
                if not isinstance(episode, dict):
                    continue

                episode_id = episode.get("id")
                episode_num = episode.get("episode_num")
                episode_title = episode.get("title", "")
                container_ext = episode.get("container_extension", "mp4")

                full_title = f"{series_name} - S{str(season_num).zfill(2)}E{str(episode_num).zfill(2)} - {episode_title}"
                ep_url = f"{server_url}/series/{username}/{password}/{episode_id}.{container_ext}"

                if not no_stream_proxy and proxy_url:
                    ep_url = f"{proxy_url}/stream-proxy/{encode_url(ep_url)}"

                # Prefer the per-episode image (often a screenshot) and fall
                # back to the series cover so every entry still gets a logo.
                episode_info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
                original_logo = (
                    episode_info.get("movie_image")
                    or episode_info.get("cover_big")
                    or series_cover
                )
                if original_logo and not no_stream_proxy and proxy_url:
                    logo_url = f"{proxy_url}/image-proxy/{encode_url(original_logo)}"
                else:
                    logo_url = original_logo or ""

                tags = [
                    f'tvg-name="{full_title}"',
                    f'tvg-logo="{logo_url}"',
                    f'group-title="{group_title}"',
                ]
                m3u += f'#EXTINF:0 {" ".join(tags)},{full_title}\n'
                m3u += f"{ep_url}\n"
                episode_count += 1

    logger.info(f"✅ Episodes playlist complete: {episode_count} episodes across {len(series_ids)} series")
    return m3u
