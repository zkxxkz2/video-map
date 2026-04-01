import os
import platform
import sys
import threading
from uuid import uuid4

import streamlit as st
from loguru import logger

# Add the root directory of the project to the system path to allow importing modules from the project
root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)
    print("******** sys.path ********")
    print(sys.path)
    print("")

from app.config import config
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services import llm, voice
from app.services import task as tm
from app.utils import utils

st.set_page_config(
    page_title="Video-Map",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="auto",
    menu_items={
        "Report a bug": "https://github.com/zkxxkz2/video-map/issues",
        "About": "# Video-Map\nSimply provide a topic or keyword for a video, and it will "
        "automatically generate the video copy, video materials, video subtitles, "
        "and video background music before synthesizing a high-definition short "
        "video.\n\nhttps://github.com/zkxxkz2/video-map",
    },
)



if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "Light" # Default

# Decide CSS variables based on theme
if st.session_state["theme_mode"] == "Dark":
    theme_css = """
    :root {
        --vm-bg-main: #0e1117;
        --vm-bg-sidebar: #161b22;
        --vm-panel: #1c2128;
        --vm-panel-hover: #22272e;
        --vm-border: #30363d;
        --vm-text-primary: #e6edf3;
        --vm-text-muted: #9eabb8;
        --vm-accent: #2ea043;
        --vm-accent-hover: #3fb950;
        --widget-bg: #161b22;
    }
    """
else:
    theme_css = """
    :root {
        --vm-bg-main: #ffffff;
        --vm-bg-sidebar: #f6f8fa;
        --vm-panel: #ffffff;
        --vm-panel-hover: #f0f2f5;
        --vm-border: #d0d7de;
        --vm-text-primary: #1f2328;
        --vm-text-muted: #59636e;
        --vm-accent: #1f883d;
        --vm-accent-hover: #2ea043;
        --widget-bg: #ffffff;
    }
    """

streamlit_style = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

{theme_css}

html, body, [class*="css"] {{
    font-family: "Inter", -apple-system, sans-serif;
    color: var(--vm-text-primary) !important;
    background-color: var(--vm-bg-main) !important;
}}

/* Force text visibility across ALL widgets */
input, textarea, select, [data-baseweb="select"] span,
[data-baseweb="select"] div, .stSelectbox label, .stTextInput label,
.stNumberInput label, .stSlider label, .stRadio label, .stCheckbox label,
.stTextArea label, p, span, li, td, th {{
    color: var(--vm-text-primary) !important;
}}
[data-testid="stWidgetLabel"] label, [data-testid="stWidgetLabel"] p {{
    color: var(--vm-text-primary) !important;
}}
.stSelectbox [data-baseweb="select"] > div {{
    color: var(--vm-text-primary) !important;
    background-color: var(--widget-bg) !important;
}}

/* Fix Dropdown Popovers - Ensure contrast for the opened menu */
div[data-baseweb="popover"] {{
    z-index: 999999 !important;
}}
div[data-baseweb="popover"] ul {{
    background-color: var(--vm-panel) !important;
    border: 1px solid var(--vm-border) !important;
    padding: 4px !important;
}}
div[data-baseweb="popover"] li {{
    background-color: transparent !important;
    color: var(--vm-text-primary) !important;
    transition: background-color 0.2s !important;
}}
div[data-baseweb="popover"] li:hover {{
    background-color: var(--vm-panel-hover) !important;
    color: var(--vm-text-primary) !important;
}}
/* Fix for the selected/highlighted state inside the dropdown */
div[data-baseweb="popover"] [aria-selected="true"] {{
    background-color: var(--vm-accent) !important;
    color: #ffffff !important;
}}

/* Fix st.code / Log Container visibility across themes - More aggressive */
.stCodeBlock, 
[data-testid="stCodeBlock"], 
pre, 
code {{
    background-color: var(--vm-panel) !important;
    color: var(--vm-text-primary) !important;
    border: 1px solid var(--vm-border) !important;
}}

/* Override all internal syntax highlighting colors to ensure readability in light mode */
[data-testid="stCodeBlock"] * {{
    color: inherit !important;
    background-color: transparent !important;
    text-shadow: none !important;
}}

/* Fix File Uploader visibility across themes */
[data-testid="stFileUploadDropzone"], 
[data-testid="stFileUploaderSection"],
.stFileUploader section {{
    background-color: var(--vm-panel) !important;
    background: var(--vm-panel) !important;
    border: 1px dashed var(--vm-border) !important;
    color: var(--vm-text-primary) !important;
}}

/* Ensure all text inside the uploader is visible */
[data-testid="stFileUploadDropzone"] div, 
[data-testid="stFileUploadDropzone"] p, 
[data-testid="stFileUploadDropzone"] span,
[data-testid="stFileUploadDropzone"] small {{
    color: var(--vm-text-primary) !important;
}}

/* Style the 'Browse files' button to match theme */
[data-testid="stFileUploader"] button {{
    background-color: var(--vm-panel) !important;
    border: 1px solid var(--vm-border) !important;
    color: var(--vm-text-primary) !important;
}}

/* Fix File Uploader List - Make it scrollable and compact */
[data-testid="stFileUploaderList"] {{
    max-height: 220px !important;
    overflow-y: auto !important;
    padding-right: 10px !important;
    border: 1px solid var(--vm-border) !important;
    border-radius: 4px !important;
    margin-top: 10px !important;
    background-color: rgba(0,0,0,0.02) !important;
}}

/* Base app backgrounds */
.stApp {{
    background-color: var(--vm-bg-main);
}}

[data-testid="stHeader"], 
header[data-testid="stHeader"], 
.stHeader, 
[data-testid="stToolbar"] {{
    background-color: var(--vm-bg-main) !important;
    background: var(--vm-bg-main) !important;
    color: var(--vm-text-primary) !important;
}}

[data-testid="stSidebar"] {{
    background-color: var(--vm-bg-sidebar) !important;
    border-right: 1px solid var(--vm-border);
}}

/* Compact layout for editing workspace */
[data-testid="stMainBlockContainer"] {{
    padding-top: 1.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 1600px;
}}

/* Workspace Header */
.vm-workspace-header {{
    margin: 0 0 1rem 0;
    padding: 0.8rem 1.2rem;
    border-radius: 6px;
    border: 1px solid var(--vm-border);
    background: var(--vm-panel);
    border-left: 4px solid var(--vm-accent);
}}
.vm-workspace-title {{
    font-weight: 700;
    font-size: 1.4rem;
    color: var(--vm-text-primary);
    display: flex;
    align-items: center;
    gap: 10px;
}}
.vm-workspace-version {{
    font-size: 0.85rem;
    font-weight: 400;
    color: var(--vm-accent);
    background: rgba(46, 160, 67, 0.15);
    padding: 2px 8px;
    border-radius: 12px;
    border: 1px solid rgba(46, 160, 67, 0.3);
}}
.vm-workspace-desc {{
    font-size: 0.85rem;
    color: var(--vm-text-muted);
    margin-top: 0.4rem;
}}

