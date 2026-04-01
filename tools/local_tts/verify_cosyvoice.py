import argparse
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:9880")
    parser.add_argument("--speaker", default="")
    parser.add_argument("--text", default="你好，我是本地部署的 CosyVoice 语音服务。")
    parser.add_argument(
        "--output",
        default="",
        help="Optional path used to save the synthesized wav file",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    health = requests.get(f"{base_url}/health", timeout=10)
    health.raise_for_status()
    print("Health:", health.json())

    voices_resp = requests.get(f"{base_url}/voices", timeout=10)
    voices_resp.raise_for_status()
    voices = voices_resp.json().get("voices", [])
    print("Voices:", voices)
    if not voices:
        raise RuntimeError("No voices returned by CosyVoice service")

    speaker = args.speaker or voices[0]
    synth = requests.post(
        f"{base_url}/synthesize",
        json={"text": args.text, "speaker": speaker, "speed": 1.0},
        timeout=(30, 600),
    )
    synth.raise_for_status()

    output = args.output.strip()
    if not output:
        output = str(Path(__file__).resolve().parents[2] / "storage" / "temp" / "cosyvoice-verify.wav")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(synth.content)
    print(f"Audio saved to: {output_path}")


if __name__ == "__main__":
    main()
