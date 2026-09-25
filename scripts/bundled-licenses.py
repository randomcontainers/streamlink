"""Collect the license files of the libraries linked into lxml.

Usage: bundled-licenses.py

lxml's Linux wheels link static builds of zlib, GNU libiconv, libxml2 and
libxslt into its extension modules, but include the license texts of libxml2
and libxslt only. This reads the lxml version from requirements.lock, finds
the library versions its Linux wheels are built with in lxml's source
release, downloads the source archive of each library, checks it against the
hash in lxml's build script, and writes the license files from the archives
and their URLs to licenses/lxml-<version>/bundled/. Run it whenever the lxml
pin in requirements.lock changes.
"""

import fnmatch
import hashlib
import io
import json
import pathlib
import re
import shlex
import shutil
import sys
import tarfile
import textwrap
import tomllib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

# name: (environment variable, source archive, license files)
LIBRARIES = {
    "zlib": (
        "ZLIB_VERSION",
        "https://github.com/madler/zlib/releases/download/v{version}/zlib-{version}.tar.gz",
        ["LICENSE"],
    ),
    "libiconv": (
        "LIBICONV_VERSION",
        "https://ftp.gnu.org/pub/gnu/libiconv/libiconv-{version}.tar.gz",
        ["COPYING.LIB", "AUTHORS"],
    ),
    "libxml2": (
        "LIBXML2_VERSION",
        "https://download.gnome.org/sources/libxml2/{series}/libxml2-{version}.tar.xz",
        ["Copyright"],
    ),
    "libxslt": (
        "LIBXSLT_VERSION",
        "https://download.gnome.org/sources/libxslt/{series}/libxslt-{version}.tar.xz",
        ["Copyright"],
    ),
}
# lib_names in lxml's buildlibxml.py for the archives above; libexslt is part of libxslt.
BUILT = {"libz", "iconv", "libxml2", "libxslt", "libexslt"}

# The wheels installed on Ubuntu and Alpine.
PLATFORMS = ("manylinux_x86_64", "manylinux_aarch64", "musllinux_x86_64", "musllinux_aarch64")


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def read(tar, path):
    try:
        return tar.extractfile(path).read()
    except KeyError:
        sys.exit(f"{path} is not in its archive")


def environment(value):
    if isinstance(value, str):
        return dict(item.partition("=")[::2] for item in shlex.split(value))
    return {key: str(item) for key, item in value.items()}


def build_environment(cibw, identifier):
    """The environment cibuildwheel sets for one build identifier."""
    env = environment(cibw.get("linux", {}).get("environment", cibw.get("environment", {})))
    for override in cibw.get("overrides", []):
        select = override.get("select", [])
        patterns = select.split() if isinstance(select, str) else select
        if "environment" not in override:
            continue
        if not any(fnmatch.fnmatch(identifier, pattern) for pattern in patterns):
            continue
        new = environment(override["environment"])
        mode = override.get("inherit", {}).get("environment", "none")
        if mode == "append":
            env = {**env, **new}
        elif mode == "prepend":
            env = {**new, **env}
        else:
            env = new
    return env


def main():
    lock = (ROOT / "requirements.lock").read_text()
    match = re.search(r"^lxml==([^\s;]+)", lock, re.M)
    if not match:
        sys.exit("requirements.lock does not pin lxml")
    lxml = match.group(1)
    match = re.search(r"--python-version 3\.(\d+)", lock)
    if not match:
        sys.exit("requirements.lock does not name the Python version it resolves for")
    python = f"cp3{match.group(1)}"

    release = json.loads(fetch(f"https://pypi.org/pypi/lxml/{lxml}/json"))
    sdists = [f for f in release["urls"] if f["packagetype"] == "sdist"]
    if len(sdists) != 1:
        sys.exit(f"lxml {lxml} has {len(sdists)} source releases on PyPI")
    sdist = sdists[0]
    data = fetch(sdist["url"])
    if hashlib.sha256(data).hexdigest() != sdist["digests"]["sha256"]:
        sys.exit(f"{sdist['url']} does not match its SHA-256 on PyPI")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        top = f"lxml-{lxml}"
        pyproject = tomllib.loads(read(tar, f"{top}/pyproject.toml").decode())
        script = read(tar, f"{top}/buildlibxml.py").decode()

    cibw = pyproject["tool"]["cibuildwheel"]
    envs = {platform: build_environment(cibw, f"{python}-{platform}") for platform in PLATFORMS}
    keys = ["STATIC_DEPS"] + [variable for variable, _, _ in LIBRARIES.values()]
    wanted = {platform: {key: env.get(key) for key in keys} for platform, env in envs.items()}
    values = wanted[PLATFORMS[0]]
    if any(other != values for other in wanted.values()):
        sys.exit(f"lxml {lxml} builds its Linux wheels with different libraries: {wanted}")
    if values["STATIC_DEPS"] != "true" or None in values.values():
        sys.exit(f"lxml {lxml} pyproject.toml does not set static library versions: {values}")

    # A library added upstream needs its license files here too.
    match = re.search(r"^\s*lib_names = (.*)$", script, re.M)
    built = set(re.findall(r"'(\w+)'", match.group(1))) if match else set()
    if built != BUILT:
        sys.exit(f"lxml {lxml} buildlibxml.py links {sorted(built)}, not {sorted(BUILT)}")
    found = re.findall(r"^\s*([0-9a-f]{64})\s+(\S+)$", script, re.M)
    hashes = {name: digest for digest, name in found}
    match = re.search(r"^LIBRARY_PATCHES = \{(.*?)^\}", script, re.M | re.S)
    patches = dict(re.findall(r"\"([^\"]+)\": \"([^\"]+)\"", match.group(1))) if match else {}

    intro = (
        f"lxml {lxml} links static builds of the libraries below into its extension "
        "modules. Its Linux wheels are built from the lxml source release with "
        "buildlibxml.py, which downloads these archives. The license files of each "
        "library are in the directory of the same name; libxslt includes libexslt. "
        "GNU libiconv is licensed under LGPL-2.1-or-later. The libiconv archive is its "
        "corresponding source, and the lxml source release has the code and build "
        "script to relink lxml with a modified copy."
    )
    sources = [textwrap.fill(intro, 76), "", f"lxml {lxml}", f"  {sdist['url']}"]
    sources.append(f"  sha256:{sdist['digests']['sha256']}")
    texts = {}
    for name, (variable, template, files) in LIBRARIES.items():
        version = values[variable]
        url = template.format(version=version, series=".".join(version.split(".")[:2]))
        filename = url.rpartition("/")[2]
        data = fetch(url)
        digest = hashlib.sha256(data).hexdigest()
        expected = hashes.get(filename)
        if expected is None:
            print(f"lxml {lxml} buildlibxml.py has no hash for {filename}", file=sys.stderr)
        elif digest != expected:
            sys.exit(f"{url} does not match the hash in lxml {lxml} buildlibxml.py")
        top = f"{name}-{version}"
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            texts[name] = {file: read(tar, f"{top}/{file}") for file in files}
        sources += [f"{name} {version}", f"  {url}", f"  sha256:{digest}"]
        if top in patches:
            sources.append(f"  patched with {patches[top]} from the lxml source release")

    base = ROOT / "licenses"
    for old in base.glob("lxml-*"):
        shutil.rmtree(old)
    out = base / f"lxml-{lxml}" / "bundled"
    for name, files in texts.items():
        (out / name).mkdir(parents=True)
        for file, text in files.items():
            (out / name / file).write_bytes(text)
    (out / "SOURCES").write_text("\n".join(sources) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
