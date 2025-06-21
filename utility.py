from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, Dict, List

import aiohttp

from nonebot_plugin_uninfo import SceneType

from zhenxun.utils._image_template import ImageTemplate
from .checker import MoraReleaseChecker
from zhenxun.configs.path_config import DATA_PATH

config_path: Path = DATA_PATH / "mora/config.json"

DATE_REGEX = re.compile(r'^\d{4}(/\d{1,2}){1,2}$')  # 匹配类似 2025/5/3 的格式

def parse_date_str(date_str: str) -> datetime.date:
    return datetime.strptime(date_str, "%Y/%m/%d").date()

def get_date_str(date: datetime.date) -> str:
    return date.strftime('%Y/%m/%d')

# 读取配置文件
def load_config() -> List[Dict[str, Any]]:
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.touch()
        save_config([])
        return []
    with open(config_path, "r", encoding="utf8") as f:
        return json.load(f)

# 写入配置文件
def save_config(data):
    with open(config_path, "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_scene(id: str, type: SceneType) -> Dict[str, Any]:
    """获取指定ID和类型的场景配置"""
    data = load_config()
    for item in data:
        if item["id"] == id and item["type"] == type:
            return item
    return {}

def set_scene(id: str, type: SceneType, update_data: Dict[str, Any]):
    """
    更新或创建指定ID和类型的场景配置
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :param update_data: 要更新的数据字段
    """
    data = load_config()
    found = False
    
    # 更新现有配置项
    for item in data:
        if item["id"] == id and item["type"] == type:
            item.update(update_data)  # 更新所有提供的字段
            found = True
            break
    
    # 如果找不到，创建新配置项
    if not found:
        default_item = {
            "id": id,
            "type": type,
            "watch_artists": [],
            "auto_push": False
        }
        default_item.update(update_data)  # 应用更新数据
        data.append(default_item)
    
    save_config(data)

def get_watch_artists(id: str, type: SceneType) -> List[Dict[str, Any]]:
    """
    获取指定ID和类型的关注艺人列表
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :return: 艺人列表，找不到时返回空列表
    """
    return get_scene(id, type).get("watch_artists", [])

def set_watch_artists(id: str, type: SceneType, artists: List[Dict[str, Any]]):
    """
    设置指定ID和类型的关注艺人列表
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :param artists: 新的艺人列表
    """
    set_scene(id, type, {"watch_artists": artists})

def get_blacklist_artists(id: str, type: SceneType) -> List[Dict[str, Any]]:
    """
    获取指定ID和类型的黑名单艺人列表
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :return: 黑名单艺人列表，找不到时返回空列表
    """
    return get_scene(id, type).get("blacklist_artists", [])

def set_blacklist_artists(id: str, type: SceneType, artists: List[Dict[str, Any]]):
    """
    设置指定ID和类型的黑名单艺人列表
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :param artists: 新的黑名单艺人列表
    """
    set_scene(id, type, {"blacklist_artists": artists})


def set_push_new_albums(id: str, type: SceneType, auto_push: bool = True):
    """
    设置指定ID和类型的是否接受推送选项
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :param auto_push: 是否接受推送选项
    """
    set_scene(id, type, { "auto_push": auto_push })

def get_push_new_albums(id: str, type: SceneType) -> bool:
    """
    获取指定ID和类型的是否接受推送选项
    
    :param id: 用户/群组ID
    :param type: 类型标识 (0=群组, 1=用户等)
    :return: 是否接受推送选项，找不到时返回False
    """
    return get_scene(id, type).get("auto_push", False)
    
def filter_albums(albums: List[Dict[str, Any]], blacklist_artists: List[Dict[str, Any]]):
    blacklist_names: list[str] = [artist["name"] for artist in blacklist_artists]
    
    result = []
    for album in albums:
        artistName = album["artistName"]
        # 检查是否包含任意黑名单名称
        if not any(black_name in artistName for black_name in blacklist_names):
            result.append(album)
    
    return result

async def download_image(url: str) -> BytesIO:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                image_data = await resp.read()
                return BytesIO(image_data)
            raise Exception(f"图片下载失败，状态码: {resp.status}")

def split_array(arr, chunk_size=500):
    """将数组按指定大小切割"""
    return [arr[i:i + chunk_size] for i in range(0, len(arr), chunk_size)]

ALBUM_INFO = """
  {idx}. 《{title}》- {artistName}，共{trackCount}首曲子

""".strip()

TOTAL_INFO = """
其他新专新曲 ({date}) 

""".strip()
class MoraHelper(MoraReleaseChecker):
    @staticmethod
    async def get_watch_artists_albums(albums: List[Dict[str, Any]], watch_artists: List[Dict[str, Any]]):
        artist_results = []
        for artist_info in watch_artists:
            matched_albums = [
                album for album in albums
                if artist_info["name"] in album["artistName"]# or (artist_info["alias"] and artist_info["alias"] in album["artistName"])
            ]
            if matched_albums:
                artist_result = {**artist_info, 'albums': matched_albums}
                artist_results.append(artist_result)

        result_info_list = []
        for artist in artist_results:
            result = [f"{artist['name']} 发布了 {len(artist['albums'])} 张专辑:\n"]
            for idx, album in enumerate(artist['albums'], 1):
                album_info = ALBUM_INFO.format(idx = idx, title = album['title'], artistName = album['artistName'], trackCount = album['trackCount'])
                result.append(album_info)
                image_url = f"{album['packageUrl']}{album['packageimage']}"
                image_bytesio = await download_image(image_url)
                result.append(image_bytesio)
            result_info_list.append(result)
        return result_info_list

    @staticmethod 
    async def get_all_albums_image(albums: List[Dict[str, Any]], target_date: datetime.date):
        process_string = lambda text: ((text or "").replace('\n', '').replace('\r', ''))[:20]
        pic_source = [[process_string(album['title']),
                        process_string(album['artistName']),
                        process_string(album['packageComment'])] for album in albums]
        result = [TOTAL_INFO.format(date=get_date_str(target_date))]
        # 一页500张专辑，避免图片过大上传失败
        for idx, sourceItem in enumerate(split_array(pic_source, 500), 1):
            img = await ImageTemplate.table_page(
                f"所有新曲 第 {idx} 页 共 {len(sourceItem)} 首",
                None,
                ['专辑名', '艺人', '简介'],
                sourceItem,
                10,
                10
            )
            result.append(img)
        return result