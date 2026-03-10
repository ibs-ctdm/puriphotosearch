"""Download InsightFace buffalo_sc model for bundling."""

import os
import sys
import time
import zipfile
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

MODEL_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip"
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds


def download_model(model_name="buffalo_sc", target_dir=None):
    """Download the InsightFace model to a local directory.

    Args:
        model_name: InsightFace model name (default: buffalo_sc)
        target_dir: Directory to store models. If None, uses ./models/
    """
    if target_dir is None:
        target_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

    os.makedirs(target_dir, exist_ok=True)
    model_dir = os.path.join(target_dir, "models", model_name)

    if os.path.isdir(model_dir) and os.listdir(model_dir):
        print(f"Model '{model_name}' already exists at {model_dir}")
        return model_dir

    zip_path = os.path.join(target_dir, f"{model_name}.zip")

    # Download with retries
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Downloading '{model_name}' (attempt {attempt}/{MAX_RETRIES})...")
            req = Request(MODEL_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=120) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    while True:
                        chunk = response.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded * 100 // total
                            print(f"\r  Progress: {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB ({pct}%)", end="", flush=True)
            print()  # newline after progress
            print(f"Download complete: {zip_path}")
            break
        except (URLError, HTTPError, OSError) as e:
            print(f"\n  Attempt {attempt} failed: {e}")
            if os.path.exists(zip_path):
                os.remove(zip_path)
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY * attempt
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Failed to download model after {MAX_RETRIES} attempts: {e}"
                )

    # Extract zip
    os.makedirs(model_dir, exist_ok=True)
    print(f"Extracting to {model_dir}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(os.path.join(target_dir, "models"))

    # Clean up zip
    os.remove(zip_path)

    print(f"Model ready at {model_dir}")
    return model_dir


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    download_model(target_dir=target)