/* Containers mapping to panels */
[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 6px !important;
    border: 1px solid var(--vm-border) !important;
    background-color: var(--vm-panel) !important;
    box-shadow: none !important;
    padding: 0.5rem !important;
}}

/* FIX TRUNCATION: Remove aggressive padding and height restrictions for inputs */
[data-baseweb="select"] > div, 
.stTextInput > div > div > input, 
.stTextArea textarea, 
.stNumberInput input {{
    border-radius: 4px !important;
    border: 1px solid var(--vm-border) !important;
    background-color: var(--widget-bg) !important;
    color: var(--vm-text-primary) !important;
    /* Do not force font-size or padding here to avoid breaking Streamlit's native input sizes */
}}

/* Buttons */
button[kind="primary"] {{
    border-radius: 4px !important;
    background-color: var(--vm-accent) !important;
    border: 1px solid rgba(240,246,252,0.1) !important;
    color: #ffffff !important;
    font-weight: 500 !important;
    transition: background-color 0.2s;
}}
button[kind="primary"]:hover {{
    background-color: var(--vm-accent-hover) !important;
}}
button[kind="secondary"] {{
    border-radius: 4px !important;
    background-color: var(--vm-panel) !important;
    border: 1px solid var(--vm-border) !important;
    transition: background-color 0.2s;
}}
button[kind="secondary"]:hover {{
    border-color: var(--vm-text-muted) !important;
}}

/* Typography and metrics */
h1, h2, h3, label, .stMarkdown p {{
    color: var(--vm-text-primary) !important;
}}
label, .stCaption {{
    color: var(--vm-text-muted) !important;
}}
[data-testid="stMetricValue"] {{
    color: var(--vm-text-primary) !important;
    font-size: 1.5rem !important;
    font-weight: 600 !important;
}}
[data-testid="stMetricLabel"] {{
    color: var(--vm-text-muted) !important;
    font-size: 0.85rem !important;
}}

/* Expanders */
[data-testid="stExpander"] {{
    border: 1px solid var(--vm-border);
    border-radius: 4px;
    background-color: var(--vm-bg-main);
}}

/* Tabs */
button[data-baseweb="tab"] {{
    border-radius: 4px 4px 0 0 !important;
}}

/* Custom Thin Scrollbar */
::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
}}
::-webkit-scrollbar-track {{
    background: transparent;
}}
::-webkit-scrollbar-thumb {{
    background: rgba(255, 255, 255, 0.15);
    border-radius: 3px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: rgba(255, 255, 255, 0.3);
}}

/* Hover Depth for Containers */
[data-testid="stVerticalBlockBorderWrapper"]:hover,
[data-testid="stExpander"]:hover {{
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    transition: box-shadow 0.2s ease-in-out;
}}

/* Floating Primary Button */
/* Removed due to user feedback indicating it floats too high and blocks content */
</style>
"""
st.markdown(streamlit_style, unsafe_allow_html=True)

# 定义资源目录
font_dir = os.path.join(root_dir, "resource", "fonts")
song_dir = os.path.join(root_dir, "resource", "songs")
i18n_dir = os.path.join(root_dir, "webui", "i18n")
config_file = os.path.join(root_dir, "webui", ".streamlit", "webui.toml")
system_locale = utils.get_system_locale()


if "video_subject" not in st.session_state:
    st.session_state["video_subject"] = ""
if "video_script" not in st.session_state:
    st.session_state["video_script"] = ""
if "video_terms" not in st.session_state:
    st.session_state["video_terms"] = ""
if "ui_language" not in st.session_state:
    st.session_state["ui_language"] = config.ui.get("language", system_locale)

# 加载语言文件
locales = utils.load_locales(i18n_dir)

# Title moved to workspace header for high-density layout

with st.sidebar:
    theme_toggle = st.radio("界面主题", ["Light", "Dark"], horizontal=True, index=0 if st.session_state["theme_mode"] == "Light" else 1)
    if theme_toggle != st.session_state["theme_mode"]:
        st.session_state["theme_mode"] = theme_toggle
        st.rerun()
        
    st.header("全局设置")
    # 仅保留简体中文和英文的界面语言
    allowed_ui_langs = ["zh", "en"]
    display_languages = []
    selected_index = 0
    filtered_codes = [c for c in locales.keys() if c in allowed_ui_langs]
    for i, code in enumerate(filtered_codes):
        display_languages.append(f"{code} - {locales[code].get('Language')}")
        if code == st.session_state.get("ui_language", ""):
            selected_index = i

    selected_language = st.selectbox(
        "界面语言",
        options=display_languages,
        index=selected_index,
        key="top_language_selector",
    )
    if selected_language:
        code = selected_language.split(" - ")[0].strip()
        st.session_state["ui_language"] = code
        config.ui["language"] = code
        
    st.divider()

support_locales = [
    "zh-CN",
    "zh-TW",
    "en-US",
    "ja-JP",
]


def get_all_fonts():
    fonts = []
    for root, dirs, files in os.walk(font_dir):
        for file in files:
            if file.endswith(".ttf") or file.endswith(".ttc"):
                fonts.append(file)
    fonts.sort()
    return fonts


def get_all_songs():
    songs = []
    for root, dirs, files in os.walk(song_dir):
        for file in files:
            if file.endswith(".mp3"):
                songs.append(file)
    return songs


def open_task_folder(task_id):
    try:
        sys = platform.system()
        path = os.path.join(root_dir, "storage", "tasks", task_id)
        if os.path.exists(path):
            if sys == "Windows":
                os.system(f"start {path}")
            if sys == "Darwin":
                os.system(f"open {path}")
    except Exception as e:
        logger.error(e)


def scroll_to_bottom():
    js = """
    <script>
        console.log("scroll_to_bottom");
        function scroll(dummy_var_to_force_repeat_execution){
            var sections = parent.document.querySelectorAll('section.main');
            console.log(sections);
            for(let index = 0; index<sections.length; index++) {
                sections[index].scrollTop = sections[index].scrollHeight;
            }
        }
        scroll(1);
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def init_log():
    logger.remove()
    _lvl = "DEBUG"

    def format_record(record):
        # 获取日志记录中的文件全路径
        file_path = record["file"].path
        # 将绝对路径转换为相对于项目根目录的路径
        relative_path = os.path.relpath(file_path, root_dir)
        # 更新记录中的文件路径
        record["file"].path = f"./{relative_path}"
        # 返回修改后的格式字符串
        # 您可以根据需要调整这里的格式
        record["message"] = record["message"].replace(root_dir, ".")

        _format = (
            "<green>{time:%Y-%m-%d %H:%M:%S}</> | "
            + "<level>{level}</> | "
            + '"{file.path}:{line}":<blue> {function}</> '
            + "- <level>{message}</>"
            + "\n"
        )
        return _format

    logger.add(
        sys.stdout,
        level=_lvl,
        format=format_record,
        colorize=True,
    )


