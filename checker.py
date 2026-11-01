import asyncio
from datetime import date, datetime
import logging
import time
from typing import Any

import aiohttp

from zhenxun.configs.config import BotConfig

FETCH_PAGE_TIME = 5
FETCH_ATTEMPTS = 3
REQUEST_TIMEOUT = 30
REGIONS = frozenset(
    {"all", "jpn", "int", "hrs", "hja", "hin", "cdq", "cja", "cin", "vid", "var"}
)
logger = logging.getLogger(__name__)


class MoraFetchError(RuntimeError):
    """Mora 分页获取失败，不能将结果视为完整列表。"""


class MoraReleaseChecker:
    """获取 Mora 新发行列表中指定日期的作品。"""

    @staticmethod
    def normalize_region(region: str | None) -> str:
        region = "jpn" if region is None else region.strip().lower()
        if region not in REGIONS:
            choices = ", ".join(sorted(REGIONS))
            raise ValueError(f"不支持的 mora 区域：{region}，可选：{choices}")
        return region

    @staticmethod
    def release_date(album: dict[str, Any]) -> date:
        return datetime.strptime(album["dispStartDate"], "%Y/%m/%d %H:%M:%S").date()

    @staticmethod
    def validate_page(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("分页数据不是 JSON 对象")
        items = data.get("newReleaseList")
        pages = data.get("splitFileCnt")
        if not isinstance(items, list) or type(pages) is not int or pages < 0:
            raise ValueError("分页缺少有效的 newReleaseList 或 splitFileCnt")
        if (items and pages == 0) or (
            not items and (pages > 1 or data.get("totalItemCnt", 0) != 0)
        ):
            raise ValueError("分页条目与总页数不一致")
        for album in items:
            if not isinstance(album, dict):
                raise ValueError("发行条目不是 JSON 对象")
            for key in ("artistName", "title", "dispStartDate"):
                if not isinstance(album.get(key), str):
                    raise ValueError(f"发行条目缺少有效的 {key}")
            if type(album.get("trackCount")) is not int:
                raise ValueError("发行条目缺少有效的 trackCount")
            MoraReleaseChecker.release_date(album)
        return data

    @staticmethod
    async def fetch_page(
        session: aiohttp.ClientSession, region: str, page: int, timestamp: int
    ) -> dict[str, Any]:
        region = MoraReleaseChecker.normalize_region(region)
        url = (
            "https://cf.mora.jp/contents/data/newrelease/web/newrelease/"
            f"newRelease_{region}_{page:04d}.json?_={timestamp}"
        )
        for attempt in range(FETCH_ATTEMPTS):
            try:
                async with session.get(url, proxy=BotConfig.system_proxy) as response:
                    response.raise_for_status()
                    data = await response.json()
                return MoraReleaseChecker.validate_page(data)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                if attempt == FETCH_ATTEMPTS - 1:
                    raise MoraFetchError(
                        f"mora {region} 第 {page} 页获取失败"
                        f"（已尝试 {FETCH_ATTEMPTS} 次）：{exc}"
                    ) from exc
                logger.warning("mora %s 第 %s 页失败，准备重试：%s", region, page, exc)
                await asyncio.sleep(attempt + 1)
        raise AssertionError("FETCH_ATTEMPTS 必须大于 0")

    @staticmethod
    def deduplicate_works(albums: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 按歌手、发行日、标题、曲数识别作品，不合并标题不同的特别版等。
        # 相同作品优先 Hi-Res，其次无损、普通；同等级保留先出现的版本。
        quality_priority = {12: 3, 13: 3, 15: 2, 10: 1}
        works: dict[tuple, dict[str, Any]] = {}
        for album in albums:
            key = (
                album["artistName"].strip(),
                MoraReleaseChecker.release_date(album),
                album["title"].strip(),
                album["trackCount"],
            )
            previous = works.get(key)
            if previous is None or quality_priority.get(
                album.get("mediaFormatNo"), 0
            ) > quality_priority.get(previous.get("mediaFormatNo"), 0):
                works[key] = album
        return list(works.values())

    @classmethod
    async def get_albums(
        cls,
        target_date: date,
        region: str | None = None,
        deduplicate: bool = True,
    ) -> list[dict[str, Any]]:
        """按发行日筛选作品；任何必要分页失败都会报错，不返回残缺结果。"""
        region = cls.normalize_region(region)
        timestamp = time.time_ns() // 1_000_000
        albums = []
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 先读取第一页，避免不知道总页数时请求不存在的分页。
            first = await cls.fetch_page(session, region, 1, timestamp)
            max_page = first["splitFileCnt"]
            results = [first]
            next_page = 2
            while True:
                for data in results:
                    for album in data["newReleaseList"]:
                        if cls.release_date(album) == target_date:
                            albums.append(album)

                # Mora 列表按发行时间倒序排列；整批读取成功后才能判断停止。
                if any(
                    cls.release_date(album) < target_date
                    for data in results
                    for album in data["newReleaseList"]
                ) or next_page > max_page:
                    break
                end_page = min(next_page + FETCH_PAGE_TIME - 1, max_page)
                batch = await asyncio.gather(
                    *(
                        cls.fetch_page(session, region, page, timestamp)
                        for page in range(next_page, end_page + 1)
                    ),
                    return_exceptions=True,
                )
                # 等待本批请求结束，避免报错后其他请求仍在使用已关闭的 session。
                results = []
                for result in batch:
                    if isinstance(result, BaseException):
                        raise result
                    results.append(result)
                next_page = end_page + 1

        return cls.deduplicate_works(albums) if deduplicate else albums
