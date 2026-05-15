<p align="center">
  <img src="docs/assets/logo.png" alt="xtream2m3u logo" width="200"
  style = "border-radius: 30%;"/>
</p>

<h1 align="center">xtream2m3u</h1>

<p align="center">
  <strong>Convert Xtream IPTV APIs into customizable M3U playlists with ease</strong>
</p>

<p align="center">
  <a href="#about">About</a> •
  <a href="#features">Features</a> •
  <a href="#prerequisites">Prerequisites</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#api-documentation">API</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  <a href="https://discord.gg/7qK8sfEq2q">
    <img src="https://img.shields.io/discord/1068543728274382868?color=7289da&label=Support&logo=discord&logoColor=7289da&style=for-the-badge" alt="Discord">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/github/languages/top/ovosimpatico/xtream2m3u?logo=python&logoColor=yellow&style=for-the-badge" alt="Language">
  </a>
  <a href="https://github.com/ovosimpatico/xtream2m3u/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/ovosimpatico/xtream2m3u?style=for-the-badge" alt="License">
  </a>
</p>

## About

**xtream2m3u** is a powerful and flexible tool designed to bridge the gap between Xtream API-based IPTV services and M3U playlist-compatible media players. It offers a **user-friendly web interface** and a **comprehensive API** to generate customized playlists.

Many IPTV providers use the Xtream API, which isn't directly compatible with all players. xtream2m3u allows you to:
1.  Connect to your Xtream IPTV provider.
2.  Select exactly which channel groups (Live TV) or VOD categories (Movies/Series) you want.
3.  Generate a standard M3U playlist compatible with almost any player (VLC, TiviMate, Televizo, etc.).

## Features

*   **Web Interface:** Easy-to-use UI for managing credentials and selecting categories.
*   **Custom Playlists:** Filter channels by including or excluding specific groups.
*   **VOD Support:** Optionally include Movies and Series in your playlist.
*   **Stream Proxying:** built-in proxy to handle CORS issues or hide upstream URLs.
*   **Catchup Support:** Optional emission of `catchup` tags for channels with `tv_archive` enabled, allowing timeshift/recording playback in compatible players (Kodi IPTV Simple Client, TiviMate, etc.).
*   **Custom DNS:** Uses reliable DNS resolvers (Cloudflare, Google) to ensure connection stability.
*   **XMLTV EPG:** Generates a compatible XMLTV guide for your playlist.
*   **Docker Ready:** Simple deployment with Docker and Docker Compose.

## Prerequisites

To use xtream2m3u, you'll need:
*   An active subscription to an IPTV service that uses the Xtream API.

For deployment:
*   **Docker & Docker Compose** (Recommended)
*   OR **Python 3.9+**

## Installation

### Using Docker (Recommended)

1.  Clone the repository:
    ```bash
    git clone https://github.com/ovosimpatico/xtream2m3u.git
    cd xtream2m3u
    ```
2.  Run the application:
    ```bash
    docker-compose up -d
    ```
3.  Open your browser and navigate to `http://localhost:5000`.

### Native Python Installation

1.  Clone the repository and enter the directory:
    ```bash
    git clone https://github.com/ovosimpatico/xtream2m3u.git
    cd xtream2m3u
    ```
2.  Create and activate a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the server:
    ```bash
    python run.py
    ```
5.  Open your browser and navigate to `http://localhost:5000`.

## Usage

### Web Interface
The easiest way to use xtream2m3u is via the web interface at `http://localhost:5000`.
1.  **Enter Credentials:** Input your IPTV provider's URL, username, and password.
2.  **Select Content:** Choose whether to include VOD (Movies & Series).
3.  **Filter Categories:** Load categories and select which ones to include or exclude.
4.  **Generate:** Click "Generate Playlist" to download your custom M3U file.

### Environment Variables
*   `PROXY_URL`: [Optional] Set a custom base URL for proxied content (useful if running behind a reverse proxy).
*   `PORT`: [Optional] Port to run the server on (default: 5000).
*   `XTREAM_URL`, `XTREAM_USERNAME`, `XTREAM_PASSWORD`: [CLI only] Credentials read by `cli.py` when the matching flags aren't passed.

### Command-Line Interface
The `cli.py` script generates playlists without needing the web server running. It accepts the same filter options as the `/m3u` endpoint, reads credentials from environment variables (or flags), and writes the playlist to stdout or a file.

```bash
# Configure credentials once
export XTREAM_URL=http://iptv.example.com:8080
export XTREAM_USERNAME=myuser
export XTREAM_PASSWORD=mypass

# Save a filtered playlist to a file
python cli.py --wanted-groups "Sports*,News" --enable-catchup -o playlist.m3u

# Pipe to stdout (composes with shell tools)
python cli.py --include-vod | grep "Movies"

# Combine with cron for periodic refresh
0 */6 * * * python /path/to/cli.py --wanted-groups "..." -o /var/iptv/list.m3u
```

The "API URL Builder" on the website also outputs a ready-to-paste CLI command alongside the URL, so you can configure your filter visually and copy the equivalent command.

Run `python cli.py --help` for the full flag list.

## API Documentation

For advanced users or automation, you can use the API endpoints directly.

### 1. Generate M3U Playlist
`GET /m3u` or `POST /m3u`

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `url` | string | Yes | IPTV Service URL |
| `username` | string | Yes | IPTV Username |
| `password` | string | Yes | IPTV Password |
| `unwanted_groups` | string | No | Comma-separated list of groups to **exclude** |
| `wanted_groups` | string | No | Comma-separated list of groups to **include** (takes precedence) |
| `include_vod` | boolean | No | Set `true` to include Movies & Series (default: `false`) |
| `nostreamproxy` | boolean | No | Set `true` to disable stream proxying (direct links) |
| `proxy_url` | string | No | Custom base URL for proxied streams |
| `include_channel_id` | boolean | No | Set `true` to include `epg_channel_id` tag |
| `channel_id_tag` | string | No | Custom tag name for channel ID (default: `channel-id`) |
| `enable_catchup` | boolean | No | Set `true` to emit catchup/timeshift tags for archive-enabled channels. **Note:** catchup channels bypass the stream proxy (URLs stay raw) so players can construct timeshift URLs. |

**Wildcard Support:** `unwanted_groups` and `wanted_groups` support `*` (wildcard) and `?` (single char).
*   Example: `*Sports*` matches "Sky Sports", "BeIN Sports", etc.

**Example:**
```
http://localhost:5000/m3u?url=http://iptv.com&username=user&password=pass&wanted_groups=Sports*,News&include_vod=true
```

### 2. Generate XMLTV Guide
`GET /xmltv`

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `url` | string | Yes | IPTV Service URL |
| `username` | string | Yes | IPTV Username |
| `password` | string | Yes | IPTV Password |
| `proxy_url` | string | No | Custom base URL for proxied images |

### 3. Get Categories
`GET /categories`

Returns a JSON list of all available categories.

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `url` | string | Yes | IPTV Service URL |
| `username` | string | Yes | IPTV Username |
| `password` | string | Yes | IPTV Password |
| `include_vod` | boolean | No | Set `true` to include VOD categories |

### 4. Proxy Endpoints
*   `GET /image-proxy/<encoded_url>`: Proxies images (logos, covers).
*   `GET /stream-proxy/<encoded_url>`: Proxies video streams.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.
See the [LICENSE](LICENSE) file for details.

## Disclaimer

xtream2m3u is a tool for managing your own legal IPTV subscriptions. It **does not** provide any content, channels, or streams. The developers are not responsible for how this tool is used.
