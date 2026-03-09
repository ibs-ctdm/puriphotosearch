"""Download InsightFace buffalo_sc model for bundling."""

import os
import sys


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

    print(f"Downloading model '{model_name}' to {target_dir}...")

    # Set INSIGHTFACE_HOME so the model downloads to our target dir
    os.environ["INSIGHTFACE_HOME"] = target_dir

    from insightface.app import FaceAnalysis

    app = FaceAnalysis(
        name=model_name,
        root=target_dir,
        providers=["CPUExecutionProvider"],
        allowed_modules=["detection", "recognition"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))

    print(f"Model downloaded successfully to {model_dir}")
    return model_dir


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    download_model(target_dir=target)
