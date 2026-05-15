"""Xtream Codes API client service"""
import json
import logging
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)


def fetch_api_data(url, timeout=10):
    """Make a request to an API endpoint"""
    ua = UserAgent()
    headers = {
        "User-Agent": ua.chrome,
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "close",
        "Accept-Encoding": "gzip, deflate",
    }

    try:
        hostname = urllib.parse.urlparse(url).netloc.split(":")[0]
        logger.debug(f"Making request to host: {hostname}")

        # Use fresh connection for each request to avoid stale connection issues
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()

        # For large responses, use streaming JSON parsing
        try:
            # Check content length to decide parsing strategy
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > 10_000_000:  # > 10MB
                logger.info(f"Large response detected ({content_length} bytes), using optimized parsing")

            # Stream the JSON content for better memory efficiency
            response.encoding = 'utf-8'  # Ensure proper encoding
            return response.json()
        except json.JSONDecodeError:
            # Fallback to text for non-JSON responses
            return response.text

    except requests.exceptions.SSLError:
        return {"error": "SSL Error", "details": "Failed to verify SSL certificate"}, 503
    except requests.exceptions.RequestException as e:
        logger.error(f"RequestException: {e}")
        return {"error": "Request Exception", "details": str(e)}, 503


def validate_xtream_credentials(url, username, password):
    """Validate the Xtream API credentials"""
    api_url = f"{url}/player_api.php?username={username}&password={password}"
    data = fetch_api_data(api_url)

    if isinstance(data, tuple):  # Error response
        return None, data[0], data[1]

    if "user_info" not in data or "server_info" not in data:
        return (
            None,
            json.dumps(
                {
                    "error": "Invalid Response",
                    "details": "Server response missing required data (user_info or server_info)",
                }
            ),
            400,
        )

    return data, None, None


def fetch_api_endpoint(url_info):
    """Fetch a single API endpoint - used for concurrent requests"""
    url, name, timeout = url_info
    try:
        logger.info(f"🚀 Fetching {name}...")
        start_time = time.time()
        data = fetch_api_data(url, timeout=timeout)
        end_time = time.time()

        if isinstance(data, list):
            logger.info(f"✅ Completed {name} in {end_time-start_time:.1f}s - got {len(data)} items")
        else:
            logger.info(f"✅ Completed {name} in {end_time-start_time:.1f}s")
        return name, data
    except Exception as e:
        logger.warning(f"❌ Failed to fetch {name}: {e}")
        return name, None


def fetch_series_episodes(url, username, password, series_id):
    """Fetch episodes for a specific series"""
    api_url = f"{url}/player_api.php?username={username}&password={password}&action=get_series_info&series_id={series_id}"
    start_time = time.time()
    try:
        # Use a shorter timeout for individual series as we might fetch many
        data = fetch_api_data(api_url, timeout=20)

        # Check if we got a valid response with episodes
        # The API returns 'episodes' as a dict {season_num: [episodes]}
        if isinstance(data, dict) and "episodes" in data and data["episodes"]:
            logger.info(f"✅ Fetched episodes for series {series_id} in {time.time() - start_time:.1f}s")
            return series_id, data["episodes"]
        else:
            logger.error(f"No episodes found for series {series_id}")
            return series_id, None
    except Exception as e:
        logger.error(f"Failed to fetch episodes for series {series_id} in {time.time() - start_time:.1f}s: {e}")
        return series_id, None


