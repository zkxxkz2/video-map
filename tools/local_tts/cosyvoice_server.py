import argparse
import io
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def _prepare_imports(cosyvoice_root: Path):
    sys.path.insert(0, str(cosyvoice_root))
    sys.path.insert(0, str(cosyvoice_root / "third_party" / "Matcha-TTS"))


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    speaker: str = Field(..., min_length=1)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


def build_app(cosyvoice_root: Path, model_dir: str):
    _prepare_imports(cosyvoice_root)
    from cosyvoice.cli.cosyvoice import AutoModel

    cosyvoice = AutoModel(model_dir=model_dir)
    sample_rate = cosyvoice.sample_rate

    app = FastAPI(title="Local CosyVoice Service", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "sample_rate": sample_rate,
            "voices": len(cosyvoice.list_available_spks()),
            "model_dir": model_dir,
        }

    @app.get("/voices")
    def voices():
        return {"voices": cosyvoice.list_available_spks()}

    @app.post("/synthesize")
    def synthesize(body: SynthesizeRequest):
        if body.speaker not in cosyvoice.list_available_spks():
            raise HTTPException(status_code=400, detail=f"unknown speaker: {body.speaker}")

        chunks = []
        silence = torch.zeros((1, int(sample_rate * 0.12)), dtype=torch.float32)
        for item in cosyvoice.inference_sft(
            body.text, body.speaker, stream=False, speed=body.speed
        ):
            tts_speech = item["tts_speech"]
            if tts_speech.ndim == 1:
                tts_speech = tts_speech.unsqueeze(0)
            chunks.append(tts_speech.cpu())
            chunks.append(silence)

        if not chunks:
            raise HTTPException(status_code=500, detail="cosyvoice returned no audio")

        merged = torch.cat(chunks[:-1], dim=1)
        audio = merged.squeeze(0).numpy().astype(np.float32)
        buffer = io.BytesIO()
        sf.write(buffer, audio, sample_rate, format="WAV")
        return Response(
            content=buffer.getvalue(),
            media_type="audio/wav",
            headers={"X-Sample-Rate": str(sample_rate)},
        )

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cosyvoice-root",
        required=True,
        help="Path to the cloned upstream CosyVoice repository",
    )
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Local model directory or ModelScope model id",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9880)
    args = parser.parse_args()

    cosyvoice_root = Path(args.cosyvoice_root).resolve()
    if not cosyvoice_root.exists():
        raise FileNotFoundError(f"CosyVoice root not found: {cosyvoice_root}")

    app = build_app(cosyvoice_root=cosyvoice_root, model_dir=args.model_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
