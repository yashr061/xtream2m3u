"""Proxy routes for images and streams"""
import logging
import urllib.parse

import requests
from flask import Blueprint, Response

from app.utils.streaming import (
    generate_live_streaming_response,
    generate_streaming_response,
    is_live_stream,
    stream_request,
)

logger = logging.getLogger(__name__)

proxy_bp = Blueprint('proxy', __name__)


@proxy_bp.route("/image-proxy/<path:image_url>")
def proxy_image(image_url):
    """Proxy endpoint for images to avoid CORS issues"""
    try:
        original_url = urllib.parse.unquote(image_url)
        logger.info(f"Image proxy request for: {original_url}")

        response = requests.get(original_url, stream=True, timeout=10)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        if not content_type.startswith("image/"):
            logger.error(f"Invalid content type for image: {content_type}")
            return Response("Invalid image type", status=415)

        return generate_streaming_response(response, content_type)
    except requests.Timeout:
        return Response("Image fetch timeout", status=504)
    except requests.HTTPError as e:
        return Response(f"Failed to fetch image: {str(e)}", status=e.response.status_code)
    except Exception as e:
        logger.error(f"Image proxy error: {str(e)}")
        return Response("Failed to process image", status=500)


@proxy_bp.route("/stream-proxy/<path:stream_url>")
def proxy_stream(stream_url):
    """Proxy endpoint for streams"""
    try:
        original_url = urllib.parse.unquote(stream_url)
        logger.info(f"Stream proxy request for: {original_url}")

        response = stream_request(original_url, timeout=60)  # Longer timeout for live streams
        response.raise_for_status()

        # Determine content type
        content_type = response.headers.get("Content-Type")
        if not content_type:
            if original_url.endswith(".ts"):
                content_type = "video/MP2T"
            elif original_url.endswith(".m3u8"):
                content_type = "application/vnd.apple.mpegurl"
            else:
                content_type = "application/octet-stream"

        logger.info(f"Using content type: {content_type}")

        # Live TS streams are an endless broadcast behind short-lived, rotating
        # provider tokens. Reconnect transparently so the player never freezes
        # when a token expires (issue #25). VOD/series are finite files and must
        # keep the single-connection path so they aren't restarted from byte 0.
        if is_live_stream(original_url):
            return generate_live_streaming_response(response, original_url, content_type)
        return generate_streaming_response(response, content_type)
    except requests.Timeout:
        logger.error(f"Timeout connecting to stream: {original_url}")
        return Response("Stream timeout", status=504)
    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching stream: {e.response.status_code} - {original_url}")
        return Response(f"Failed to fetch stream: {str(e)}", status=e.response.status_code)
    except Exception as e:
        logger.error(f"Stream proxy error: {str(e)} - {original_url}")
        return Response("Failed to process stream", status=500)
