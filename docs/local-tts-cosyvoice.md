# Local CosyVoice TTS

This project can call a locally deployed CosyVoice SFT service for offline TTS.

## What gets deployed

- Upstream project: `FunAudioLLM/CosyVoice`
- Model source: ModelScope
- Recommended model for this project: `iic/CosyVoice-300M-SFT`

This model exposes built-in speakers, so it fits the current MoneyPrinterTurbo workflow without voice cloning or training.

## Bootstrap

From the project root on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\local_tts\bootstrap_cosyvoice.ps1
```

Recommended for single-environment deployment (run inside your activated `video` conda env):

```powershell
conda activate video
powershell -ExecutionPolicy Bypass -File .\tools\local_tts\bootstrap_cosyvoice.ps1 -UseCurrentEnv $true
```

That script will:

- use current Python env by default (`-UseCurrentEnv $true`)
- optionally create `storage/local_tts/venv` only when `-UseCurrentEnv $false`
- clone/update `storage/local_tts/CosyVoice-upstream`
- install upstream dependencies into the selected runtime Python
- download `iic/CosyVoice-300M-SFT` from ModelScope
- store ModelScope cache under `storage/local_tts/modelscope_cache`

## Start the local TTS service

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\local_tts\start_cosyvoice.ps1 -PythonExe "D:\anaconda3\envs\video\python.exe"
```

The default local API endpoint is:

```text
http://127.0.0.1:9880
```

## Verify the service

```powershell
D:\anaconda3\envs\video\python.exe .\tools\local_tts\verify_cosyvoice.py
```

If the service is healthy, the script will:

- print health data
- print the built-in speaker list
- synthesize a short test sentence
- save a `.wav` file under `storage/temp/cosyvoice-verify.wav`

## MoneyPrinterTurbo integration

After the local service is running:

1. Open the WebUI.
2. In `Audio Settings`, choose `Local CosyVoice`.
3. Set `Local TTS Base URL` if needed.
4. Pick one of the built-in speakers returned by the service.

The generated audio is stored as `.wav`, and subtitles continue to use the existing subtitle pipeline.
