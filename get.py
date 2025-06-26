import asyncio
import nonebot
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from nonebot.plugin import PluginMetadata

from zhenxun.configs.utils import Command, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils._image_template import ImageTemplate
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from datetime import datetime, timedelta
import pytz

from zhenxun.utils.platform import PlatformUtils

from .utility import *

__plugin_meta__ = PluginMetadata(
    name="mora推送",
    description="查询 mora 平台每日发布的新曲信息",
    usage="""
    查询 mora 平台每日发布的新曲信息。

    指令：
        mora新曲               - 查询今日日本地区新曲
        mora新曲 2025/5/3      - 查询指定日期的日本新曲
        mora新曲 2025/5/3 int  - 查询指定日期的国际新曲
        mora关注 艺人名         - 添加艺人到关注列表
        mora取消关注 艺人名     - 从关注列表移除艺人
        mora关注列表           - 查看当前关注的艺人列表
        mora接受订阅           - 接收每日推送
        mora取消订阅           - 取消每日推送

        mora拉黑 艺人名       - 添加黑名单，推送时不显示
        mora拉黑移除 艺人名   - 取消添加黑名单
        mora拉黑列表          - 查看当前黑名单艺人列表

    注意事项：
        - 默认使用日本时区（UTC+9）
        - 区域参数不区分大小写，支持 jpn / int 等格式
    """.strip(),
    extra=PluginExtraData(
        author="舰长的初号",
        version="1.0",
        plugin_type=PluginType.NORMAL,
        # menu_type="其他",
        commands=[
            Command(command="mora新曲 [date]"),
            Command(command="mora关注 [artist]"),
            Command(command="mora取消关注 [artist]"),
            Command(command="mora关注列表"),
            Command(command="mora接受订阅"),
            Command(command="mora取消订阅"),

            Command(command="mora拉黑添加"),
            Command(command="mora拉黑移除"),
            Command(command="mora拉黑列表"),
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna(
        "mora新曲",
        Args["target?", str],           # 默认值设为今天
        Args["region?", str],           # 可选参数 region，默认 None
    ),
    priority=5,
    block=True,
    rule=to_me()
)

@_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    target = arparma.query[str]("target") or ""
    region = arparma.query[str]("region") or "jpn"

    if DATE_REGEX.match(target):
        query_date = parse_date_str(target)
    elif target == '':
        now_jp = datetime.now(pytz.timezone("Asia/Tokyo"))
        today = now_jp.date()
        query_date = today
    else:
        await MessageUtils.build_message("请输入有效指令，如：mora新曲 2025/5/3").finish()
        return

    logger.info(f"查询日期：{query_date}，区域：{region}")
    await mora_get(session, arparma, query_date, region)

async def send_message(albums: List[Dict[str, Any]],
                       target_date: datetime.date,
                       user_id,
                       group_id,
                       type: SceneType): 
    bot = nonebot.get_bot()
    await PlatformUtils.send_message(bot=bot,
                                     user_id=user_id,
                                     group_id=group_id,
                                     message=MessageUtils.build_message("=== {date} 发布了 {len} 张专辑 ===\n".strip().format(date=get_date_str(target_date), len=len(albums))))
    blacklist_artist = get_blacklist_artists(user_id, type) if type == SceneType.PRIVATE else get_blacklist_artists(group_id, type)
    albums = filter_albums(albums, blacklist_artist)
    watch_artists = get_watch_artists(user_id, type) if type == SceneType.PRIVATE else get_watch_artists(group_id, type)
    for result_info in await MoraHelper.get_watch_artists_albums(albums, watch_artists):
        await PlatformUtils.send_message(bot=bot,
                                         user_id=user_id,
                                         group_id=group_id,
                                         message=MessageUtils.build_message(result_info))

    all_albums_image: list = await MoraHelper.get_all_albums_image(albums, target_date)

    await PlatformUtils.send_message(bot=bot,
                                     user_id=user_id,
                                     group_id=group_id,
                                     message=MessageUtils.build_message(all_albums_image))

async def mora_get(session: Uninfo, arparma: Arparma, query_date: datetime.date, region: str):
    id = session.scene.id
    type: SceneType = session.scene.type
    try:
        await MessageUtils.build_message([f"正在获取 {get_date_str(query_date)} 的 mora 新专辑"]).send()
        albums = MoraReleaseChecker().get_albums(target_date = query_date, region = region)
        user_id = id if type == SceneType.PRIVATE else None
        group_id = id if type == SceneType.GROUP else None
        
        # 调用send_message发送所有消息
        await send_message(
            albums=albums,
            target_date=query_date,
            user_id=user_id,
            group_id=group_id,
            type=type
        )
        
    except Exception as e:
        await MessageUtils.build_message(f"获取mora新曲失败: {e}").send()

_push_matcher = on_alconna(Alconna("mora接受订阅"), priority=5, block=True, rule=to_me())
@_push_matcher.handle()
async def push_new_albums(session: Uninfo, arparma: Arparma):
    set_push_new_albums(session.scene.id, session.scene.type, True)
    await MessageUtils.build_message('成功接收mora推送订阅').send()

_unpush_matcher = on_alconna(Alconna("mora取消订阅"), priority=5, block=True, rule=to_me())
@_unpush_matcher.handle()
async def unpush_new_albums(session: Uninfo, arparma: Arparma):
    set_push_new_albums(session.scene.id, session.scene.type, False)
    await MessageUtils.build_message('成功取消mora推送订阅').send()

async def daily_check_mora_new_songs():
    logger.info("开始执行每日检查任务：mora 新专辑推送")

    # 获取所有开启 auto_push 的群/用户
    groups_with_push_enabled = []
    private_with_push_enabled = []
    mora_config = load_config()
    for info in mora_config:
        id: str = str(info.get('id'))
        type: SceneType = SceneType(info.get('type'))
        if get_push_new_albums(id, type):
            if type == SceneType.GROUP:
                groups_with_push_enabled.append(str(id))
            elif type == SceneType.PRIVATE:
                private_with_push_enabled.append(str(id))

    now_jp = datetime.now(pytz.timezone("Asia/Tokyo"))
    today = now_jp.date()

    retryTime = 15
    albums = []
    target_date = today
    while retryTime > 0:
        albums = MoraReleaseChecker.get_albums(
            target_date = target_date,
            region = "jpn"
            )
        if len(albums) > 0:
            break
        retryTime = retryTime - 1
        logger.error(f"拉取失败，尝试次数剩余: {retryTime}")
        await asyncio.sleep(20)
    try:
        bot = nonebot.get_bot()

        # 获取当前机器人支持的群列表和好友列表
        group_list = [str(g["group_id"]) for g in await bot.get_group_list()]
        friend_list = [str(g["user_id"]) for g in await bot.get_friend_list()]

        tasks = []

        # 构建群聊推送任务
        for group_id in group_list:
            if group_id in groups_with_push_enabled:
                tasks.append(
                    send_message(albums, today, None, group_id, type=SceneType.GROUP)
                )

        # 构建私聊推送任务
        for user_id in friend_list:
            if user_id in private_with_push_enabled:
                tasks.append(
                    send_message(albums, today, user_id, None, type=SceneType.PRIVATE)
                )

        # 并行执行所有 send_message 任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查结果是否有异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"第 {i} 个消息发送任务失败: {result}")

    except Exception as e:
        logger.error(f"定时推送失败: {e}")


async def push_new():
    asyncio.create_task(daily_check_mora_new_songs())
    pass

from nonebot_plugin_apscheduler import scheduler
from apscheduler.triggers.cron import CronTrigger
scheduler.add_job(
    push_new,
    CronTrigger(hour=23, minute=7),
    id="check_mora_new_songs"
)