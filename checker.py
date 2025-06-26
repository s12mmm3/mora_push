import asyncio
import aiohttp
import requests
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

# 每次拉取的页数
FETCH_PAGE_TIME = 5

class MoraReleaseChecker:
    """用于获取Mora.jp上指定日期发布的所有专辑"""
    
    @staticmethod
    async def fetch_page(session: aiohttp.ClientSession, region: str, page: int, timestamp: int) -> dict:
        url = f"https://cf.mora.jp/contents/data/newrelease/web/newrelease/newRelease_{region}_{page:04d}.jsonp?_{timestamp}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"获取第{page}页失败，状态码：{response.status}")
                    return {}

                text = await response.text()
                json_str = text.replace("moraCallback(", "")[:-2]  # 去除回调函数包装
                return json.loads(json_str)
        except Exception as e:
            print(f"获取第{page}页时出错: {e}")
            return {}

    @staticmethod
    async def get_albums(
        target_date: datetime.date,
        region: Optional[str] = None,
        deduplicate: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取指定日期发布的所有专辑
        
        :param target_date: 要查询的日期
        :param region: 地区代码，None则使用默认值 'jpn'
        :param deduplicate: 是否去重
        :return: 专辑字典列表
        """
        if region is None:
            region = "jpn"

        target_date_str = target_date.strftime("%Y/%m/%d") + " 00:00:00"
        timestamp = int(time.mktime(target_date.timetuple())) * 1000

        new_release_list = []
        page = 1
        has_more_pages = True

        async with aiohttp.ClientSession() as session:
            while has_more_pages:
                tasks = [MoraReleaseChecker.fetch_page(session, region, p, timestamp) for p in range(page, page + FETCH_PAGE_TIME)]
                results = await asyncio.gather(*tasks)

                current_data = []
                for data in results:
                    if not data or "newReleaseList" not in data:
                        continue
                    current_data.extend(data["newReleaseList"])

                # 过滤目标日期的专辑
                current_page_albums = [
                    album for album in current_data
                    if album["dispStartDate"] == target_date_str
                ]
                new_release_list.extend(current_page_albums)

                # 检查是否还有下一页
                last_album = current_data[-1] if current_data else None
                max_page = max((data.get("splitFileCnt", 0) for data in results if data), default=0)

                if any(album["dispStartDate"] < target_date_str for album in current_data):
                    has_more_pages = False
                elif page >= max_page:
                    has_more_pages = False
                else:
                    page += FETCH_PAGE_TIME  # 下一轮

        # 去重逻辑
        if deduplicate and new_release_list:
            seen = set()
            deduplicated_list = []

            for album in new_release_list:
                identifier = (
                    album["artistName"],
                    album["dispStartDate"],
                    album["title"],
                    album["trackCount"]
                )
                if identifier not in seen:
                    seen.add(identifier)
                    deduplicated_list.append(album)

            return deduplicated_list

        return new_release_list