init_log()

locales = utils.load_locales(i18n_dir)


def tr(key):
    loc = locales.get(st.session_state["ui_language"], {})
    return loc.get("Translation", {}).get(key, key)


# 创建基础设置折叠框
if True: # Removed conditional hide_config check per user request

    with st.sidebar:
        st.subheader(tr("引擎与API配置 (Engine & API)"))
        
        left_config_panel = st.container()
        middle_config_panel = st.container()
        right_config_panel = st.container()

        # 左侧面板 - 日志设置
        with left_config_panel:
            st.write(tr("Log Settings"))
            # Removed Hide Basic Settings and Hide Log toggles per user feedback


        # 中间面板 - LLM 设置

        with middle_config_panel:
            st.write(tr("LLM Settings"))
            llm_providers = [
                "OpenAI",
                "Moonshot",
                "Azure",
                "Qwen",
                "DeepSeek",
                "ModelScope",
                "Gemini",
                "Ollama",
                "G4f",
                "OneAPI",
                "Cloudflare",
                "ERNIE",
                "Pollinations",
            ]
            saved_llm_provider = config.app.get("llm_provider", "OpenAI").lower()
            saved_llm_provider_index = 0
            for i, provider in enumerate(llm_providers):
                if provider.lower() == saved_llm_provider:
                    saved_llm_provider_index = i
                    break

            llm_provider = st.selectbox(
                tr("LLM Provider"),
                options=llm_providers,
                index=saved_llm_provider_index,
            )
            llm_helper = st.container()
            llm_provider = llm_provider.lower()
            config.app["llm_provider"] = llm_provider

            llm_api_key = config.app.get(f"{llm_provider}_api_key", "")
            llm_secret_key = config.app.get(
                f"{llm_provider}_secret_key", ""
            )  # only for baidu ernie
            llm_base_url = config.app.get(f"{llm_provider}_base_url", "")
            llm_model_name = config.app.get(f"{llm_provider}_model_name", "")
            llm_account_id = config.app.get(f"{llm_provider}_account_id", "")

            tips = ""
            if llm_provider == "ollama":
                if not llm_model_name:
                    llm_model_name = "qwen:7b"
                if not llm_base_url:
                    llm_base_url = "http://localhost:11434/v1"

                with llm_helper:
                    tips = """
                            ##### Ollama配置说明
                            - **API Key**: 随便填写，比如 123
                            - **Base Url**: 一般为 http://localhost:11434/v1
                                - 如果 `Video-Map` 和 `Ollama` **不在同一台机器上**，需要填写 `Ollama` 机器的IP地址
                                - 如果 `Video-Map` 是 `Docker` 部署，建议填写 `http://host.docker.internal:11434/v1`
                            - **Model Name**: 使用 `ollama list` 查看，比如 `qwen:7b`
                            """

            if llm_provider == "openai":
                if not llm_model_name:
                    llm_model_name = "gpt-3.5-turbo"
                with llm_helper:
                    tips = """
                            ##### OpenAI 配置说明
                            > 需要VPN开启全局流量模式
                            - **API Key**: [点击到官网申请](https://platform.openai.com/api-keys)
                            - **Base Url**: 可以留空
                            - **Model Name**: 填写**有权限**的模型，[点击查看模型列表](https://platform.openai.com/settings/organization/limits)
                            """

            if llm_provider == "moonshot":
                if not llm_model_name:
                    llm_model_name = "moonshot-v1-8k"
                with llm_helper:
                    tips = """
                            ##### Moonshot 配置说明
                            - **API Key**: [点击到官网申请](https://platform.moonshot.cn/console/api-keys)
                            - **Base Url**: 固定为 https://api.moonshot.cn/v1
                            - **Model Name**: 比如 moonshot-v1-8k，[点击查看模型列表](https://platform.moonshot.cn/docs/intro#%E6%A8%A1%E5%9E%8B%E5%88%97%E8%A1%A8)
                            """
            if llm_provider == "oneapi":
                if not llm_model_name:
                    llm_model_name = (
                        "claude-3-5-sonnet-20240620"  # 默认模型，可以根据需要调整
                    )
                with llm_helper:
                    tips = """
                        ##### OneAPI 配置说明
                        - **API Key**: 填写您的 OneAPI 密钥
                        - **Base Url**: 填写 OneAPI 的基础 URL
                        - **Model Name**: 填写您要使用的模型名称，例如 claude-3-5-sonnet-20240620
                        """

            if llm_provider == "qwen":
                if not llm_model_name:
                    llm_model_name = "qwen-max"
                with llm_helper:
                    tips = """
                            ##### 通义千问Qwen 配置说明
                            - **API Key**: [点击到官网申请](https://dashscope.console.aliyun.com/apiKey)
                            - **Base Url**: 留空
                            - **Model Name**: 比如 qwen-max，[点击查看模型列表](https://help.aliyun.com/zh/dashscope/developer-reference/model-introduction#3ef6d0bcf91wy)
                            """

            if llm_provider == "g4f":
                if not llm_model_name:
                    llm_model_name = "gpt-3.5-turbo"
                with llm_helper:
                    tips = """
                            ##### gpt4free 配置说明
                            > [GitHub开源项目](https://github.com/xtekky/gpt4free)，可以免费使用GPT模型，但是**稳定性较差**
                            - **API Key**: 随便填写，比如 123
                            - **Base Url**: 留空
                            - **Model Name**: 比如 gpt-3.5-turbo，[点击查看模型列表](https://github.com/xtekky/gpt4free/blob/main/g4f/models.py#L308)
                            """
            if llm_provider == "azure":
                with llm_helper:
                    tips = """
                            ##### Azure 配置说明
                            > [点击查看如何部署模型](https://learn.microsoft.com/zh-cn/azure/ai-services/openai/how-to/create-resource)
                            - **API Key**: [点击到Azure后台创建](https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/OpenAI)
                            - **Base Url**: 留空
                            - **Model Name**: 填写你实际的部署名
                            """

            if llm_provider == "gemini":
                if not llm_model_name:
                    llm_model_name = "gemini-1.0-pro"

                with llm_helper:
                    tips = """
                            ##### Gemini 配置说明
                            > 需要VPN开启全局流量模式
                            - **API Key**: [点击到官网申请](https://ai.google.dev/)
                            - **Base Url**: 留空
                            - **Model Name**: 比如 gemini-1.0-pro
                            """

            if llm_provider == "deepseek":
                if not llm_model_name:
                    llm_model_name = "deepseek-chat"
                if not llm_base_url:
                    llm_base_url = "https://api.deepseek.com"
                with llm_helper:
                    tips = """
                            ##### DeepSeek 配置说明
                            - **API Key**: [点击到官网申请](https://platform.deepseek.com/api_keys)
                            - **Base Url**: 固定为 https://api.deepseek.com
                            - **Model Name**: 固定为 deepseek-chat
                            """

            if llm_provider == "modelscope":
                if not llm_model_name:
                    llm_model_name = "Qwen/Qwen3-32B"
                if not llm_base_url:
                    llm_base_url = "https://api-inference.modelscope.cn/v1/"
                with llm_helper:
                    tips = """
                            ##### ModelScope 配置说明
                            - **API Key**: [点击到官网申请](https://modelscope.cn/docs/model-service/API-Inference/intro)
                            - **Base Url**: 固定为 https://api-inference.modelscope.cn/v1/
                            - **Model Name**: 比如 Qwen/Qwen3-32B，[点击查看模型列表](https://modelscope.cn/models?filter=inference_type&page=1)
                            """

            if llm_provider == "ernie":
                with llm_helper:
                    tips = """
                            ##### 百度文心一言 配置说明
                            - **API Key**: [点击到官网申请](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
                            - **Secret Key**: [点击到官网申请](https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application)
                            - **Base Url**: 填写 **请求地址** [点击查看文档](https://cloud.baidu.com/doc/WENXINWORKSHOP/s/jlil56u11#%E8%AF%B7%E6%B1%82%E8%AF%B4%E6%98%8E)
                            """

            if llm_provider == "pollinations":
                if not llm_model_name:
                    llm_model_name = "default"
                with llm_helper:
                    tips = """
                            ##### Pollinations AI Configuration
                            - **API Key**: Optional - Leave empty for public access
                            - **Base Url**: Default is https://text.pollinations.ai/openai
                            - **Model Name**: Use 'openai-fast' or specify a model name
                            """

            if tips and config.ui["language"] == "zh":
                st.warning(
                    "国内用户建议使用 **DeepSeek** 或 **Moonshot** 作为大模型提供商\n- 国内可直接访问，不需要VPN \n- 注册就送额度，基本够用"
                )
                st.info(tips)

            st_llm_api_key = st.text_input(
                tr("API Key"), value=llm_api_key, type="password"
            )
            st_llm_base_url = st.text_input(tr("Base Url"), value=llm_base_url)
            st_llm_model_name = ""
            if llm_provider != "ernie":
                st_llm_model_name = st.text_input(
                    tr("Model Name"),
                    value=llm_model_name,
                    key=f"{llm_provider}_model_name_input",
                )
                if st_llm_model_name:
                    config.app[f"{llm_provider}_model_name"] = st_llm_model_name
            else:
                st_llm_model_name = None

            if st_llm_api_key:
                config.app[f"{llm_provider}_api_key"] = st_llm_api_key
            if st_llm_base_url:
                config.app[f"{llm_provider}_base_url"] = st_llm_base_url
            if st_llm_model_name:
                config.app[f"{llm_provider}_model_name"] = st_llm_model_name
            if llm_provider == "ernie":
                st_llm_secret_key = st.text_input(
                    tr("Secret Key"), value=llm_secret_key, type="password"
                )
                config.app[f"{llm_provider}_secret_key"] = st_llm_secret_key

            if llm_provider == "cloudflare":
                st_llm_account_id = st.text_input(
                    tr("Account ID"), value=llm_account_id
                )
                if st_llm_account_id:
                    config.app[f"{llm_provider}_account_id"] = st_llm_account_id

        # 右侧面板 - API 密钥设置
        with right_config_panel:

            def get_keys_from_config(cfg_key):
                api_keys = config.app.get(cfg_key, [])
                if isinstance(api_keys, str):
                    api_keys = [api_keys]
                api_key = ", ".join(api_keys)
                return api_key

            def save_keys_to_config(cfg_key, value):
                value = value.replace(" ", "")
                if value:
                    config.app[cfg_key] = value.split(",")

            st.write(tr("Video Source Settings"))

            pexels_api_key = get_keys_from_config("pexels_api_keys")
            pexels_api_key = st.text_input(
                tr("Pexels API Key"), value=pexels_api_key, type="password"
            )
            save_keys_to_config("pexels_api_keys", pexels_api_key)

            pixabay_api_key = get_keys_from_config("pixabay_api_keys")
            pixabay_api_key = st.text_input(
                tr("Pixabay API Key"), value=pixabay_api_key, type="password"
            )
            save_keys_to_config("pixabay_api_keys", pixabay_api_key)

        with st.expander(tr("Click to show API Key management"), expanded=False):
            st.subheader(tr("Manage Pexels and Pixabay API Keys"))

            col1, col2 = st.tabs(["Pexels API Keys", "Pixabay API Keys"])

            with col1:
                st.subheader("Pexels API Keys")
                if config.app["pexels_api_keys"]:
                    st.write(tr("Current Keys:"))
                    for key in config.app["pexels_api_keys"]:
                        st.code(key)
                else:
                    st.info(tr("No Pexels API Keys currently"))

                new_key = st.text_input(tr("Add Pexels API Key"), key="pexels_new_key")
                if st.button(tr("Add Pexels API Key")):
                    if new_key and new_key not in config.app["pexels_api_keys"]:
                        config.app["pexels_api_keys"].append(new_key)
                        config.save_config()
                        st.success(tr("Pexels API Key added successfully"))
                    elif new_key in config.app["pexels_api_keys"]:
                        st.warning(tr("This API Key already exists"))
                    else:
                        st.error(tr("Please enter a valid API Key"))

                if config.app["pexels_api_keys"]:
                    delete_key = st.selectbox(
                        tr("Select Pexels API Key to delete"), config.app["pexels_api_keys"], key="pexels_delete_key"
                    )
                    if st.button(tr("Delete Selected Pexels API Key")):
                        config.app["pexels_api_keys"].remove(delete_key)
                        config.save_config()
                        st.success(tr("Pexels API Key deleted successfully"))

            with col2:
                st.subheader("Pixabay API Keys")

                if config.app["pixabay_api_keys"]:
                    st.write(tr("Current Keys:"))
                    for key in config.app["pixabay_api_keys"]:
                        st.code(key)
                else:
                    st.info(tr("No Pixabay API Keys currently"))

                new_key = st.text_input(tr("Add Pixabay API Key"), key="pixabay_new_key")
                if st.button(tr("Add Pixabay API Key")):
                    if new_key and new_key not in config.app["pixabay_api_keys"]:
                        config.app["pixabay_api_keys"].append(new_key)
                        config.save_config()
                        st.success(tr("Pixabay API Key added successfully"))
                    elif new_key in config.app["pixabay_api_keys"]:
                        st.warning(tr("This API Key already exists"))
                    else:
                        st.error(tr("Please enter a valid API Key"))

                if config.app["pixabay_api_keys"]:
                    delete_key = st.selectbox(
                        tr("Select Pixabay API Key to delete"), config.app["pixabay_api_keys"], key="pixabay_delete_key"
                    )
                    if st.button(tr("Delete Selected Pixabay API Key")):
                        config.app["pixabay_api_keys"].remove(delete_key)
                        config.save_config()
                        st.success(tr("Pixabay API Key deleted successfully"))


