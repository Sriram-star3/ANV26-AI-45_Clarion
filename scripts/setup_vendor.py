"""Setup script for downloading and extracting vendor frontend dependencies.

Downloads npm tarballs from registry.npmjs.org and extracts React 18, React DOM,
Babel standalone, and Tailwind CSS into static/vendor/.
Uses Python standard library only.
"""

from __future__ import annotations

import io
from pathlib import Path
import tarfile
import urllib.request

VENDOR_TARGETS = {
    "react.js": {
        "url": "https://registry.npmjs.org/react/-/react-18.3.1.tgz",
        "internal_path": "package/umd/react.production.min.js",
    },
    "react-dom.js": {
        "url": "https://registry.npmjs.org/react-dom/-/react-dom-18.3.1.tgz",
        "internal_path": "package/umd/react-dom.production.min.js",
    },
    "babel.js": {
        "url": "https://registry.npmjs.org/@babel/standalone/-/standalone-7.26.4.tgz",
        "internal_path": "package/babel.min.js",
    },
    "tailwind.js": {
        "url": "https://registry.npmjs.org/@tailwindcss/browser/-/browser-4.3.3.tgz",
        "internal_path": "package/dist/index.global.js",
    },
}


def download_and_extract_vendor(dest_dir: str | Path = "static/vendor") -> None:
    """Download vendor packages from npm registry and extract minified distributions."""
    vendor_path = Path(dest_dir)
    vendor_path.mkdir(parents=True, exist_ok=True)

    # Check if all files already exist
    all_present = all((vendor_path / fname).exists() and (vendor_path / fname).stat().st_size > 0 for fname in VENDOR_TARGETS)
    if all_present:
        print(f"All vendor files already present in {vendor_path.as_posix()}, skipping download.")
        return

    headers = {"User-Agent": "Clarion-Vendor-Setup/1.0"}

    for filename, meta in VENDOR_TARGETS.items():
        target_file = vendor_path / filename
        if target_file.exists() and target_file.stat().st_size > 0:
            print(f"Vendor file '{filename}' already exists, skipping.")
            continue

        print(f"Downloading {filename} from {meta['url']} ...")
        req = urllib.request.Request(meta["url"], headers=headers)
        with urllib.request.urlopen(req) as resp:
            tar_bytes = resp.read()

        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
            member = tar.getmember(meta["internal_path"])
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"Could not extract {meta['internal_path']} from tarball")
            content = extracted.read()

        target_file.write_bytes(content)
        print(f"Successfully saved {filename} ({len(content):,} bytes) to {target_file.as_posix()}")

    print("Vendor setup completed successfully.")


if __name__ == "__main__":
    download_and_extract_vendor()
