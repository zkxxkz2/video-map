# Video-Map 在 Mac mini 使用指南（单环境 + 本地 CosyVoice）

本指南适用于你当前这套改造后的项目：
- WebUI 与本地 TTS 使用同一个 Python 环境（推荐 conda 环境名 `video`）
- CosyVoice 模型放在项目目录内，便于整包迁移

## 1. 迁移前要打包哪些内容

从当前机器拷走整个项目目录 `video-map`，并确保以下路径存在：

- `storage/local_tts/models/CosyVoice-300M-SFT`
- `storage/local_tts/CosyVoice-upstream`
- `storage/local_tts/modelscope_cache`（可选，但建议保留，减少首次启动下载）
- `config.toml`

不需要带 Windows 便携运行时（在仓库外层的 `lib/python`、`lib/ffmpeg`、`lib/imagemagic` 这些目录）。

## 2. Mac mini 基础准备

先安装系统依赖（如果你还没装）：

```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install ffmpeg imagemagick
```

## 3. 创建并激活 video 环境

建议 Python 3.10：

```bash
conda create -n video python=3.10 -y
conda activate video
```

进入项目目录（示例）：

```bash
cd /path/to/video-map
```

## 4. 一键启动（推荐）

项目已提供脚本：`start_macos_video.sh`

首次运行建议：

```bash
chmod +x ./start_macos_video.sh
PYTHON_BIN=$(which python) bash ./start_macos_video.sh
```

脚本会自动做这些事：
- 安装主项目依赖：`requirements.txt`
- 安装本地 TTS 依赖：`tools/local_tts/requirements.cosyvoice-runtime.macos.txt`
- 启动本地 CosyVoice 服务（默认 `127.0.0.1:9880`）
- 健康检查通过后启动 WebUI

## 5. 手动启动（需要拆分排查时使用）

### 5.1 安装依赖

```bash
conda activate video
python -m pip install -r requirements.txt
python -m pip install -r tools/local_tts/requirements.cosyvoice-runtime.macos.txt
```

### 5.2 启动本地 TTS

```bash
conda activate video
export MODELSCOPE_CACHE="$(pwd)/storage/local_tts/modelscope_cache"
python tools/local_tts/cosyvoice_server.py \
  --cosyvoice-root "$(pwd)/storage/local_tts/CosyVoice-upstream" \
  --model-dir "$(pwd)/storage/local_tts/models/CosyVoice-300M-SFT" \
  --host 127.0.0.1 \
  --port 9880
```

### 5.3 启动 WebUI

```bash
conda activate video
streamlit run ./webui/Main.py --browser.serverAddress="0.0.0.0" --server.enableCORS=True --browser.gatherUsageStats=False
```

## 6. WebUI 配置建议

进入 WebUI 后：

1. 在 Audio Settings 里选择 `Local CosyVoice`
2. `Local TTS Base URL` 设为 `http://127.0.0.1:9880`
3. 选择可用音色（如 `中文女`）

如你已迁移 `config.toml`，这些通常会自动保留。

## 7. 快速验证

### 7.1 检查 TTS 健康状态

```bash
curl http://127.0.0.1:9880/health
curl http://127.0.0.1:9880/voices
```

### 7.2 生成一段测试语音

```bash
conda activate video
python tools/local_tts/verify_cosyvoice.py --base-url http://127.0.0.1:9880
```

成功后会输出并写入测试音频文件。

## 8. 常见问题

### 8.1 启动时报 `python not found`

请显式指定解释器：

```bash
PYTHON_BIN=/path/to/miniconda3/envs/video/bin/python bash ./start_macos_video.sh
```

### 8.2 本地 TTS 端口不通

先确认服务是否在跑：

```bash
lsof -iTCP:9880 -sTCP:LISTEN
```

若未运行，先单独启动 `cosyvoice_server.py`，再启动 WebUI。

### 8.3 首次启动下载较慢

这是正常现象。已把模型和缓存放在项目内后，后续速度会明显提升。

### 8.4 与 Windows GPU 速度不同

Mac mini 不使用 CUDA，性能可能与 Windows + NVIDIA 不同，这是预期行为。

## 9. 相关文件

- `start_macos_video.sh`
- `tools/local_tts/cosyvoice_server.py`
- `tools/local_tts/requirements.cosyvoice-runtime.macos.txt`
- `tools/local_tts/verify_cosyvoice.py`
- `config.toml`