llm_provider = config.app.get("llm_provider", "").lower()
st.markdown(
    """
<div class="vm-workspace-header">
  <div class="vm-workspace-title">
    Video-Map <span class="vm-workspace-version">v1.0.0</span>
  </div>
  <div class="vm-workspace-desc"><b>创作工作台</b> | 脚本、素材、音频、字幕都在同一工作流中配置，生成行为保持不变。</div>
</div>
""",
    unsafe_allow_html=True,
)

work_columns = st.columns([1.1, 1, 1], gap="small")
left_panel = work_columns[0]
middle_panel = work_columns[1]
right_panel = work_columns[2]

params = VideoParams(video_subject="")
uploaded_files = []

with left_panel:


    if True: # was script_cfg_col
        with st.container(border=True):
            st.write("脚本控制")
            subject_presets = [
                "",
                "城市夜景",
                "自然风光",
                "旅行Vlog",
                "美食探店",
                "科技数码",
                "商业财经",
                "汽车机车",
                "健身运动",
                "宠物日常",
                "历史人文",
                "影视混剪",
            ]
            selected_subject_preset = st.selectbox(
                tr("Subject Presets"),
                options=subject_presets,
                index=0,
                help=tr("Choose a preset and apply it to Video Subject"),
            )
            if selected_subject_preset and st.button(
                tr("Apply Subject Preset"),
                key="apply_subject_preset",
                use_container_width=True,
            ):
                st.session_state["video_subject"] = selected_subject_preset
                st.rerun()

            params.video_subject = st.text_input(
                tr("Video Subject"),
                value=st.session_state["video_subject"],
                key="video_subject_input",
            ).strip()

            video_languages = [
                (tr("Auto Detect"), ""),
            ]
            for code in support_locales:
                video_languages.append((code, code))

            selected_index = st.selectbox(
                tr("Script Language"),
                index=0,
                options=range(len(video_languages)),
                format_func=lambda x: video_languages[x][0],
            )
            params.video_language = video_languages[selected_index][1]

            if st.button(
                tr("Generate Video Script and Keywords"),
                key="auto_generate_script",
                use_container_width=True,
            ):
                with st.spinner(tr("Generating Video Script and Keywords")):
                    script = llm.generate_script(
                        video_subject=params.video_subject, language=params.video_language
                    )
                    terms = llm.generate_terms(params.video_subject, script)
                    if "Error: " in script:
                        st.error(tr(script))
                    elif "Error: " in terms:
                        st.error(tr(terms))
                    else:
                        st.session_state["video_script"] = script
                        st.session_state["video_terms"] = ", ".join(terms)

            st.caption("先生成完整文案，再用文案生成关键词，匹配度更稳定。")

    if True: # was script_out_col
        with st.container(border=True):
            st.write("视频设置")
            params.video_script = st.text_area(
                tr("Video Script"), value=st.session_state["video_script"], height=300
            )


            if True: # was action_cols
                if st.button(tr("Generate Video Keywords"), key="auto_generate_terms", use_container_width=True):
                    if not params.video_script:
                        st.error(tr("Please Enter the Video Subject"))
                        st.stop()

                    with st.spinner(tr("Generating Video Keywords")):
                        terms = llm.generate_terms(params.video_subject, params.video_script)
                        if "Error: " in terms:
                            st.error(tr(terms))
                        else:
                            st.session_state["video_terms"] = ", ".join(terms)

            params.video_terms = st.text_area(
                tr("Video Keywords"), value=st.session_state["video_terms"], height=180
            )

