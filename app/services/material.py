import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.utils import utils

requested_count = 0
_last_pexels_request_ts = 0.0


def _respect_pexels_interval():
    global _last_pexels_request_ts
    min_interval = float(config.app.get("pexels_min_interval_seconds", 0.35))
    now = time.time()
    elapsed = now - _last_pexels_request_ts
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_pexels_request_ts = time.time()


def _log_pexels_rate_headers(resp: requests.Response):
    # Headers are available on successful responses and help track monthly quota.
    limit = resp.headers.get("X-Ratelimit-Limit")
    remain = resp.headers.get("X-Ratelimit-Remaining")
    reset = resp.headers.get("X-Ratelimit-Reset")
    if limit or remain or reset:
        logger.info(
            f"pexels quota => limit={limit or '-'}, remaining={remain or '-'}, reset={reset or '-'}"
        )


def _request_pexels_with_retry(url: str, headers: dict) -> requests.Response | None:
    max_retries = int(config.app.get("pexels_max_retries", 4))
    base_backoff = float(config.app.get("pexels_backoff_base_seconds", 1.0))
    timeout = (30, 60)

    for attempt in range(max_retries):
        _respect_pexels_interval()
        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=config.proxy,
                verify=False,
                timeout=timeout,
            )

            if resp.status_code == 429:
                wait_seconds = base_backoff * (2**attempt)
                logger.warning(
                    f"pexels rate limited (429), retry {attempt + 1}/{max_retries} after {wait_seconds:.1f}s"
                )
                time.sleep(wait_seconds)
                continue

            if resp.status_code >= 500:
                wait_seconds = base_backoff * (2**attempt)
                logger.warning(
                    f"pexels server error ({resp.status_code}), retry {attempt + 1}/{max_retries} after {wait_seconds:.1f}s"
                )
                time.sleep(wait_seconds)
                continue

            _log_pexels_rate_headers(resp)
            return resp
        except Exception as e:
            wait_seconds = base_backoff * (2**attempt)
            logger.warning(
                f"pexels request failed ({str(e)}), retry {attempt + 1}/{max_retries} after {wait_seconds:.1f}s"
            )
            time.sleep(wait_seconds)

    return None


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global requested_count
    requested_count += 1
    return api_keys[requested_count % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    per_page = int(config.app.get("pexels_per_page", 20))
    per_page = min(max(per_page, 1), 80)
    
    pexels_page = int(config.app.get("pexels_page", 1) or 1)
    page_num = max(1, pexels_page)

    endpoint_mode = str(config.app.get("pexels_endpoint", "search")).strip().lower()
    
    if endpoint_mode == "popular":
        params = {
            "per_page": per_page,
            "page": page_num
        }
        
        min_width = int(config.app.get("pexels_min_width", 0))
        if min_width > 0: params["min_width"] = min_width
        
        min_height = int(config.app.get("pexels_min_height", 0))
        if min_height > 0: params["min_height"] = min_height

        min_duration_pop = int(config.app.get("pexels_min_duration", 0))
        if min_duration_pop > 0: params["min_duration"] = min_duration_pop

        max_duration_pop = int(config.app.get("pexels_max_duration", 0))
        if max_duration_pop > 0: params["max_duration"] = max_duration_pop
        
        query_url = f"https://api.pexels.com/v1/videos/popular?{urlencode(params)}"
    else:
        # User defined orientation overrides global aspect orientation
        user_ori = str(config.app.get("pexels_orientation", "auto")).strip().lower()
        active_ori = user_ori if user_ori in {"landscape", "portrait", "square"} else video_orientation
        
        params = {
            "query": search_term,
            "per_page": per_page,
            "page": page_num,
            "orientation": active_ori,
        }

        pexels_size = str(config.app.get("pexels_size", "")).strip().lower()
        if pexels_size in {"small", "medium", "large"}:
            params["size"] = pexels_size

        pexels_locale = str(config.app.get("pexels_locale", "")).strip()
        if pexels_locale:
            params["locale"] = pexels_locale

        query_url = f"https://api.pexels.com/v1/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = _request_pexels_with_retry(query_url, headers)
        if r is None:
            logger.error("search videos failed: pexels request exhausted retries")
            return []
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["videos"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["video_files"]
            # loop through each url to determine the best quality
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                if w == video_width and h == video_height:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    video_width, video_height = aspect.to_resolution()

    api_key = get_api_key("pixabay_api_keys")
    # Build URL
    params = {
        "q": search_term,
        "video_type": "all",  # Accepted values: "all", "film", "animation"
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=False, timeout=(30, 60)
        )
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["hits"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            # loop through each url to determine the best quality
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                # h = int(video["height"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # if video does not exist, download it
    with open(video_path, "wb") as f:
        f.write(
            requests.get(
                video_url,
                headers=headers,
                proxies=config.proxy,
                verify=False,
                timeout=(60, 240),
            ).content
        )

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            clip.close()
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            try:
                os.remove(video_path)
            except Exception:
                pass
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
    max_items: int = 0,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    for search_term in search_terms:
        video_items = search_videos(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    required_duration = max(0.0, float(audio_duration or 0.0))
    workers = int(config.app.get("video_download_workers", 4) or 4)
    workers = max(1, min(workers, 16))
    max_items = int(max_items or 0)
    enforce_duration_limit = required_duration > 0 and max_items <= 0
    duplicate_skipped = 0
    failed_count = 0
    empty_result_count = 0
    logger.info(
        f"download strategy => workers={workers}, required_duration={required_duration:.2f}s, max_items={max_items}, enforce_duration_limit={enforce_duration_limit}, candidates={len(valid_video_items)}"
    )

    if workers == 1:
        for item in valid_video_items:
            try:
                logger.info(f"downloading video: {item.url}")
                saved_video_path = save_video(
                    video_url=item.url, save_dir=material_directory
                )
                if not saved_video_path:
                    empty_result_count += 1
                    continue

                if saved_video_path in video_paths:
                    duplicate_skipped += 1
                    continue

                if saved_video_path and saved_video_path not in video_paths:
                    logger.info(f"video saved: {saved_video_path}")
                    video_paths.append(saved_video_path)
                    if max_items > 0 and len(video_paths) >= max_items:
                        logger.info(f"reached max_items={max_items}, stop downloading more")
                        break
                    total_duration += min(max_clip_duration, item.duration)
                    if enforce_duration_limit and total_duration > required_duration:
                        logger.info(
                            f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                        )
                        break
            except Exception as e:
                failed_count += 1
                logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    else:
        def _download_one(index: int, item: MaterialInfo):
            logger.info(f"downloading video[{index + 1}]: {item.url}")
            saved_video_path = save_video(video_url=item.url, save_dir=material_directory)
            return index, saved_video_path, min(max_clip_duration, item.duration)

        future_to_item = {}
        accepted_paths = set()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for idx, item in enumerate(valid_video_items):
                future = executor.submit(_download_one, idx, item)
                future_to_item[future] = item

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    _, saved_video_path, seconds = future.result()
                    if not saved_video_path:
                        empty_result_count += 1
                        continue
                    if saved_video_path in accepted_paths:
                        duplicate_skipped += 1
                        continue

                    accepted_paths.add(saved_video_path)
                    video_paths.append(saved_video_path)
                    if max_items > 0 and len(video_paths) >= max_items:
                        logger.info(f"reached max_items={max_items}, stop accepting more results")
                        break
                    total_duration += seconds
                    logger.info(
                        f"video saved: {saved_video_path}, collected={total_duration:.2f}s"
                    )

                    if enforce_duration_limit and total_duration > required_duration:
                        logger.info(
                            f"total duration of downloaded videos: {total_duration} seconds, stop accepting more results"
                        )
                        break
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"failed to download video: {utils.to_json(item)} => {str(e)}"
                    )

            for future in future_to_item:
                if not future.done():
                    future.cancel()

    requested_items = max_items if max_items > 0 else None
    shortfall = 0
    if requested_items is not None:
        shortfall = max(0, requested_items - len(video_paths))

    logger.info(
        "download diagnostics => "
        f"requested_items={requested_items if requested_items is not None else '-'}, "
        f"downloaded={len(video_paths)}, shortfall={shortfall}, "
        f"candidates={len(valid_video_items)}, duplicate_skipped={duplicate_skipped}, "
        f"failed={failed_count}, empty_result={empty_result_count}, "
        f"duration_collected={total_duration:.2f}s"
    )
    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )
