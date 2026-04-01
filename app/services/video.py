import glob
import os
import random
import gc
import hashlib
import re
import shutil
import platform
import subprocess
from functools import lru_cache
from typing import Any, Dict, List
from loguru import logger
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import ImageFont

from app.models import const
from app.config import config
from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services.utils import video_effects
from app.utils import utils

class SubClippedVideoClip:
    def __init__(self, file_path, start_time=None, end_time=None, width=None, height=None, duration=None, tags=None, group=""):
        self.file_path = file_path
        self.start_time = start_time
        self.end_time = end_time
        self.width = width
        self.height = height
        self.tags = tags or []
        self.group = group
        if duration is None:
            self.duration = end_time - start_time
        else:
            self.duration = duration

    def __str__(self):
        return f"SubClippedVideoClip(file_path={self.file_path}, start_time={self.start_time}, end_time={self.end_time}, duration={self.duration}, width={self.width}, height={self.height})"


audio_codec = "aac"
video_codec = "libx264"
fps = 30


def _ffmpeg_bin() -> str:
    return os.environ.get("IMAGEIO_FFMPEG_EXE", "ffmpeg")


@lru_cache(maxsize=1)
def _ffmpeg_encoders_text() -> str:
    try:
        result = subprocess.run(
            [_ffmpeg_bin(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = f"{result.stdout}\n{result.stderr}".lower()
        return output
    except Exception as e:
        logger.warning(f"failed to probe ffmpeg encoders: {str(e)}")
        return ""


def _has_encoder(encoder_name: str) -> bool:
    return encoder_name.lower() in _ffmpeg_encoders_text()


@lru_cache(maxsize=1)
def _resolve_video_encoder() -> tuple[str, List[str]]:
    accel_mode = str(config.app.get("video_hardware_accel", "auto")).strip().lower()
    preferred_encoder = str(config.app.get("video_encoder", "auto")).strip().lower()
    logger.info(
        f"video encoder policy => accel_mode={accel_mode}, preferred_encoder={preferred_encoder or 'auto'}, ffmpeg={_ffmpeg_bin()}"
    )

    if accel_mode in {"off", "cpu", "none"}:
        logger.info("video hardware acceleration disabled, using libx264")
        return video_codec, []

    if preferred_encoder not in {"", "auto"}:
        if _has_encoder(preferred_encoder):
            logger.info(f"using configured video encoder: {preferred_encoder}")
            return preferred_encoder, []
        logger.warning(f"configured encoder not available: {preferred_encoder}, fallback to auto detection")

    # Best-effort order: Nvidia -> Apple -> Intel -> AMD -> CPU.
    candidates = [
        ("h264_nvenc", ["-preset", "p4", "-rc", "vbr", "-cq", "23"]),
        ("h264_videotoolbox", []),
        ("h264_qsv", []),
        ("h264_amf", []),
    ]

    # Platform-aware preference for safer defaults.
    system_name = platform.system().lower()
    if system_name == "darwin":
        candidates = [
            ("h264_videotoolbox", []),
            ("h264_nvenc", ["-preset", "p4", "-rc", "vbr", "-cq", "23"]),
            ("h264_qsv", []),
            ("h264_amf", []),
        ]

    vendor_filtered = {
        "nvidia": [candidates[0]],
        "apple": [next((c for c in candidates if c[0] == "h264_videotoolbox"), candidates[0])],
        "intel": [next((c for c in candidates if c[0] == "h264_qsv"), candidates[0])],
        "amd": [next((c for c in candidates if c[0] == "h264_amf"), candidates[0])],
    }
    if accel_mode in vendor_filtered:
        candidates = vendor_filtered[accel_mode]

    for encoder, params in candidates:
        if _has_encoder(encoder):
            logger.info(f"using hardware encoder: {encoder}")
            return encoder, params

    logger.warning("no supported hardware encoder found, fallback to libx264")
    return video_codec, []


def _write_videofile_with_fallback(
    clip,
    output_file: str,
    include_audio: bool,
    threads: int = 2,
    temp_audiofile_path: str = "",
    local_fps: int = fps,
    stage: str = "video_export",
):
    codec, ffmpeg_params = _resolve_video_encoder()
    logger.info(
        f"[{stage}] export start => codec={codec}, audio={'on' if include_audio else 'off'}, fps={local_fps}, threads={threads}, output={output_file}"
    )
    write_kwargs = {
        "logger": None,
        "fps": local_fps,
        "codec": codec,
    }
    if threads:
        write_kwargs["threads"] = threads
    if include_audio:
        write_kwargs["audio_codec"] = audio_codec
    if temp_audiofile_path:
        write_kwargs["temp_audiofile_path"] = temp_audiofile_path
    if ffmpeg_params:
        write_kwargs["ffmpeg_params"] = ffmpeg_params

    try:
        clip.write_videofile(output_file, **write_kwargs)
        logger.info(f"[{stage}] export done => codec={codec}")
    except Exception as e:
        if codec == video_codec:
            logger.error(f"[{stage}] export failed with cpu codec {video_codec}: {str(e)}")
            raise
        logger.warning(
            f"[{stage}] hardware encoding failed ({codec}), fallback to {video_codec}: {str(e)}"
        )
        write_kwargs["codec"] = video_codec
        write_kwargs.pop("ffmpeg_params", None)
        clip.write_videofile(output_file, **write_kwargs)
        logger.info(f"[{stage}] export done after fallback => codec={video_codec}")

def close_clip(clip):
    if clip is None:
        return
        
    try:
        # close main resources
        if hasattr(clip, 'reader') and clip.reader is not None:
            clip.reader.close()
            
        # close audio resources
        if hasattr(clip, 'audio') and clip.audio is not None:
            if hasattr(clip.audio, 'reader') and clip.audio.reader is not None:
                clip.audio.reader.close()
            del clip.audio
            
        # close mask resources
        if hasattr(clip, 'mask') and clip.mask is not None:
            if hasattr(clip.mask, 'reader') and clip.mask.reader is not None:
                clip.mask.reader.close()
            del clip.mask
            
        # handle child clips in composite clips
        if hasattr(clip, 'clips') and clip.clips:
            for child_clip in clip.clips:
                if child_clip is not clip:  # avoid possible circular references
                    close_clip(child_clip)
            
        # clear clip list
        if hasattr(clip, 'clips'):
            clip.clips = []
            
    except Exception as e:
        logger.error(f"failed to close clip: {str(e)}")
    
    del clip
    gc.collect()

def delete_files(files: List[str] | str):
    if isinstance(files, str):
        files = [files]
        
    for file in files:
        try:
            os.remove(file)
        except:
            pass

def get_bgm_file(bgm_type: str = "random", bgm_file: str = ""):
    if not bgm_type:
        return ""

    if bgm_file and os.path.exists(bgm_file):
        return bgm_file

    if bgm_type == "random":
        suffix = "*.mp3"
        song_dir = utils.song_dir()
        files = glob.glob(os.path.join(song_dir, suffix))
        return random.choice(files)

    return ""


def _deterministic_rng(seed_text: str) -> random.Random:
    digest = hashlib.md5(seed_text.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _rotate_items(items: List, offset: int):
    if not items:
        return items
    offset = offset % len(items)
    if offset == 0:
        return items
    return items[offset:] + items[:offset]


def _normalize_tags(tags) -> List[str]:
    if not tags:
        return []
    if isinstance(tags, str):
        source = re.split(r"[,，\s]+", tags)
    elif isinstance(tags, list):
        source = tags
    else:
        return []

    normalized = []
    for tag in source:
        text = str(tag).strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _tokenize_text(text: str) -> List[str]:
    if not text:
        return []
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())
    return [token for token in tokens if token]


def _split_script_segments(text: str) -> List[str]:
    if not text:
        return []
    segments = re.split(r"[。！？!?；;，,\n\r]+", text)
    return [segment.strip() for segment in segments if segment.strip()]


def _infer_tags_from_filename(file_path: str) -> List[str]:
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    rough = re.split(r"[\s,_\-]+", file_name)
    return [token.lower() for token in rough if token and len(token) > 1 and not token.isdigit()]


def _infer_group_from_filename(file_path: str) -> str:
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    if "__" in file_name:
        return file_name.split("__", 1)[0].strip().lower()
    if "-" in file_name:
        return file_name.split("-", 1)[0].strip().lower()
    return file_name.strip().lower()


def _resolve_material_meta(file_path: str, material_catalog: Dict[str, Dict[str, Any]]):
    metadata = material_catalog.get(file_path, {}) if material_catalog else {}
    tags = _normalize_tags(metadata.get("tags"))
    if not tags:
        tags = _infer_tags_from_filename(file_path)

    group = str(metadata.get("group") or "").strip().lower()
    if not group:
        group = _infer_group_from_filename(file_path)

    return {"tags": tags, "group": group}


def _order_subclips_by_script(
    subclipped_items: List[SubClippedVideoClip],
    script_text: str,
    rng: random.Random,
    sequence_index: int,
) -> List[SubClippedVideoClip]:
    segments = _split_script_segments(script_text)
    if not segments:
        rng.shuffle(subclipped_items)
        return _rotate_items(subclipped_items, sequence_index)

    remain = list(subclipped_items)
    ordered = []
    for segment in segments:
        segment_tokens = set(_tokenize_text(segment))
        if not segment_tokens:
            continue

        best_idx = -1
        best_score = 0
        candidate_indexes = list(range(len(remain)))
        rng.shuffle(candidate_indexes)

        for idx in candidate_indexes:
            clip_tags = set(remain[idx].tags or [])
            score = len(segment_tokens.intersection(clip_tags))
            if score > best_score:
                best_idx = idx
                best_score = score

        if best_idx >= 0 and best_score > 0:
            ordered.append(remain.pop(best_idx))

    rng.shuffle(remain)
    ordered.extend(remain)
    return _rotate_items(ordered, sequence_index)


def _spread_duplicate_neighbors(
    items: List[SubClippedVideoClip], rng: random.Random
) -> List[SubClippedVideoClip]:
    if len(items) <= 2:
        return items

    arranged = list(items)
    for i in range(1, len(arranged)):
        prev = arranged[i - 1]
        cur = arranged[i]
        same_source = cur.file_path == prev.file_path
        same_group = bool(cur.group and prev.group and cur.group == prev.group)
        if not same_source and not same_group:
            continue

        swap_idx = -1
        candidate_indexes = list(range(i + 1, len(arranged)))
        rng.shuffle(candidate_indexes)
        for j in candidate_indexes:
            candidate = arranged[j]
            cand_same_source = candidate.file_path == prev.file_path
            cand_same_group = bool(candidate.group and prev.group and candidate.group == prev.group)
            if not cand_same_source and not cand_same_group:
                swap_idx = j
                break

        if swap_idx > 0:
            arranged[i], arranged[swap_idx] = arranged[swap_idx], arranged[i]

    return arranged


def _segment_key(item: SubClippedVideoClip) -> str:
    # Normalize to milliseconds to avoid float precision causing accidental duplicates.
    start_ms = int(round((item.start_time or 0) * 1000))
    end_ms = int(round((item.end_time or 0) * 1000))
    return f"{item.file_path}|{start_ms}|{end_ms}"


def combine_videos(
    combined_video_path: str,
    video_paths: List[str],
    audio_file: str,
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_concat_mode: VideoConcatMode = VideoConcatMode.random,
    video_transition_mode: VideoTransitionMode = None,
    max_clip_duration: int = 5,
    threads: int = 2,
    sequence_seed: str = "",
    sequence_index: int = 0,
    transition_duration: float = 0.35,
    material_catalog: Dict[str, Dict[str, Any]] = None,
    script_text: str = "",
) -> str:
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    logger.info(f"audio duration: {audio_duration} seconds")
    # Required duration of each clip
    req_dur = audio_duration / len(video_paths)
    req_dur = max_clip_duration
    logger.info(f"maximum clip duration: {req_dur} seconds")
    output_dir = os.path.dirname(combined_video_path)

    aspect = VideoAspect(video_aspect)
    video_width, video_height = aspect.to_resolution()

    processed_clips = []
    subclipped_items = []
    video_duration = 0
    seed = sequence_seed or os.path.basename(combined_video_path)
    rng = _deterministic_rng(seed)
    resolved_transition_mode = video_transition_mode or VideoTransitionMode.shuffle

    for video_path in video_paths:
        metadata = _resolve_material_meta(video_path, material_catalog or {})
        clip = VideoFileClip(video_path)
        clip_duration = clip.duration
        clip_w, clip_h = clip.size
        close_clip(clip)
        
        start_time = 0

        while start_time < clip_duration:
            end_time = min(start_time + max_clip_duration, clip_duration)            
            if clip_duration - start_time >= max_clip_duration:
                subclipped_items.append(SubClippedVideoClip(file_path= video_path, start_time=start_time, end_time=end_time, width=clip_w, height=clip_h, tags=metadata["tags"], group=metadata["group"]))
            start_time = end_time    
            if video_concat_mode.value == VideoConcatMode.sequential.value:
                break

    # random subclipped_items order
    if video_concat_mode.value == VideoConcatMode.random.value:
        clips_per_video = max(1, int((audio_duration + max_clip_duration - 1) // max_clip_duration))
        rotation_offset = sequence_index * clips_per_video
        has_any_tags = any(item.tags for item in subclipped_items)
        if script_text and has_any_tags:
            subclipped_items = _order_subclips_by_script(
                subclipped_items=subclipped_items,
                script_text=script_text,
                rng=rng,
                sequence_index=0,
            )
        else:
            rng.shuffle(subclipped_items)

        subclipped_items = _spread_duplicate_neighbors(subclipped_items, rng)
        subclipped_items = _rotate_items(subclipped_items, rotation_offset)

        # Log source diversity preview for troubleshooting repeated-content issues.
        preview_count = min(8, len(subclipped_items))
        source_preview = [
            f"{os.path.basename(item.file_path)}@{int(item.start_time)}-{int(item.end_time)}"
            for item in subclipped_items[:preview_count]
        ]
        logger.info(
            f"random order prepared => clips_per_video={clips_per_video}, rotation_offset={rotation_offset}, preview={source_preview}"
        )
        
    logger.debug(f"total subclipped items: {len(subclipped_items)}")
    
    # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
    used_segment_keys = set()
    for i, subclipped_item in enumerate(subclipped_items):
        if video_duration > audio_duration:
            break

        seg_key = _segment_key(subclipped_item)
        if seg_key in used_segment_keys:
            logger.debug(f"skip duplicated segment in same video: {seg_key}")
            continue
        
        logger.debug(f"processing clip {i+1}: {subclipped_item.width}x{subclipped_item.height}, current duration: {video_duration:.2f}s, remaining: {audio_duration - video_duration:.2f}s")
        
        try:
            clip = VideoFileClip(subclipped_item.file_path).subclipped(subclipped_item.start_time, subclipped_item.end_time)
            clip_duration = clip.duration
            # Not all videos are same size, so we need to resize them
            clip_w, clip_h = clip.size
            if clip_w != video_width or clip_h != video_height:
                clip_ratio = clip.w / clip.h
                video_ratio = video_width / video_height
                logger.debug(f"resizing clip, source: {clip_w}x{clip_h}, ratio: {clip_ratio:.2f}, target: {video_width}x{video_height}, ratio: {video_ratio:.2f}")
                
                if clip_ratio == video_ratio:
                    clip = clip.resized(new_size=(video_width, video_height))
                else:
                    if clip_ratio > video_ratio:
                        scale_factor = video_width / clip_w
                    else:
                        scale_factor = video_height / clip_h

                    new_width = int(clip_w * scale_factor)
                    new_height = int(clip_h * scale_factor)

                    background = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(clip_duration)
                    clip_resized = clip.resized(new_size=(new_width, new_height)).with_position("center")
                    clip = CompositeVideoClip([background, clip_resized])
                    
            shuffle_side = rng.choice(["left", "right", "top", "bottom"])
            transition_t = min(max(0.15, transition_duration), max(0.15, clip.duration / 3))
            if resolved_transition_mode.value == VideoTransitionMode.none.value:
                clip = clip
            elif resolved_transition_mode.value == VideoTransitionMode.fade_in.value:
                clip = video_effects.fadein_transition(clip, transition_t)
                clip = video_effects.fadeout_transition(clip, transition_t)
            elif resolved_transition_mode.value == VideoTransitionMode.fade_out.value:
                clip = video_effects.fadeout_transition(clip, transition_t)
                clip = video_effects.fadein_transition(clip, transition_t)
            elif resolved_transition_mode.value == VideoTransitionMode.slide_in.value:
                clip = video_effects.slidein_transition(clip, transition_t, shuffle_side)
                clip = video_effects.fadeout_transition(clip, transition_t)
            elif resolved_transition_mode.value == VideoTransitionMode.slide_out.value:
                clip = video_effects.slideout_transition(clip, transition_t, shuffle_side)
                clip = video_effects.fadein_transition(clip, transition_t)
            elif resolved_transition_mode.value == VideoTransitionMode.shuffle.value:
                transition_funcs = [
                    lambda c: video_effects.fadein_transition(c, transition_t),
                    lambda c: video_effects.fadeout_transition(c, transition_t),
                    lambda c: video_effects.slidein_transition(c, transition_t, shuffle_side),
                    lambda c: video_effects.slideout_transition(c, transition_t, shuffle_side),
                ]
                shuffle_transition = rng.choice(transition_funcs)
                clip = shuffle_transition(clip)

            if clip.duration > max_clip_duration:
                clip = clip.subclipped(0, max_clip_duration)
                
            # wirte clip to temp file
            clip_file = f"{output_dir}/temp-clip-{i+1}.mp4"
            _write_videofile_with_fallback(
                clip=clip,
                output_file=clip_file,
                include_audio=False,
                threads=threads,
                local_fps=fps,
                stage="temp_clip",
            )
            
            close_clip(clip)
        
            processed_clips.append(SubClippedVideoClip(file_path=clip_file, duration=clip.duration, width=clip_w, height=clip_h))
            video_duration += clip.duration
            used_segment_keys.add(seg_key)
            
        except Exception as e:
            logger.error(f"failed to process clip: {str(e)}")
    
    # Keep segments unique inside one composed video. Do not loop previous clips.
    if video_duration < audio_duration:
        logger.warning(
            f"video duration ({video_duration:.2f}s) is shorter than audio duration ({audio_duration:.2f}s). "
            "strict unique-segment mode keeps clips non-repeating within one video."
        )

    logger.info(
        f"unique segment summary => used={len(used_segment_keys)}, total_candidates={len(subclipped_items)}"
    )
     
    # merge video clips progressively, avoid loading all videos at once to avoid memory overflow
    logger.info("starting clip merging process")
    if not processed_clips:
        logger.warning("no clips available for merging")
        return combined_video_path
    
    # if there is only one clip, use it directly
    if len(processed_clips) == 1:
        logger.info("using single clip directly")
        shutil.copy(processed_clips[0].file_path, combined_video_path)
        delete_files(processed_clips)
        logger.info("video combining completed")
        return combined_video_path
    
    # create initial video file as base
    base_clip_path = processed_clips[0].file_path
    temp_merged_video = f"{output_dir}/temp-merged-video.mp4"
    temp_merged_next = f"{output_dir}/temp-merged-next.mp4"
    
    # copy first clip as initial merged video
    shutil.copy(base_clip_path, temp_merged_video)
    
    # merge remaining video clips one by one
    for i, clip in enumerate(processed_clips[1:], 1):
        logger.info(f"merging clip {i}/{len(processed_clips)-1}, duration: {clip.duration:.2f}s")
        
        try:
            # load current base video and next clip to merge
            base_clip = VideoFileClip(temp_merged_video)
            next_clip = VideoFileClip(clip.file_path)
            
            # merge these two clips
            merged_clip = concatenate_videoclips([base_clip, next_clip])

            # save merged result to temp file
            _write_videofile_with_fallback(
                clip=merged_clip,
                output_file=temp_merged_next,
                include_audio=True,
                threads=threads,
                temp_audiofile_path=output_dir,
                local_fps=fps,
                stage="merge_clip",
            )
            close_clip(base_clip)
            close_clip(next_clip)
            close_clip(merged_clip)
            
            # replace base file with new merged file
            delete_files(temp_merged_video)
            os.rename(temp_merged_next, temp_merged_video)
            
        except Exception as e:
            logger.error(f"failed to merge clip: {str(e)}")
            continue
    
    # after merging, rename final result to target file name
    os.rename(temp_merged_video, combined_video_path)
    
    # clean temp files
    clip_files = [clip.file_path for clip in processed_clips]
    delete_files(clip_files)
            
    logger.info("video combining completed")
    return combined_video_path


def wrap_text(text, max_width, font="Arial", fontsize=60):
    # Create ImageFont
    font = ImageFont.truetype(font, fontsize)

    def get_text_size(inner_text):
        inner_text = inner_text.strip()
        left, top, right, bottom = font.getbbox(inner_text)
        return right - left, bottom - top

    width, height = get_text_size(text)
    if width <= max_width:
        return text, height

    processed = True

    _wrapped_lines_ = []
    words = text.split(" ")
    _txt_ = ""
    for word in words:
        _before = _txt_
        _txt_ += f"{word} "
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            if _txt_.strip() == word.strip():
                processed = False
                break
            _wrapped_lines_.append(_before)
            _txt_ = f"{word} "
    _wrapped_lines_.append(_txt_)
    if processed:
        _wrapped_lines_ = [line.strip() for line in _wrapped_lines_]
        result = "\n".join(_wrapped_lines_).strip()
        height = len(_wrapped_lines_) * height
        return result, height

    _wrapped_lines_ = []
    chars = list(text)
    _txt_ = ""
    for word in chars:
        _txt_ += word
        _width, _height = get_text_size(_txt_)
        if _width <= max_width:
            continue
        else:
            _wrapped_lines_.append(_txt_)
            _txt_ = ""
    _wrapped_lines_.append(_txt_)
    result = "\n".join(_wrapped_lines_).strip()
    height = len(_wrapped_lines_) * height
    return result, height


def generate_video(
    video_path: str,
    audio_path: str,
    subtitle_path: str,
    output_file: str,
    params: VideoParams,
):
    aspect = VideoAspect(params.video_aspect)
    video_width, video_height = aspect.to_resolution()

    logger.info(f"generating video: {video_width} x {video_height}")
    logger.info(f"  ① video: {video_path}")
    logger.info(f"  ② audio: {audio_path}")
    logger.info(f"  ③ subtitle: {subtitle_path}")
    logger.info(f"  ④ output: {output_file}")

    # https://github.com/zkxxkz2/video-map/issues/217
    # PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'final-1.mp4.tempTEMP_MPY_wvf_snd.mp3'
    # write into the same directory as the output file
    output_dir = os.path.dirname(output_file)

    font_path = ""
    if params.subtitle_enabled:
        if not params.font_name:
            params.font_name = "STHeitiMedium.ttc"
        font_path = os.path.join(utils.font_dir(), params.font_name)
        if os.name == "nt":
            font_path = font_path.replace("\\", "/")

        logger.info(f"  ⑤ font: {font_path}")

    def create_text_clip(subtitle_item):
        params.font_size = int(params.font_size)
        params.stroke_width = int(params.stroke_width)
        phrase = subtitle_item[1]
        max_width = video_width * 0.9
        wrapped_txt, txt_height = wrap_text(
            phrase, max_width=max_width, font=font_path, fontsize=params.font_size
        )
        interline = int(params.font_size * 0.25)
        size=(int(max_width), int(txt_height + params.font_size * 0.25 + (interline * (wrapped_txt.count("\n") + 1))))

        _clip = TextClip(
            text=wrapped_txt,
            font=font_path,
            font_size=params.font_size,
            color=params.text_fore_color,
            bg_color=params.text_background_color,
            stroke_color=params.stroke_color,
            stroke_width=params.stroke_width,
            # interline=interline,
            # size=size,
        )
        duration = subtitle_item[0][1] - subtitle_item[0][0]
        _clip = _clip.with_start(subtitle_item[0][0])
        _clip = _clip.with_end(subtitle_item[0][1])
        _clip = _clip.with_duration(duration)
        if params.subtitle_position == "bottom":
            _clip = _clip.with_position(("center", video_height * 0.95 - _clip.h))
        elif params.subtitle_position == "top":
            _clip = _clip.with_position(("center", video_height * 0.05))
        elif params.subtitle_position == "custom":
            # Ensure the subtitle is fully within the screen bounds
            margin = 10  # Additional margin, in pixels
            max_y = video_height - _clip.h - margin
            min_y = margin
            custom_y = (video_height - _clip.h) * (params.custom_position / 100)
            custom_y = max(
                min_y, min(custom_y, max_y)
            )  # Constrain the y value within the valid range
            _clip = _clip.with_position(("center", custom_y))
        else:  # center
            _clip = _clip.with_position(("center", "center"))
        return _clip

    video_clip = VideoFileClip(video_path).without_audio()
    audio_clip = AudioFileClip(audio_path).with_effects(
        [afx.MultiplyVolume(params.voice_volume)]
    )

    def make_textclip(text):
        return TextClip(
            text=text,
            font=font_path,
            font_size=params.font_size,
        )

    if subtitle_path and os.path.exists(subtitle_path):
        sub = SubtitlesClip(
            subtitles=subtitle_path, encoding="utf-8", make_textclip=make_textclip
        )
        text_clips = []
        for item in sub.subtitles:
            clip = create_text_clip(subtitle_item=item)
            text_clips.append(clip)
        video_clip = CompositeVideoClip([video_clip, *text_clips])

    bgm_file = get_bgm_file(bgm_type=params.bgm_type, bgm_file=params.bgm_file)
    if bgm_file:
        try:
            bgm_clip = AudioFileClip(bgm_file).with_effects(
                [
                    afx.MultiplyVolume(params.bgm_volume),
                    afx.AudioFadeOut(3),
                    afx.AudioLoop(duration=video_clip.duration),
                ]
            )
            audio_clip = CompositeAudioClip([audio_clip, bgm_clip])
        except Exception as e:
            logger.error(f"failed to add bgm: {str(e)}")

    video_clip = video_clip.with_audio(audio_clip)
    _write_videofile_with_fallback(
        clip=video_clip,
        output_file=output_file,
        include_audio=True,
        threads=params.n_threads or 2,
        temp_audiofile_path=output_dir,
        local_fps=fps,
        stage="final_video",
    )
    video_clip.close()
    del video_clip


def preprocess_video(materials: List[MaterialInfo], clip_duration=4):
    for material in materials:
        if not material.url:
            continue

        ext = utils.parse_extension(material.url)
        try:
            clip = VideoFileClip(material.url)
        except Exception:
            clip = ImageClip(material.url)

        width = clip.size[0]
        height = clip.size[1]
        if width < 480 or height < 480:
            logger.warning(f"low resolution material: {width}x{height}, minimum 480x480 required")
            continue

        if ext in const.FILE_TYPE_IMAGES:
            logger.info(f"processing image: {material.url}")
            # Create an image clip and set its duration to 3 seconds
            clip = (
                ImageClip(material.url)
                .with_duration(clip_duration)
                .with_position("center")
            )
            # Apply a zoom effect using the resize method.
            # A lambda function is used to make the zoom effect dynamic over time.
            # The zoom effect starts from the original size and gradually scales up to 120%.
            # t represents the current time, and clip.duration is the total duration of the clip (3 seconds).
            # Note: 1 represents 100% size, so 1.2 represents 120% size.
            zoom_clip = clip.resized(
                lambda t: 1 + (clip_duration * 0.03) * (t / clip.duration)
            )

            # Optionally, create a composite video clip containing the zoomed clip.
            # This is useful when you want to add other elements to the video.
            final_clip = CompositeVideoClip([zoom_clip])

            # Output the video to a file.
            video_file = f"{material.url}.mp4"
            _write_videofile_with_fallback(
                clip=final_clip,
                output_file=video_file,
                include_audio=False,
                threads=2,
                local_fps=30,
                stage="image_to_video",
            )
            close_clip(clip)
            material.url = video_file
            logger.success(f"image processed: {video_file}")
    return materials
