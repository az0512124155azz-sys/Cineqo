from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import HfApi, upload_folder

ROOT = Path(__file__).resolve().parent
SPACES = [
    ("cineqo-core", ROOT / "deploy" / "huggingface" / "core-space"),
    ("cineqo-video", ROOT / "deploy" / "huggingface" / "video-space"),
]


def main() -> int:
    api = HfApi()
    me = api.whoami()["name"]
    print(f"Logged in to Hugging Face as: {me}")

    for name, folder in SPACES:
        if not folder.exists():
            print(f"ERROR: missing folder: {folder}")
            return 2

        repo_id = f"{me}/{name}"
        print(f"\nCreating/updating Space: {repo_id}")
        api.create_repo(
            repo_id=repo_id,
            repo_type="space",
            space_sdk="gradio",
            exist_ok=True,
        )

        print(f"Uploading: {folder}")
        upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=str(folder),
        )

        print("Requesting ZeroGPU hardware...")
        try:
            runtime = api.request_space_hardware(repo_id=repo_id, hardware="zero-a10g")
            print(
                "ZeroGPU requested. "
                f"Current={getattr(runtime, 'hardware', None)} "
                f"Requested={getattr(runtime, 'requested_hardware', None)}"
            )
        except Exception as exc:
            print(f"ZeroGPU request was not accepted automatically: {exc}")
            print(
                "The Space was still created and uploaded. "
                "If your account is eligible, select ZeroGPU in the Space hardware settings."
            )

        try:
            runtime = api.get_space_runtime(repo_id=repo_id)
            print(
                f"Runtime: stage={getattr(runtime, 'stage', None)} "
                f"hardware={getattr(runtime, 'hardware', None)} "
                f"requested={getattr(runtime, 'requested_hardware', None)}"
            )
        except Exception as exc:
            print(f"Could not read runtime yet: {exc}")

        print(f"Space URL: https://huggingface.co/spaces/{repo_id}")

    print("\nDone. Both Cineqo Spaces were created/uploaded.")
    print(f"CORE={me}/cineqo-core")
    print(f"VIDEO={me}/cineqo-video")
    print("\nYou can inspect logs with:")
    print(f"hf spaces logs {me}/cineqo-core -n 50")
    print(f"hf spaces logs {me}/cineqo-video -n 50")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
