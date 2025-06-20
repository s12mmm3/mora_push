from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from zhenxun.utils.message import MessageUtils

from .utility import *

# 拉黑艺人命令
_blacklist_add_matcher = on_alconna(
    Alconna("mora拉黑", Args["artist", str]),
    priority=5,
    block=True,
    rule=to_me()
)

@_blacklist_add_matcher.handle()
async def blacklist_artist(session: Uninfo, arparma: Arparma):
    artist_name = arparma.query[str]("artist")
    if artist_name == '':
        await MessageUtils.build_message("请输入有效指令，如：mora关注 Variant Ariists").finish()
    id = session.scene.id
    type = session.scene.type
    artists = get_blacklist_artists(id, type)

    new_artist_info = {
        "name": artist_name,
        "alias": "",
        "type": "",
    }

    if any(a["name"] == new_artist_info["name"] for a in artists):
        await MessageUtils.build_message(f"已拉黑 {artist_name}，无需重复添加").send()
        return

    updated_artists = artists + [new_artist_info]
    set_blacklist_artists(id, type, updated_artists)
    await MessageUtils.build_message(f"成功将艺人拉黑：{artist_name}").send()

# 取消拉黑艺人命令
_blacklist_remove_matcher = on_alconna(
    Alconna("mora拉黑移除", Args["artist", str]),
    priority=5,
    block=True,
    rule=to_me()
)

@_blacklist_remove_matcher.handle()
async def blacklist_remove_artist(session: Uninfo, arparma: Arparma):
    artist_name = arparma.query[str]("artist")
    if artist_name == '':
        await MessageUtils.build_message("请输入有效指令，如：mora取消关注 Variant Ariists").finish()
    id = session.scene.id
    type = session.scene.type

    current_artists = get_blacklist_artists(id, type)
    updated_artists = [a for a in current_artists if a["name"] != artist_name]

    if len(updated_artists) == len(current_artists):
        await MessageUtils.build_message(f"未找到名为 {artist_name} 的拉黑艺人").send()
    else:
        set_blacklist_artists(id, type, updated_artists)
        await MessageUtils.build_message(f"已取消拉黑：{artist_name}").send()


_blacklist_list_matcher = on_alconna(
    Alconna("mora拉黑列表"),
    priority=5,
    block=True,
    rule=to_me()
)

@_blacklist_list_matcher.handle()
async def blacklist_list_artists(session: Uninfo):
    id = session.scene.id
    type = session.scene.type
    artists = get_blacklist_artists(id, type)

    if not artists:
        await MessageUtils.build_message("当前没有拉黑任何艺人").send()
        return

    msg = ["当前拉黑的艺人：\n"]
    for idx, artist in enumerate(artists, 1):
        msg.append(f"{idx}. {artist['name']}\n")

    await MessageUtils.build_message(msg).send()