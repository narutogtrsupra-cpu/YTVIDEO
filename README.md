<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:2bebb4510f40bcf4a21308e01cb3d037ec2363d4daf348db3861843e4949392a -->

# Telegram YouTube player for your phone

Play a YouTube video with sound in one Telegram supergroup video chat. Host the Python worker on a **64-bit Android phone using Termux + Ubuntu**, or on a Linux computer. Control it from Telegram commands and buttons. There is no web server or database.

## Controls

| Command | Action |
| --- | --- |
| `/play <YouTube link or search words>` | Play immediately, or add one video to the queue |
| `/pause`, `/resume` | Pause or resume the current track |
| `/skip` | Play the next queued track; leave when the queue is empty |
| `/stop` | Cancel a pending lookup, clear the queue, and leave the call |
| `/queue`, `/remove 2`, `/clear` | View or edit the waiting queue |
| `/volume 50` | Set volume from 1–100% |
| `/mode audio`, `/mode video` | Set the mode for the next track |
| `/quality 240`, `/quality 360` | Set maximum source height for the next track |
| `/status`, `/now` | Show the current track, settings, and control buttons |
| `/help` | Show command help |

Buttons provide pause, resume, skip, stop, queue, and status. Every click checks permissions again. Owners can control from their private chat with the bot or the configured group. Group admins can control inside that group when `ALLOW_GROUP_ADMINS=true`. Commands addressed to another bot are ignored.

## How it works

A **bot account** handles controls, and a **separate Telegram user account (the assistant)** joins the call and streams media through PyTgCalls/NTgCalls and FFmpeg. A bot token alone cannot perform this streaming role.

The queue stores video metadata. Direct media URLs are resolved when a track starts, because those URLs expire. No complete media files are downloaded to disk, though network/media buffers are still used. Video uses separate audio and video FFmpeg pipelines when needed.

## Resource limits

Defaults are 360p, 15 fps, mono audio, one FFmpeg decoding thread per pipeline, one filter thread, one call, and 20 waiting tracks. `VIDEO_FPS` can be lowered to 5–10. The automatic quality selector never falls back to a video source above the chosen height; unavailable formats produce an error. Audio mode requests an audio source first and disables the video pipeline.

- Use `/mode audio` for the lowest CPU, battery, and network load.
- For video, try `/quality 240` and `VIDEO_FPS=10` if the phone gets hot.
- Playback is transcoded to Telegram's call format. This is not zero-copy playback; video encoding and WebRTC still use CPU and multiple native threads.
- The queue leaves the call when exhausted. A paused call or failed playback setup disconnects after `IDLE_SECONDS` (60 by default).
- Extraction has a timeout, a 4 MiB metadata output limit, bounded retries, and one operation at a time. `/stop` can interrupt a pending lookup.
- Live/upcoming streams, playlists, arbitrary remote sources, and videos longer than `MAX_DURATION_SECONDS` are disabled. FFmpeg output is also limited to each validated track duration so EOF reconnection cannot extend a track indefinitely.
- Queue, volume, mode, and quality are held in memory and reset on restart.

There is no measured CPU/RAM/battery target yet. Performance depends on the phone, video codec, connection, and Android's background process restrictions. Running Ubuntu under proot adds overhead.

## Requirements

- Android with an **ARM64 CPU and 64-bit Android userspace**, a current Termux installation, storage for Ubuntu and dependencies, and a stable network connection. This Python deployment does not support 32-bit phones. iOS is not a supported local host for this worker.
- Linux with glibc 2.28+; CPython 3.11–3.14. ARM64 and x86_64 wheels are published for the pinned NTgCalls version.
- FFmpeg and ffprobe; Node.js **22+** for yt-dlp's YouTube JavaScript challenges. `yt-dlp[default]` includes its EJS package.
- A Telegram API ID/hash, a bot token, the assistant account, and a supergroup with an active video chat.

The Android/proot path is based on the published Linux ARM64 wheels and has **not been exercised on a physical phone**. Direct installation into Termux Python uses Android's Bionic libc and cannot use these manylinux wheels. A native Android app would be a separate implementation.

## 1. Prepare Android