with middle_panel:
    with st.container(border=True):
        st.write(tr("Video Settings"))
        video_concat_modes = [
            (tr("Sequential"), "sequential"),
            (tr("Random"), "random"),
        ]
        video_sources = [
            (tr("Pexels"), "pexels"),
            (tr("Pixabay"), "pixabay"),
            (tr("Local file"), "local"),
            (tr("TikTok"), "douyin"),
            (tr("Bilibili"), "bilibili"),
            (tr("Xiaohongshu"), "xiaohongshu"),
        ]

        saved_video_source_name = config.app.get("video_source", "pexels")
        saved_video_source_index = [v[1] for v in video_sources].index(
            saved_video_source_name
        )

        selected_index = st.selectbox(
            tr("Video Source"),
            options=range(len(video_sources)),
            format_func=lambda x: video_sources[x][0],
            index=saved_video_source_index,
        )
        params.video_source = video_sources[selected_index][1]
        config.app["video_source"] = params.video_source

        if params.video_source == "pexels":
            with st.expander("Pexels API 高级设置", expanded=False):
                pexels_mode_options = ["Search", "Popular"]
                current_mode = config.app.get("pexels_endpoint", "search").capitalize()
                
                selected_mode = st.radio("Pexels 抓取模式", pexels_mode_options, index=pexels_mode_options.index(current_mode) if current_mode in pexels_mode_options else 0, horizontal=True, help="Search: 根据关键词搜索。Popular: 获取当下流行的无关键词素材。")
                config.app["pexels_endpoint"] = selected_mode.lower()
                
                pexels_per_page = int(config.app.get("pexels_per_page", 20))
                pexels_per_page = min(max(pexels_per_page, 1), 80)
                config.app["pexels_per_page"] = st.slider(
                    "每页请求数量", min_value=1, max_value=80, value=pexels_per_page, help="单次API请求返回的素材最大数量。"
                )

                pexels_page = int(config.app.get("pexels_page", 1) or 1)
                pexels_page = max(1, pexels_page)
                config.app["pexels_page"] = st.number_input(
                    "起始页码", min_value=1, value=pexels_page, help="如果同一关键词想换一批素材，可以增加此页码。"
                )

                if config.app["pexels_endpoint"] == "popular":
                    st.write("---")
                    st.write("热门接口专属参数 (Popular API)")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        config.app["pexels_min_width"] = st.number_input("最小宽度 (min_width)", min_value=0, value=int(config.app.get("pexels_min_width", 0)), help="筛选画面宽度（像素）。不填填 0 即可。")
                        config.app["pexels_min_duration"] = st.number_input("最小时长 (min_duration)", min_value=0, value=int(config.app.get("pexels_min_duration", 0)), help="最小视频片段的时长（秒）。")
                    with col_p2:
                        config.app["pexels_min_height"] = st.number_input("最小高度 (min_height)", min_value=0, value=int(config.app.get("pexels_min_height", 0)), help="筛选画面高度（像素）。不填填 0 即可。")
                        config.app["pexels_max_duration"] = st.number_input("最大时长 (max_duration)", min_value=0, value=int(config.app.get("pexels_max_duration", 0)), help="最大视频片段的时长（秒）。")
                        
                    if config.app["pexels_max_duration"] > 0 and config.app["pexels_min_duration"] > config.app["pexels_max_duration"]:
                        st.error("⚠️ 最小时长不能大于最大时长，请修正。 (Min duration cannot exceed max duration)")
                else:
                    st.write("---")
                    st.write("搜索接口专属参数 (Search API)")
                    
                    pexels_orientation_opts = ["auto", "landscape", "portrait", "square"]
                    saved_orientation = config.app.get("pexels_orientation", "auto")
                    selected_ori = st.selectbox("强制画面方向", pexels_orientation_opts, index=pexels_orientation_opts.index(saved_orientation) if saved_orientation in pexels_orientation_opts else 0, help="强制指定 API 搜索的横竖比例，不选则跟随全局配置自动推断。")
                    config.app["pexels_orientation"] = selected_ori

                    pexels_size_options = ["auto", "small", "medium", "large"]
                    saved_size = config.app.get("pexels_size", "")
                    size_index = pexels_size_options.index(saved_size if saved_size else "auto")
                    selected_size = st.selectbox(
                        "尺寸要求",
                        options=pexels_size_options,
                        index=size_index,
                        help="可以指定仅搜索具有特定分辨率规模的视频（小、中、大）。"
                    )
                    config.app["pexels_size"] = "" if selected_size == "auto" else selected_size

                    config.app["pexels_locale"] = st.text_input(
                        "地区语言",
                        value=config.app.get("pexels_locale", ""),
                        help="特定语言地区的排序偏好，直接填入如 en-US, zh-CN, ja-JP 等标准识别码。",
                    ).strip()

        if params.video_source == "local":
            uploaded_files = st.file_uploader(
                "Upload Local Files",
                type=["mp4", "mov", "avi", "flv", "mkv", "jpg", "jpeg", "png"],
                accept_multiple_files=True,
            )

        selected_index = st.selectbox(
            tr("Video Concat Mode"),
            index=1,
            options=range(
                len(video_concat_modes)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_concat_modes[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_concat_mode = VideoConcatMode(
            video_concat_modes[selected_index][1]
        )

        # 视频转场模式
        video_transition_modes = [
            (tr("None"), VideoTransitionMode.none.value),
            (tr("Shuffle"), VideoTransitionMode.shuffle.value),
            (tr("FadeIn"), VideoTransitionMode.fade_in.value),
            (tr("FadeOut"), VideoTransitionMode.fade_out.value),
            (tr("SlideIn"), VideoTransitionMode.slide_in.value),
            (tr("SlideOut"), VideoTransitionMode.slide_out.value),
        ]
        selected_index = st.selectbox(
            tr("Video Transition Mode"),
            options=range(len(video_transition_modes)),
            format_func=lambda x: video_transition_modes[x][0],
            index=0,
        )
        params.video_transition_mode = VideoTransitionMode(
            video_transition_modes[selected_index][1]
        )

        saved_transition_duration = float(
            config.ui.get("video_transition_duration", params.video_transition_duration or 0.35)
        )
        saved_transition_duration = min(max(saved_transition_duration, 0.1), 1.5)
        params.video_transition_duration = st.slider(
            tr("Video Transition Duration"),
            min_value=0.1,
            max_value=1.5,
            value=saved_transition_duration,
            step=0.05,
            help=tr("Set transition smoothness in seconds"),
        )
        config.ui["video_transition_duration"] = params.video_transition_duration

        video_aspect_ratios = [
            (tr("Portrait"), VideoAspect.portrait.value),
            (tr("Landscape"), VideoAspect.landscape.value),
        ]
        selected_index = st.selectbox(
            tr("Video Ratio"),
            options=range(
                len(video_aspect_ratios)
            ),  # Use the index as the internal option value
            format_func=lambda x: video_aspect_ratios[x][
                0
            ],  # The label is displayed to the user
        )
        params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])

        params.video_clip_duration = st.selectbox(
            tr("Clip Duration"), options=[2, 3, 4, 5, 6, 7, 8, 9, 10], index=1
        )
        params.video_count = st.selectbox(
            tr("Number of Videos Generated Simultaneously"),
            options=[1, 2, 3, 4, 5, 10, 20, 30, 40, 50, 100],
            index=0,
        )
        saved_materials_download_count = int(config.ui.get("materials_download_count", 20) or 20)
        saved_materials_download_count = max(1, min(saved_materials_download_count, 500))
        selected_materials_download_count = int(
            st.number_input(
                tr("Materials Download Count"),
                min_value=1,
                max_value=500,
                value=saved_materials_download_count,
                step=1,
                help=tr("Used by Download Materials Only mode"),
            )
        )
        config.ui["materials_download_count"] = selected_materials_download_count
        try:
            params.materials_download_count = selected_materials_download_count
        except ValueError:
            # Backward compatibility: old schema without this field.
            logger.warning("VideoParams has no field 'materials_download_count', using config.ui value as fallback")

with right_panel:
    with st.container(border=True):
        st.write(tr("Audio Settings"))

        # 添加TTS服务器选择下拉框
        tts_servers = [
            ("siliconflow", "SiliconFlow TTS"),
            ("local-cosyvoice", "Local CosyVoice"),
        ]

        # 获取保存的TTS服务器，默认为 siliconflow
        saved_tts_server = config.ui.get("tts_server", "siliconflow")
        if saved_tts_server not in [s[0] for s in tts_servers]:
            saved_tts_server = "siliconflow"
        saved_tts_server_index = 0
        for i, (server_value, _) in enumerate(tts_servers):
            if server_value == saved_tts_server:
                saved_tts_server_index = i
                break

        selected_tts_server_index = st.selectbox(
            tr("TTS Servers"),
            options=range(len(tts_servers)),
            format_func=lambda x: tts_servers[x][1],
            index=saved_tts_server_index,
        )

        selected_tts_server = tts_servers[selected_tts_server_index][0]
        config.ui["tts_server"] = selected_tts_server

        # 根据选择的TTS服务器获取声音列表
        filtered_voices = []

        if selected_tts_server == "siliconflow":
            # 获取硅基流动的声音列表
            filtered_voices = voice.get_siliconflow_voices()
        elif selected_tts_server == "gemini-tts":
            # 获取Gemini TTS的声音列表
            filtered_voices = voice.get_gemini_voices()
        elif selected_tts_server == "local-cosyvoice":
            filtered_voices = voice.get_local_cosyvoice_voices()
        else:
            # 获取Azure的声音列表
            all_voices = voice.get_all_azure_voices(filter_locals=None)

            # 根据选择的TTS服务器筛选声音
            for v in all_voices:
                if selected_tts_server == "azure-tts-v2":
                    # V2版本的声音名称中包含"v2"
                    if "V2" in v:
                        filtered_voices.append(v)
                else:
                    # V1版本的声音名称中不包含"v2"
                    if "V2" not in v:
                        filtered_voices.append(v)

        friendly_names = {}
        for v in filtered_voices:
            if voice.is_local_cosyvoice_voice(v):
                friendly_names[v] = v.split(":", 1)[1]
            else:
                friendly_names[v] = (
                    v.replace("Female", tr("Female"))
                    .replace("Male", tr("Male"))
                    .replace("Neural", "")
                )

        saved_voice_name = config.ui.get("voice_name", "")
        saved_voice_name_index = 0

        # 检查保存的声音是否在当前筛选的声音列表中
        if saved_voice_name in friendly_names:
            saved_voice_name_index = list(friendly_names.keys()).index(saved_voice_name)
        else:
            # 如果不在，则根据当前UI语言选择一个默认声音
            for i, v in enumerate(filtered_voices):
                if v.lower().startswith(st.session_state["ui_language"].lower()):
                    saved_voice_name_index = i
                    break

        # 如果没有找到匹配的声音，使用第一个声音
        if saved_voice_name_index >= len(friendly_names) and friendly_names:
            saved_voice_name_index = 0

        # 确保有声音可选
        if friendly_names:
            selected_friendly_name = st.selectbox(
                tr("Speech Synthesis"),
                options=list(friendly_names.values()),
                index=min(saved_voice_name_index, len(friendly_names) - 1)
                if friendly_names
                else 0,
            )

            voice_name = list(friendly_names.keys())[
                list(friendly_names.values()).index(selected_friendly_name)
            ]
            params.voice_name = voice_name
            config.ui["voice_name"] = voice_name
        else:
            # 如果没有声音可选，显示提示信息
            st.warning(
                tr(
                    "No voices available for the selected TTS server. Please select another server."
                )
            )
            voice_name = ""
            params.voice_name = ""
            config.ui["voice_name"] = ""

        # 只有在有声音可选时才显示试听按钮
        if friendly_names and st.button(tr("Play Voice")):
            play_content = params.video_subject
            if not play_content:
                play_content = params.video_script
            if not play_content:
                play_content = tr("Voice Example")
            with st.spinner(tr("Synthesizing Voice")):
                temp_dir = utils.storage_dir("temp", create=True)
                audio_ext = voice.get_audio_extension(voice_name)
                audio_file = os.path.join(temp_dir, f"tmp-voice-{str(uuid4())}{audio_ext}")
                sub_maker = voice.tts(
                    text=play_content,
                    voice_name=voice_name,
                    voice_rate=params.voice_rate,
                    voice_file=audio_file,
                    voice_volume=params.voice_volume,
                )
                # if the voice file generation failed, try again with a default content.
                if not sub_maker:
                    play_content = "This is a example voice. if you hear this, the voice synthesis failed with the original content."
                    sub_maker = voice.tts(
                        text=play_content,
                        voice_name=voice_name,
                        voice_rate=params.voice_rate,
                        voice_file=audio_file,
                        voice_volume=params.voice_volume,
                    )

                if sub_maker and os.path.exists(audio_file):
                    audio_format = "audio/wav" if audio_file.endswith(".wav") else "audio/mp3"
                    st.audio(audio_file, format=audio_format)
                    if os.path.exists(audio_file):
                        os.remove(audio_file)

        if selected_tts_server == "local-cosyvoice" or (
            voice_name and voice.is_local_cosyvoice_voice(voice_name)
        ):
            saved_local_tts_base_url = config.local_tts.get(
                "base_url", "http://127.0.0.1:9880"
            )
            local_tts_base_url = st.text_input(
                tr("Local TTS Base URL"),
                value=saved_local_tts_base_url,
                key="local_tts_base_url_input",
            )
            config.local_tts["base_url"] = local_tts_base_url.strip()

            if filtered_voices:
                st.success(
                    tr("Local TTS service is reachable") + f": {len(filtered_voices)}"
                )
            else:
                st.warning(
                    tr("Local TTS service is unavailable or returned no voices")
                )

        # 当选择V2版本或者声音是V2声音时，显示服务区域和API key输入框
        if selected_tts_server == "azure-tts-v2" or (
            voice_name and voice.is_azure_v2_voice(voice_name)
        ):
            saved_azure_speech_region = config.azure.get("speech_region", "")
            saved_azure_speech_key = config.azure.get("speech_key", "")
            azure_speech_region = st.text_input(
                tr("Speech Region"),
                value=saved_azure_speech_region,
                key="azure_speech_region_input",
            )
            azure_speech_key = st.text_input(
                tr("Speech Key"),
                value=saved_azure_speech_key,
                type="password",
                key="azure_speech_key_input",
            )
            config.azure["speech_region"] = azure_speech_region
            config.azure["speech_key"] = azure_speech_key

        # 当选择硅基流动时，显示API key输入框和说明信息
        if selected_tts_server == "siliconflow" or (
            voice_name and voice.is_siliconflow_voice(voice_name)
        ):
            saved_siliconflow_api_key = config.siliconflow.get("api_key", "")

            siliconflow_api_key = st.text_input(
                tr("SiliconFlow API Key"),
                value=saved_siliconflow_api_key,
                type="password",
                key="siliconflow_api_key_input",
            )

            # 显示硅基流动的说明信息
            st.info(
                tr("SiliconFlow TTS Settings")
                + ":\n"
                + "- "
                + tr("Speed: Range [0.25, 4.0], default is 1.0")
                + "\n"
                + "- "
                + tr("Volume: Uses Speech Volume setting, default 1.0 maps to gain 0")
            )

            config.siliconflow["api_key"] = siliconflow_api_key

        params.voice_volume = st.selectbox(
            tr("Speech Volume"),
            options=[0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0],
            index=2,
        )

        params.voice_rate = st.selectbox(
            tr("Speech Rate"),
            options=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0],
            index=2,
        )

        bgm_options = [
            (tr("No Background Music"), ""),
            (tr("Random Background Music"), "random"),
            (tr("Custom Background Music"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Background Music"),
            index=1,
            options=range(
                len(bgm_options)
            ),  # Use the index as the internal option value
            format_func=lambda x: bgm_options[x][
                0
            ],  # The label is displayed to the user
        )
        # Get the selected background music type
        params.bgm_type = bgm_options[selected_index][1]

        # Show or hide components based on the selection
        if params.bgm_type == "custom":
            custom_bgm_file = st.text_input(
                tr("Custom Background Music File"), key="custom_bgm_file_input"
            )
            if custom_bgm_file and os.path.exists(custom_bgm_file):
                params.bgm_file = custom_bgm_file
                # st.write(f":red[已选择自定义背景音乐]：**{custom_bgm_file}**")
        params.bgm_volume = st.selectbox(
            tr("Background Music Volume"),
            options=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            index=2,
        )

    with st.container(border=True):
        st.write(tr("Subtitle Settings"))
        params.subtitle_enabled = st.checkbox(tr("Enable Subtitles"), value=True)
        font_names = get_all_fonts()
        saved_font_name = config.ui.get("font_name", "MicrosoftYaHeiBold.ttc")
        saved_font_name_index = 0
        if saved_font_name in font_names:
            saved_font_name_index = font_names.index(saved_font_name)
        params.font_name = st.selectbox(
            tr("Font"), font_names, index=saved_font_name_index
        )
        config.ui["font_name"] = params.font_name

        subtitle_positions = [
            (tr("Top"), "top"),
            (tr("Center"), "center"),
            (tr("Bottom"), "bottom"),
            (tr("Custom"), "custom"),
        ]
        selected_index = st.selectbox(
            tr("Position"),
            index=2,
            options=range(len(subtitle_positions)),
            format_func=lambda x: subtitle_positions[x][0],
        )
        params.subtitle_position = subtitle_positions[selected_index][1]

        if params.subtitle_position == "custom":
            custom_position = st.text_input(
                tr("Custom Position (% from top)"),
                value="70.0",
                key="custom_position_input",
            )
            try:
                params.custom_position = float(custom_position)
                if params.custom_position < 0 or params.custom_position > 100:
                    st.error(tr("Please enter a value between 0 and 100"))
            except ValueError:
                st.error(tr("Please enter a valid number"))


        if True:
            saved_text_fore_color = config.ui.get("text_fore_color", "#FFFFFF")
            params.text_fore_color = st.color_picker(
                tr("Font Color"), saved_text_fore_color
            )
            config.ui["text_fore_color"] = params.text_fore_color

        if True:
            saved_font_size = config.ui.get("font_size", 60)
            params.font_size = st.slider(tr("Font Size"), 30, 100, saved_font_size)
            config.ui["font_size"] = params.font_size


        if True:
            params.stroke_color = st.color_picker(tr("Stroke Color"), "#000000")
        if True:
            params.stroke_width = st.slider(tr("Stroke Width"), 0.0, 10.0, 1.5)

profile_metrics = st.columns(4)
profile_metrics[0].metric("Source", str(params.video_source).upper())
profile_metrics[1].metric("Aspect", str(params.video_aspect))
profile_metrics[2].metric("Clip(s)", str(params.video_count))
profile_metrics[3].metric("TTS", str(config.ui.get("tts_server", "-")).upper())

action_cols = st.columns(2)
start_button = action_cols[0].button(
    tr("Generate Video"), use_container_width=True, type="primary"
)
download_only_button = action_cols[1].button(
    tr("Download Materials Only"), use_container_width=True
)

if start_button or download_only_button:
    config.save_config()
    task_id = str(uuid4())
    run_mode = "materials" if download_only_button else "video"
    if not params.video_subject and not params.video_script:
        st.error(tr("Video Script and Subject Cannot Both Be Empty"))
        scroll_to_bottom()
        st.stop()

    if params.video_source not in ["pexels", "pixabay", "local"]:
        st.error(tr("Please Select a Valid Video Source"))
        scroll_to_bottom()
        st.stop()

    if params.video_source == "pexels" and not config.app.get("pexels_api_keys", ""):
        st.error(tr("Please Enter the Pexels API Key"))
        scroll_to_bottom()
        st.stop()

    if params.video_source == "pixabay" and not config.app.get("pixabay_api_keys", ""):
        st.error(tr("Please Enter the Pixabay API Key"))
        scroll_to_bottom()
        st.stop()

    if uploaded_files:
        local_videos_dir = utils.storage_dir("local_videos", create=True)
        for file in uploaded_files:
            file_path = os.path.join(local_videos_dir, f"{file.file_id}_{file.name}")
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())
                m = MaterialInfo()
                m.provider = "local"
                m.url = file_path
                if not params.video_materials:
                    params.video_materials = []
                params.video_materials.append(m)

    log_container = st.empty()
    log_records = []

    def log_received(msg):
        if config.ui["hide_log"]:
            return
        # Streamlit UI updates must run on the main script thread.
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            with log_container:
                log_records.append(msg)
                st.code("\n".join(log_records))
        except Exception:
            # Ignore transient context teardown errors when rerunning/stopping.
            return

    logger.add(log_received)

    if run_mode == "materials":
        st.toast(tr("Downloading Materials"))
        logger.info(tr("Start Downloading Materials"))
    else:
        st.toast(tr("Generating Video"))
        logger.info(tr("Start Generating Video"))
    logger.info(utils.to_json(params))
    scroll_to_bottom()

    result = tm.start(task_id=task_id, params=params, stop_at=run_mode)

    if run_mode == "materials":
        material_files = result.get("materials", []) if result else []
        archive_dir = result.get("materials_archive_dir", "") if result else ""
        if not material_files:
            st.error(tr("Material Download Failed"))
            logger.error(tr("Material Download Failed"))
            scroll_to_bottom()
            st.stop()

        st.success(tr("Material Download Completed"))
        if archive_dir:
            st.info(f"{tr('Archive Directory')}: {archive_dir}")
        with st.expander(tr("Downloaded Materials"), expanded=True):
            for item in material_files:
                st.write(item)

        open_task_folder(task_id)
        logger.info(tr("Material Download Completed"))
        scroll_to_bottom()
        st.stop()

    if not result or "videos" not in result:
        st.error(tr("Video Generation Failed"))
        logger.error(tr("Video Generation Failed"))
        scroll_to_bottom()
        st.stop()

    video_files = result.get("videos", [])
    st.success(tr("Video Generation Completed"))
    try:
        if video_files:
            player_cols = st.columns(len(video_files) * 2 + 1)
            for i, url in enumerate(video_files):
                player_cols[i * 2 + 1].video(url)
    except Exception:
        pass

    open_task_folder(task_id)
    logger.info(tr("Video Generation Completed"))
    scroll_to_bottom()

config.save_config()
