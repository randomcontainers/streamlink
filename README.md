# streamlink

Container images with [Streamlink](https://streamlink.github.io/), the command-line tool that extracts streams from websites and saves them to a file or passes them to a video player. `latest` also includes FFmpeg, which Streamlink uses to combine video and audio that a site sends separately. The images are rebuilt when Streamlink publishes a release and when the base image changes, for `linux/amd64` and `linux/arm64`.

This is an unofficial build, not affiliated with or endorsed by the Streamlink project. Report problems with the image in this repository and problems with Streamlink itself [upstream](https://github.com/streamlink/streamlink/issues).

## Quick start

Record a live stream into the current directory:

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  ghcr.io/randomcontainers/streamlink -o recording.ts "https://www.twitch.tv/<channel>" best
```

The same images can also be pulled as `randomcontainers.com/streamlink`.

List the qualities a stream is available in:

```sh
docker run --rm ghcr.io/randomcontainers/streamlink "https://www.twitch.tv/<channel>"
```

Streamlink cannot start a player inside the container. Send the stream to a player on the host with `--stdout` instead; log messages then go to stderr:

```sh
docker run --rm ghcr.io/randomcontainers/streamlink --stdout "https://www.twitch.tv/<channel>" best | mpv -
```

Options can also come from a config file in the working directory:

```sh
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" \
  ghcr.io/randomcontainers/streamlink --config streamlink.conf -o recording.ts "https://www.twitch.tv/<channel>" best
```

## What is in the image

| | slim | default |
|---|---|---|
| Streamlink and its Python dependencies, installed from `requirements.lock` | yes | yes |
| FFmpeg, to combine video and audio that a site sends as separate streams | no | yes |

FFmpeg is the [randomcontainers/ffmpeg](https://github.com/randomcontainers/ffmpeg) build.

The image has no web browser, so Streamlink's webbrowser API is not available. The Kick plugin needs it, and the Twitch plugin uses it only when it has to get a new client-integrity token.

## Default or slim

The default image (`latest`) has Streamlink and FFmpeg and is recommended for general use. Many sites send video and audio as separate streams (DASH, or HLS with separate audio tracks), and Streamlink needs FFmpeg to combine them; without it those streams have no sound or fewer qualities. Use `slim`, which has Streamlink and Python only, as the base when you build your own image and want that base kept up to date.

The default image is also published as `ghcr.io/randomcontainers/streamlink-ffmpeg`, built in the [streamlink-ffmpeg](https://github.com/randomcontainers/streamlink-ffmpeg) repository with the same contents and a different digest.

## Tags

`<version>` is a Streamlink release such as `8.6.1`. `<minor>` and `<major>` are its shorter forms, `8.6` and `8`, and follow the newest release in that series.

| Default (with FFmpeg) | Slim | Base |
|---|---|---|
| `latest`, `<version>`, `<minor>`, `<major>` | `slim`, `<version>-slim`, `<minor>-slim`, `<major>-slim` | Ubuntu |
| `ubuntu`, `<version>-ubuntu`, `<minor>-ubuntu`, `<major>-ubuntu` | `slim-ubuntu`, `<version>-slim-ubuntu`, `<minor>-slim-ubuntu`, `<major>-slim-ubuntu` | Ubuntu |
| `<version>-ubuntu26.04` | `<version>-slim-ubuntu26.04` | Ubuntu 26.04 |
| `alpine`, `<version>-alpine`, `<minor>-alpine`, `<major>-alpine` | `slim-alpine`, `<version>-slim-alpine`, `<minor>-slim-alpine`, `<major>-slim-alpine` | Alpine |
| `<version>-alpine3.24` | `<version>-slim-alpine3.24` | Alpine 3.24 |

The images are currently built on Ubuntu 26.04 and Alpine 3.24. Tags without a distro version move to the next distro release when the project does; tags ending in `ubuntu26.04` or `alpine3.24` stay on that release and are no longer rebuilt once the project moves to the next one. Every tag of the current Streamlink version, including the exact version, is rebuilt in place (see [Updates](#updates)), so pin a digest when you need the same bytes every time.

## Platforms

`linux/amd64` and `linux/arm64`, for both Ubuntu and Alpine. Both are built natively on GitHub-hosted runners, without emulation. Streamlink's Python dependencies are installed from prebuilt wheels: manylinux wheels on Ubuntu and musllinux wheels on Alpine.

## Files and permissions

The working directory is `/work`. The image runs as UID 1000, and any other UID works too: `HOME` is then `/`, and caches go to `/cache`, which anyone can write to. How to get output files owned by you depends on how you run containers:

| Runtime | Flag |
|---|---|
| Docker on Linux (rootful), GitHub Actions | `--user "$(id -u):$(id -g)"` |
| Rootless Podman | `--userns=keep-id` |
| Rootless Docker | `--user 0:0` (root in the container is your user on the host) |
| Docker Desktop on macOS or Windows | none, file ownership is mapped for you |

Some plugins store login and session tokens in `/cache/streamlink`, for example TF1 and Zattoo. Add `-v streamlink-cache:/cache` to keep them between runs.

## Extending the slim image

Use a `slim` tag as the base for your own image. `slim`, `slim-ubuntu` and `slim-alpine` follow new Streamlink releases and are rebuilt when its locked Python dependencies or the distro change. Streamlink runs from a virtual environment in `/usr/local/lib/streamlink`; the `python3` on `PATH` is the distro's interpreter and cannot import Streamlink. The distro packages Streamlink needs are listed in `/usr/local/share/randomcontainers/streamlink/runtime-deps`. Switch to root to install more, then back:

```dockerfile
FROM ghcr.io/randomcontainers/streamlink:slim-ubuntu@sha256:...
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends jq \
 && rm -rf /var/lib/apt/lists/*
USER 1000:1000
```

On Alpine, use `apk add --no-cache jq`. The entrypoint is `["tini", "--", "streamlink"]`; set your own `ENTRYPOINT` if your image runs a script. To pick up new Streamlink releases and base image fixes, let Dependabot or Renovate update the digest in your `FROM` line.

## Verifying

Each image has a build provenance attestation from this repository's GitHub Actions run, signed by the shared build workflow in `randomcontainers/ci`:

```sh
gh attestation verify oci://ghcr.io/randomcontainers/streamlink:latest \
  --repo randomcontainers/streamlink --signer-repo randomcontainers/ci
```

Images from `ghcr.io/randomcontainers/streamlink-ffmpeg` are built in that repository, so verify them with `--repo randomcontainers/streamlink-ffmpeg` and the same `--signer-repo`.

Each platform image also carries an SPDX SBOM that lists the distro and Python packages in it with their versions:

```sh
docker buildx imagetools inspect ghcr.io/randomcontainers/streamlink:latest --format '{{ json .SBOM }}'
```

Streamlink and all of its Python dependencies are installed from [`requirements.lock`](requirements.lock), which pins every package to a version and its SHA-256 hashes, and pip refuses anything else. The URL and hash of each installed wheel are in `/usr/local/share/randomcontainers/streamlink/source`.

## Updates

The project checks [streamlink on PyPI](https://pypi.org/project/streamlink/) every 15 minutes. A release is picked up once it is 24 hours old and PyPI holds a provenance attestation showing it was published from the [streamlink/streamlink](https://github.com/streamlink/streamlink) repository. The new version and a regenerated `requirements.lock` are then committed together and the images are rebuilt. Only the newest release is built; tags of older versions stay as they were last built. Dependency versions in the lock must have been on PyPI for at least 7 days. The lock is also regenerated weekly at the same Streamlink version, so fixes in dependencies such as urllib3 and certifi reach the current tags between releases.

The images of the current version are also rebuilt when the Ubuntu or Alpine base image changes, the default ones when a new FFmpeg image is published, and all of them at least every 7 days, so distro security fixes reach the current tags.

## Building

```sh
docker build -f Dockerfile.ubuntu --target slim --build-arg VERSION=<version> -t streamlink:local .
```

Use `Dockerfile.alpine` for the Alpine image. `<version>` must be the version pinned in `requirements.lock`; the build stops otherwise. The default image is generated from the `combos` section of `package.yml` by [randomcontainers/ci](https://github.com/randomcontainers/ci) and layers this image onto the FFmpeg image. The command that produced `requirements.lock` is at the top of the file; it resolves for Python 3.14, the version on both bases. If a new lock changes the lxml version, run `python3 scripts/bundled-licenses.py` (Python 3.11 or later) to refresh `licenses/`. The build fails until those files match the installed lxml.

## Licenses

Streamlink is released under the [BSD 2-Clause license](https://github.com/streamlink/streamlink/blob/master/LICENSE). The slim image adds its Python dependencies, which are mostly under MIT, Apache-2.0 and BSD licenses, plus certifi (MPL-2.0) and pycountry (LGPL-2.1-only). The complete SPDX expression is in the image's `org.opencontainers.image.licenses` label, and each package's license files are in `/usr/local/share/randomcontainers/streamlink/licenses/`.

lxml's extension modules link static builds of libxml2 and libxslt (MIT), zlib (Zlib) and GNU libiconv (LGPL-2.1-or-later). The lxml wheel includes the license texts of libxml2 and libxslt but not those of zlib and libiconv, so this repository adds the license files of all four libraries in [`licenses/`](licenses/), and the image has them in `/usr/local/share/randomcontainers/streamlink/licenses/lxml/bundled/`. The `SOURCES` file there names the lxml source release and the source archive of each library with its SHA-256. For libiconv, that archive is the corresponding source, and the lxml source release has the code and build script to relink lxml with a modified libiconv.

`latest` also contains FFmpeg, licensed under GPL-3.0-or-later. Its license files and corresponding source are described in the [ffmpeg repository](https://github.com/randomcontainers/ffmpeg#licenses).

The files in this repository are available under the MIT license, see [LICENSE](LICENSE).

## Requesting a tool

To suggest another tool, use the [Request a tool](https://github.com/randomcontainers/.github/issues/new?template=tool-request.yml) form.