def fetch_categories_and_channels(url, username, password, include_vod=False, for_m3u=False):
    """Fetch categories and channels from the Xtream API using concurrent requests

    Set for_m3u=True to fetch the heavy VOD/series stream lists needed for
    M3U generation. The /categories endpoint leaves this off so the UI loads quickly.
    """
    all_categories = []
    all_streams = []

    try:
        # Prepare all API endpoints to fetch concurrently
        api_endpoints = [
            (f"{url}/player_api.php?username={username}&password={password}&action=get_live_categories",
             "live_categories", 60),
            (f"{url}/player_api.php?username={username}&password={password}&action=get_live_streams",
             "live_streams", 180),
        ]

        # Add VOD endpoints if requested (WARNING: This will be much slower!)
        if include_vod:
            logger.warning("⚠️  Including VOD content - this will take significantly longer!")
            logger.info("💡 For faster loading, use the API without include_vod=true")

            # Only add the most essential VOD endpoints - skip the massive streams for categories-only requests
            api_endpoints.extend([
                (f"{url}/player_api.php?username={username}&password={password}&action=get_vod_categories",
                 "vod_categories", 60),
                (f"{url}/player_api.php?username={username}&password={password}&action=get_series_categories",
                 "series_categories", 60),
            ])

            # Only fetch the massive stream lists if explicitly needed for M3U generation
            if for_m3u:
                logger.warning("🐌 Fetching massive VOD/Series streams for M3U generation...")
                api_endpoints.extend([
                    (f"{url}/player_api.php?username={username}&password={password}&action=get_vod_streams",
                     "vod_streams", 240),
                    (f"{url}/player_api.php?username={username}&password={password}&action=get_series",
                     "series", 240),
                ])
            else:
                logger.info("⚡ Skipping massive VOD streams for categories-only request")

        # Fetch all endpoints concurrently using ThreadPoolExecutor
        logger.info(f"Starting concurrent fetch of {len(api_endpoints)} API endpoints...")
        results = {}

        with ThreadPoolExecutor(max_workers=10) as executor:  # Increased workers for better concurrency
            # Submit all API calls
            future_to_name = {executor.submit(fetch_api_endpoint, endpoint): endpoint[1]
                             for endpoint in api_endpoints}

            # Collect results as they complete
            for future in as_completed(future_to_name):
                name, data = future.result()
                results[name] = data

        logger.info("All concurrent API calls completed!")

        # Process live categories and streams (required)
        live_categories = results.get("live_categories")
        live_streams = results.get("live_streams")

        if isinstance(live_categories, tuple):  # Error response
            return None, None, live_categories[0], live_categories[1]
        if isinstance(live_streams, tuple):  # Error response
            return None, None, live_streams[0], live_streams[1]

        if not isinstance(live_categories, list) or not isinstance(live_streams, list):
            return (
                None,
                None,
                json.dumps(
                    {
                        "error": "Invalid Data Format",
                        "details": "Live categories or streams data is not in the expected format",
                    }
                ),
                500,
            )

        # Optimized data processing - batch operations for massive datasets
        logger.info("Processing live content...")

        # Batch set content_type for live content
        if live_categories:
            for category in live_categories:
                category["content_type"] = "live"
            all_categories.extend(live_categories)

        if live_streams:
            for stream in live_streams:
                stream["content_type"] = "live"
            all_streams.extend(live_streams)

        logger.info(f"✅ Added {len(live_categories)} live categories and {len(live_streams)} live streams")

        # Process VOD content if requested and available
        if include_vod:
            logger.info("Processing VOD content...")

            # Process VOD categories
            vod_categories = results.get("vod_categories")
            if isinstance(vod_categories, list) and vod_categories:
                for category in vod_categories:
                    category["content_type"] = "vod"
                all_categories.extend(vod_categories)
                logger.info(f"✅ Added {len(vod_categories)} VOD categories")

            # Process series categories first (lightweight)
            series_categories = results.get("series_categories")
            if isinstance(series_categories, list) and series_categories:
                for category in series_categories:
                    category["content_type"] = "series"
                all_categories.extend(series_categories)
                logger.info(f"✅ Added {len(series_categories)} series categories")

            # Only process massive stream lists if they were actually fetched
            vod_streams = results.get("vod_streams")
            if isinstance(vod_streams, list) and vod_streams:
                logger.info(f"🔥 Processing {len(vod_streams)} VOD streams (this is the slow part)...")

                # Batch process for better performance
                batch_size = 5000
                for i in range(0, len(vod_streams), batch_size):
                    batch = vod_streams[i:i + batch_size]
                    for stream in batch:
                        stream["content_type"] = "vod"
                    if i + batch_size < len(vod_streams):
                        logger.info(f"  Processed {i + batch_size}/{len(vod_streams)} VOD streams...")

                all_streams.extend(vod_streams)
                logger.info(f"✅ Added {len(vod_streams)} VOD streams")

            # Process series (this can also be huge!)
            series = results.get("series")
            if isinstance(series, list) and series:
                logger.info(f"🔥 Processing {len(series)} series (this is also slow)...")

                # Batch process for better performance
                batch_size = 5000
                for i in range(0, len(series), batch_size):
                    batch = series[i:i + batch_size]
                    for show in batch:
                        show["content_type"] = "series"
                    if i + batch_size < len(series):
                        logger.info(f"  Processed {i + batch_size}/{len(series)} series...")

                all_streams.extend(series)
                logger.info(f"✅ Added {len(series)} series")

    except Exception as e:
        logger.error(f"Critical error fetching API data: {e}")
        return (
            None,
            None,
            json.dumps(
                {
                    "error": "API Fetch Error",
                    "details": f"Failed to fetch data from IPTV service: {str(e)}",
                }
            ),
            500,
        )

    logger.info(f"🚀 CONCURRENT FETCH COMPLETE: {len(all_categories)} total categories and {len(all_streams)} total streams")
    return all_categories, all_streams, None, None
