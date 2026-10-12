"""Choose the local backend's embedding device, keeping the Qwen model."""

import argparse
from pathlib import Path

from dotenv import set_key
import torch

ROOT = Path(__file__).resolve().parents[1]
QWEN = "Qwen/Qwen3-Embedding-0.6B"


def configure(device: str, env_file: Path) -> None:
    if device not in {"auto", "cpu", "cuda"}:
        raise ValueError("Device must be auto, cpu or cuda.")
    if not env_file.is_file():
        raise RuntimeError(
            "backend/.env is missing. Create your local configuration first."
        )
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is unavailable. Install a compatible NVIDIA driver and CUDA-enabled PyTorch first. "
            "Your existing settings were not changed."
        )
    set_key(str(env_file), "AURA_EMBEDDING_MODEL", QWEN)
    set_key(str(env_file), "AURA_EMBEDDING_DEVICE", device)
    selected = (
        ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
    )
    print(f"Saved Qwen embedding configuration: {device}; current device: {selected}.")
    if selected == "cuda":
        print("Detected GPU:", torch.cuda.get_device_name(0))
    print(
        "Restart the backend to apply the setting. Database and authentication settings are preserved."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args()
    device = args.device
    if device is None:
        print("Qwen embedding device: 1) Auto  2) NVIDIA GPU (CUDA)  3) CPU")
        choice = input("Choose 1, 2 or 3 [1]: ").strip() or "1"
        device = {"1": "auto", "2": "cuda", "3": "cpu"}.get(choice)
        if device is None:
            raise SystemExit("Invalid choice. No settings were changed.")
    try:
        configure(device, ROOT / "backend/.env")
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