Install Termux using its [official installation guidance](https://github.com/termux/termux-app#installation). In Termux, outside Ubuntu:

```sh
pkg update
pkg install proot-distro git
proot-distro install ubuntu
termux-wake-lock
proot-distro login ubuntu --shared-tmp
```

Keep Termux open and allow background operation in Android's battery settings. A wake lock does not guarantee that Android will keep the process alive.

Inside Ubuntu (also suitable for a regular Ubuntu host with the appropriate sudo privileges):

```sh
apt update
apt install -y python3 python3-venv python3-pip ffmpeg nodejs git ca-certificates libstdc++6
python3 --version
node --version
uname -m
```

Use Python 3.11–3.14 and Node 22 or newer. If your Ubuntu image provides older versions, upgrade the image or install a supported runtime before proceeding. On Android, `uname -m` should be `aarch64`; also confirm `getconf LONG_BIT` reports 64.

## 2. Install the project

Clone the branch containing this implementation after it has been published, or copy this working tree onto the phone. An empty `main` branch will not contain the player.

```sh
cd YTVIDEO
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
# Require a wheel for the large native library; avoid accidentally building it on a phone.
.venv/bin/python -m pip install --only-binary=ntgcalls -r requirements.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m vcplayer.doctor
cp .env.example .env
chmod 600 .env
```

`requirements.txt` pins the tested dependency set. `pyproject.toml` declares compatible ranges. The doctor checks native imports, FFmpeg/ffprobe, Node, and the YouTube EJS dependency without accessing Telegram or reading secrets.

## 3. Configure Telegram

1. Create a control bot with **@BotFather** and copy its token into `.env` locally.
2. Obtain `API_ID` and `API_HASH` at [my.telegram.org/apps](https://my.telegram.org/apps). These are used by both clients.
3. Choose a separate Telegram user account as the assistant. Join your supergroup with that account and add the bot.
4. Set `CHAT_ID` to your numeric supergroup ID (`-100...`) and `OWNER_IDS` to your numeric user ID (comma-separated for multiple owners). You can obtain IDs using an existing trusted Telegram ID tool or a Telegram API client. Owners are required even when group admin controls are enabled.
5. Give the assistant permission to join, speak, and share video in the call. The bot needs permission to send messages. Telegram admin lookup may require making the bot a group admin.
6. If you want unaddressed group commands to reach the bot, make it an admin or adjust BotFather's group privacy setting. With privacy enabled, address commands as `/play@YourBotUsername ...`.
7. Start the group video chat manually. This worker joins an existing call; it does not create a call automatically.

Edit `.env` using a local text editor. Never send `.env`, API hashes, tokens, login codes, cookies, or session files in chat or commit them. `.env`, `.state/`, and `*.session*` are ignored by Git. The application creates session files with a private umask and a private state directory.

Optional: `YOUTUBE_COOKIES_FILE` points to a private Netscape-format cookies file for videos that need sign-in. yt-dlp can update this file, so make it writable and keep it outside the repository. Public videos are preferable. YouTube restrictions may still prevent extraction.

## 4. Sign in and run

From the project directory, log the assistant in once. Enter its phone number, login code, and two-step password locally if requested:

```sh
.venv/bin/vc-login
./scripts/run.sh
```

`vc-login` caches the assistant's group dialogs so numeric group IDs can be resolved. If you add the assistant to a group later or change `CHAT_ID`, rerun `vc-login` to refresh that cache. The control bot authenticates with `BOT_TOKEN` during startup.

Send `/help` or `/play <YouTube link>` to the bot. Keep this process running. Ctrl+C or SIGTERM leaves the call and disconnects the clients. To start again, enter Ubuntu, return to this directory, and run `./scripts/run.sh`. Do not run two instances against the same session directory.

The launcher caps common numerical-library thread settings. FFmpeg thread limits are applied separately by the transport. You can also run `.venv/bin/vc-player` directly. There is no HTTP listener, browser preview, inbound port, webhook endpoint, or required cloud server.

## Configuration reference

See [.env.example](.env.example) for every setting. Limits are validated before connecting:

| Setting | Default / permitted values |
| --- | --- |
| `DEFAULT_MODE` | `video`; `audio` or `video` |
| `VIDEO_HEIGHT` | `360`; 240 or 360 |
| `VIDEO_FPS` | 15; 5–20 |
| `FFMPEG_THREADS` | 1; 1–2 decoding threads per pipeline |
| `DEFAULT_VOLUME` | 70; 1–100 |
| `MAX_QUEUE` | 20; 1–50 waiting items |
| `MAX_DURATION_SECONDS` | 7200; 30–14400 |
| `IDLE_SECONDS` | 60; 10–600 |
| `EXTRACT_TIMEOUT_SECONDS` | 45; 10–120 per extraction |
| `ALLOW_GROUP_ADMINS` | `true`; `true` or `false` |
| `STATE_DIR` | `.state`; local private directory |
| `YOUTUBE_COOKIES_FILE` | unset; optional private file |

## Troubleshooting

- **No matching NTgCalls distribution:** check the Python version, ARM64/64-bit userspace, glibc, and that you are inside Ubuntu rather than Termux's native Python. Avoid compiling NTgCalls on the phone as the first remedy.
- **Cannot resolve group:** join with the assistant and rerun `vc-login`. Use a supergroup numeric ID, not a bot ID or invite link.
- **Cannot join / nothing plays:** start the group video chat, check assistant permissions and network access, then `/stop` and `/play`. If the assistant is removed or the group call is closed, restart the call and retry; automatic rejoin after those events is not implemented.
- **YouTube extraction fails:** check the doctor, try a public unrestricted video, and check yt-dlp's current YouTube requirements. Updating `yt-dlp[default]` may help (`.venv/bin/python -m pip install -U 'yt-dlp[default]'`), but that changes the tested dependency set. Cookies do not guarantee success.
- **Bot ignores commands:** verify your numeric owner ID, group ID, and BotFather privacy settings; try a private message as a configured owner.
- **Phone sleeps / process is killed:** keep Termux in the foreground and revisit Android battery settings. Proot cannot override Android's process limits.

## Development and verification

```sh
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/ruff check vcplayer tests
.venv/bin/ruff format --check vcplayer tests
.venv/bin/python -m vcplayer.doctor
```

Tests use synthetic metadata and fake Telegram clients, and exercise actual PyTgCalls stream parameter construction. They cover queue progression, limits, cancellations, idle cleanup, permission checks, URL validation, extraction timeouts/output limits, and configuration validation. They do not prove a real Telegram call or Android performance. A real smoke test needs your configured accounts, active group call, and phone.

### Upstream references

- [PyTgCalls](https://github.com/pytgcalls/pytgcalls) and [Telegram client example](https://github.com/pytgcalls/pytgcalls/blob/master/example/telethon_example/example_telethon.py)
- [NTgCalls Python wheel inventory](https://pypi.org/project/ntgcalls/3.0.6/#files) and [supported platforms](https://github.com/pytgcalls/ntgcalls)
- [yt-dlp dependencies](https://github.com/yt-dlp/yt-dlp#dependencies) and [JavaScript challenge requirements](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- [Termux proot-distro](https://github.com/termux/proot-distro)


<!-- /coderabbit-ai-generated:v1 -->