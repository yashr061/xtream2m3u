"""Streaming and proxy utilities"""
import logging
import time
import urllib.parse

import requests
from flask import Response

logger = logging.getLogger(__name__)


def is_live_stream(url):
    """Return True for Xtream *live* TS streams (``/live/.../<id>.ts``).

    Live streams are an endless broadcast that we want to keep alive across
    upstream reconnects (see ``generate_live_streaming_response``). VOD/series
    URLs (``/movie/``, ``/series/``) are finite files and must NOT be reconnected
    — re-requesting would restart them from byte 0 and corrupt the download.
    HLS (``.m3u8``) playlists are short text documents, not a byte stream, so
    they are excluded too.
    """
    path = urllib.parse.urlparse(url).path.lower()
    return "/live/" in path and path.endswith(".ts")


def stream_request(url, headers=None, timeout=30):
    """Make a streaming request that doesn't buffer the full response"""
    if not headers:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Connection": "keep-alive",
        }

    # Use longer timeout for streams and set both connect and read timeouts
    return requests.get(url, stream=True, headers=headers, timeout=(10, timeout))


def generate_streaming_response(response, content_type=None):
    """Generate a streaming response with appropriate headers"""
    if not content_type:
        content_type = response.headers.get("Content-Type", "application/octet-stream")

    def generate():
        try:
            bytes_sent = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    bytes_sent += len(chunk)
                    yield chunk
            logger.info(f"Stream completed, sent {bytes_sent} bytes")
        except requests.exceptions.ChunkedEncodingError as e:
            # Chunked encoding error from upstream - log and stop gracefully
            logger.warning(f"Upstream chunked encoding error after {bytes_sent} bytes: {str(e)}")
            # Don't raise - just stop yielding to close stream gracefully
        except requests.exceptions.ConnectionError as e:
            # Connection error (reset, timeout, etc.) - log and stop gracefully
            logger.warning(f"Connection error after {bytes_sent} bytes: {str(e)}")
            # Don't raise - just stop yielding to close stream gracefully
        except Exception as e:
            logger.error(f"Streaming error after {bytes_sent} bytes: {str(e)}")
            # Don't raise exceptions in generators after headers are sent!
            # Raising here causes Flask to inject "HTTP/1.1 500" into the chunked body,
        finally:
            # Always close the upstream response to free resources
            try:
                response.close()
            except:
                pass

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": content_type,
    }

    # Add content length if available and not using chunked transfer
    if "Content-Length" in response.headers and "Transfer-Encoding" not in response.headers:
        headers["Content-Length"] = response.headers["Content-Length"]
    else:
        headers["Transfer-Encoding"] = "chunked"

    return Response(generate(), mimetype=content_type, headers=headers, direct_passthrough=True)


def generate_live_streaming_response(first_response, url, content_type, max_failures=3):
    """Proxy an endless live stream, transparently reconnecting on upstream end.

    Xtream providers redirect ``/live/<id>.ts`` to a short-lived, *tokenized*
    edge URL (``...?token=...``) and rotate the token on every request. A player
    streaming directly just re-requests the original URL when its connection
    drops and gets a fresh token, so it plays forever. The proxy, however,
    followed the redirect only once and held that single tokenized connection —
    so when the token/edge session expired (≈10 min) the upstream closed and the
    player froze (issue #25). The old ``--timeout`` tweaks never helped because
    the cut was happening upstream, not in Gunicorn.

    This generator fixes it by re-requesting the *original* URL (→ fresh
    redirect → fresh token) whenever the upstream ends, stitching the segments
    into one uninterrupted response. MPEG-TS tolerates the discontinuity exactly
    like any live reconnect. We stop when the player disconnects (``GeneratorExit``)
    or after ``max_failures`` consecutive reconnects that yield no data (dead
    channel), so a genuinely broken stream can't loop forever.

    ``first_response`` is the already-opened, validated upstream response from the
    initial request, reused so the first connect's status code still surfaces to
    the caller.
    """
    def generate():
        response = first_response  # already opened & validated by the caller
        total_bytes = 0
        failures = 0
        try:
            while True:
                # (Re)connect to the ORIGINAL url when we have no live upstream.
                # Re-requesting the original yields a fresh redirect → fresh token.
                if response is None:
                    try:
                        response = stream_request(url, timeout=60)
                        response.raise_for_status()
                        logger.info(f"Reconnected to live stream {url}")
                    except Exception as e:
                        failures += 1
                        logger.warning(f"Live reconnect attempt failed for {url}: {e}")
                        if failures >= max_failures:
                            logger.error(
                                f"Live stream {url} reconnect failed {failures}x in a row; giving up"
                            )
                            break
                        time.sleep(min(failures, 3))  # brief backoff before retrying
                        continue

                # Pump the current upstream connection until it ends or drops.
                segment_bytes = 0
                segment_start = time.monotonic()
                try:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            segment_bytes += len(chunk)
                            total_bytes += len(chunk)
                            yield chunk
                    logger.info(
                        f"Upstream live segment ended cleanly after {segment_bytes} bytes "
                        f"(total {total_bytes}); reconnecting for a fresh token"
                    )
                except (requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.ConnectionError) as e:
                    logger.warning(
                        f"Upstream live connection dropped after {segment_bytes} bytes "
                        f"(total {total_bytes}): {e}; reconnecting"
                    )
                finally:
                    # Release the old upstream connection *before* opening a new
                    # one so we don't temporarily double our provider session count.
                    try:
                        response.close()
                    except Exception:
                        pass
                    response = None  # force a reconnect on the next iteration

                # A segment that produced data means the channel is healthy, so
                # reset the failure budget. Only consecutive empty reads count
                # toward giving up, so a genuinely dead channel can't loop forever.
                if segment_bytes > 0:
                    failures = 0
                else:
                    failures += 1
                    if failures >= max_failures:
                        logger.error(
                            f"Live stream {url} returned no data {failures}x in a row; giving up"
                        )
                        break
                    time.sleep(min(failures, 3))

                # Rate-limit floor: if an upstream dies almost immediately (e.g. a
                # provider "max connections reached" blob that carries bytes, so it
                # wouldn't trip the failure budget above), back off briefly so we
                # don't hammer the provider in a tight reconnect loop. Healthy
                # multi-minute segments never hit this.
                if time.monotonic() - segment_start < 1.0:
                    time.sleep(1.0)
        except GeneratorExit:
            # Player disconnected — stop reconnecting and let the generator close.
            logger.info(f"Client disconnected from live stream after {total_bytes} bytes: {url}")
            raise
        except Exception as e:
            logger.error(f"Live streaming error after {total_bytes} bytes: {e}")
        finally:
            try:
                if response is not None:
                    response.close()
            except Exception:
                pass

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": content_type,
        "Transfer-Encoding": "chunked",
    }
    return Response(generate(), mimetype=content_type, headers=headers, direct_passthrough=True)
