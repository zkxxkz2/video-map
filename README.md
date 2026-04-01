# Video-Map

个人维护仓库地址：

- https://github.com/zkxxkz2/video-map

## 项目简介

`Video-Map` 是一个自动化短视频生成工具。输入主题或文案后，系统会完成：

1. LLM 生成脚本与素材关键词
2. 语音合成（支持本地 CosyVoice）
3. 字幕生成
4. 素材检索/下载或本地素材预处理
5. 片段拼接与最终视频导出

## 当前分支特点

- 默认可切换并支持 `local-cosyvoice`
- 增加了 Windows/macOS 启动脚本
- 启动脚本已加入端口冲突检测（如 `8501`、`9880`）
- 适配单环境（`video` conda）运行方案

## 快速开始

1. 克隆仓库

```bash
git clone https://github.com/zkxxkz2/video-map.git
cd video-map
```

2. 准备配置

```bash
cp config.example.toml config.toml
```

3. 安装依赖（示例）

```bash
pip install -r requirements.txt
```

4. 启动 WebUI

```bash
python -m streamlit run ./webui/Main.py --browser.gatherUsageStats=False --server.enableCORS=True
```

## Docker

```bash
docker compose up --build
```

默认端口：

- WebUI: `8501`
- API: `8080`

## Pexels API 使用限制

已补充单独说明文档：

- [docs/pexels-api-limit-guide.md](docs/pexels-api-limit-guide.md)

内容包含：

1. 官方默认限额（每小时、每月）
2. 本项目推荐并发策略
3. 如何根据响应头做额度监控
4. 触发 `429` 后的回退与重试建议

### 已内置到代码的限额策略

`video_source=pexels` 时，项目会自动启用以下策略（见 `app/services/material.py`）：

1. 请求间隔节流：默认最小间隔 `0.35s`
2. 重试次数：默认最多 `4` 次
3. 退避策略：遇到 `429` 或 `5xx` 使用指数退避（`1s, 2s, 4s, 8s`）
4. 额度日志：记录 `X-Ratelimit-Limit / Remaining / Reset` 响应头

可在 `config.toml` 的 `[app]` 区域按需覆盖：

```toml
pexels_min_interval_seconds = 0.35
pexels_max_retries = 4
pexels_backoff_base_seconds = 1.0
```

## 目录说明

- `app/` 业务逻辑与服务
- `webui/` Streamlit 前端
- `tools/local_tts/` 本地 TTS 启动与验证脚本
- `storage/` 任务输出、缓存与本地模型目录

## 注意事项

- 模型文件不应提交到 Git 仓库
- 若端口被占用，先释放端口再启动脚本
- 本地 TTS 建议先验证 `http://127.0.0.1:9880/health`
