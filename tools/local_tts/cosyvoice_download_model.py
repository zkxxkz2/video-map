import argparse
import os
from pathlib import Path

from modelscope import snapshot_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-id",
        default="iic/CosyVoice-300M-SFT",
        help="ModelScope model id",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory where the model will be downloaded",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.strip()
    if not output_dir:
        model_name = args.model_id.split("/")[-1]
        output_dir = str(
            Path(__file__).resolve().parents[2] / "storage" / "local_tts" / "models" / model_name
        )

    os.makedirs(output_dir, exist_ok=True)
    print(f"Downloading {args.model_id} to {output_dir}")
    snapshot_download(args.model_id, local_dir=output_dir)
    print(f"Model ready: {output_dir}")


if __name__ == "__main__":
    main()
