from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from zhenxun.utils.message import MessageUtils

from .utility import *

# 关注艺人命令
_follow_add_matcher = on_alconna(
    Alconna("mora关注", Args["artist", str]),
    priority=5,
    block=True,
    rule=to_me()
)

@_follow_add_matcher.handle()
async def follow_add_artist(session: Uninfo, arparma: Arparma):
    artist_name = arparma.query[str]("artist")
    if artist_name == '':
        await MessageUtils.build_message("请输入有效指令，如：mora关注 Variant Ariists").finish()
    id = session.scene.id
    type = session.scene.type
    artists = get_watch_artists(id, type)

    new_artist_info = {
        "name": artist_name,
        "alias": "",
        "type": "",
    }

    if any(a["name"] == new_artist_info["name"] for a in artists):
        await MessageUtils.build_message(f"已关注 {artist_name}，无需重复添加").send()
        return

    updated_artists = artists + [new_artist_info]
    set_watch_artists(id, type, updated_artists)
    await MessageUtils.build_message(f"成功关注艺人：{artist_name}").send()

# 取消关注艺人命令
_follow_remove_matcher = on_alconna(
    Alconna("mora取消关注", Args["artist", str]),
    priority=5,
    block=True,
    rule=to_me()
)

@_follow_remove_matcher.handle()
async def follow_remove_artist(session: Uninfo, arparma: Arparma):
    artist_name = arparma.query[str]("artist")
    if artist_name == '':
        await MessageUtils.build_message("请输入有效指令，如：mora取消关注 Variant Ariists").finish()
    id = session.scene.id
    type = session.scene.type

    current_artists = get_watch_artists(id, type)
    updated_artists = [a for a in current_artists if a["name"] != artist_name]

    if len(updated_artists) == len(current_artists):
        await MessageUtils.build_message(f"未找到名为 {artist_name} 的关注艺人").send()
    else:
        set_watch_artists(id, type, updated_artists)
        await MessageUtils.build_message(f"已取消关注：{artist_name}").send()


_follow_list_matcher = on_alconna(
    Alconna("mora关注列表"),
    priority=5,
    block=True,
    rule=to_me()
)

@_follow_list_matcher.handle()
async def follow_list_artists(session: Uninfo):
    id = session.scene.id
    type = session.scene.type
    artists = get_watch_artists(id, type)

    if not artists:
        await MessageUtils.build_message("当前没有关注任何艺人").send()
        return

    msg = ["当前关注的艺人：\n"]
    for idx, artist in enumerate(artists, 1):
        msg.append(f"{idx}. {artist['name']}\n")

    await MessageUtils.build_message(msg).send()