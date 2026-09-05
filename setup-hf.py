from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import HfApi, upload_folder
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError

ROOT = Path(__file__).resolve().parent
SPACES = [
    ("cineqo-core", ROOT / "deploy" / "huggingface" / "core-space"),
    ("cineqo-video", ROOT / "deploy" / "huggingface" / "video-space"),
]
ZERO_GPU = "zero-a10g"


def _runtime(api: HfApi, repo_id: str):
    try:
        return api.get_space_runtime(repo_id=repo_id)
    except Exception:
        return None


def _is_zero(runtime) -> bool:
    if runtime is None:
        return False
    current = str(getattr(runtime, "hardware", "") or "")
    requested = str(getattr(runtime, "requested_hardware", "") or "")
    return current == ZERO_GPU or requested == ZERO_GPU


def main() -> int:
    api = HfApi()
    me = api.whoami()["name"]
    print(f"Logged in to Hugging Face as: {me}")
    print("Cineqo will create the two Gradio Spaces directly on ZeroGPU.")

    for name, folder in SPACES:
        if not folder.exists():
            print(f"ERROR: missing folder: {folder}")
            return 2

        repo_id = f"{me}/{name}"
        runtime = _runtime(api, repo_id)

        if runtime is not None and not _is_zero(runtime):
            current = getattr(runtime, "hardware", None)
            requested = getattr(runtime, "requested_hardware", None)
            print(f"\nExisting Space {repo_id} is not ZeroGPU (current={current}, requested={requested}).")
            print("Hugging Face now blocks new free Gradio Spaces on cpu-basic, so this Space must be recreated directly as ZeroGPU.")
            answer = input(f"Delete and recreate ONLY {repo_id} as ZeroGPU? [Y/n]: ").strip().lower()
            if answer not in {"", "y", "yes"}:
                print("Cancelled. No Space was deleted.")
                return 3
            api.delete_repo(repo_id=repo_id, repo_type="space")
            print(f"Deleted old {repo_id}.")
            runtime = None

        print(f"\nCreating/updating ZeroGPU Space: {repo_id}")
        try:
            api.create_repo(
                repo_id=repo_id,
                repo_type="space",
                space_sdk="gradio",
                space_hardware=ZERO_GPU,
                exist_ok=True,
            )
        except HfHubHTTPError as exc:
            print(f"ERROR creating {repo_id}: {exc}")
            print("If this is a 402/401, verify that your Hugging Face email is verified and your free account is in good standing and older than 30 days.")
            print("Free accounts cannot fall back to cpu-basic for new Gradio Spaces; ZeroGPU must be assigned at creation.")
            return 4

        print(f"Uploading: {folder}")
        upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=str(folder),
        )

        runtime = _runtime(api, repo_id)
        if runtime is not None:
            print(
                f"Runtime: stage={getattr(runtime, 'stage', None)} "
                f"hardware={getattr(runtime, 'hardware', None)} "
                f"requested={getattr(runtime, 'requested_hardware', None)}"
            )
            if not _is_zero(runtime):
                print("WARNING: Hugging Face created the Space but did not assign ZeroGPU.")
                return 5

        print(f"Space URL: https://huggingface.co/spaces/{repo_id}")

    print("\nDone. Both Cineqo ZeroGPU Spaces were created/uploaded.")
    print(f"CORE={me}/cineqo-core")
    print(f"VIDEO={me}/cineqo-video")
    print("\nInspect logs with:")
    print(f"hf spaces logs {me}/cineqo-core -n 50")
    print(f"hf spaces logs {me}/cineqo-video -n 50")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
