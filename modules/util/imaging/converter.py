import re
import unicodedata
from io import BytesIO

from aiohttp import ClientSession
from bs4 import BeautifulSoup
from discord.ext import commands

from modules.util.converters import SpecificUserConverter
from modules.util.executor import executor

TENOR_REGEX = r"https?:\/\/tenor\.com\/view\/.+"
URL_REGEX = (
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)

CONTENT_TYPES = ["image/gif", "image/jpeg", "image/png", "image/webp"]


async def scrape_tenor(session: ClientSession, url: str):
    @executor()
    def parse(content: str):
        soup = BeautifulSoup(content, "lxml")
        gif = soup.find("div", class_="Gif")
        if gif:
            img = gif.find("img")
            if img:
                return img.get("src")

    async with session.get(url) as resp:
        if resp.status != 200:
            return

        content = await resp.text()
        return await parse(content)


async def read_url(url: str, session: ClientSession, *args, **kwargs):
    resp = await session.get(url, *args, **kwargs)
    content_type = resp.headers.get("Content-Type")
    data = await resp.read()
    if len(data) > 16 * 1024 * 1024:  # 16 mb
        return
    if content_type in CONTENT_TYPES:
        return BytesIO(data)


async def parse_url(url: str, session: ClientSession):
    if re.match(TENOR_REGEX, url) and (tenor := await scrape_tenor(session, url)):
        url = tenor

    return await read_url(url, session)


# thanks chatgpt
def is_emoji(content: str):
    for char in content:
        if unicodedata.category(char) in ("So", "Sk"):
            return char


class ImageConverter(commands.Converter):
    async def convert(
        self,
        ctx: commands.Context,
        argument: str,
        *,
        relative: bool = True,
        animated: bool = True,
        fallback: bool = True,
    ) -> str:
        argument = argument.strip()
        message = ctx.message

        used = False

        if message.attachments:
            if result := await read_url(message.attachments[0].url, ctx.bot.session):
                return result, used

        if message.reference and relative:
            if message.reference.resolved:
                ref = message.reference.resolved
                if ref.attachments:
                    if result := await read_url(
                        ref.attachments[0].url, ctx.bot.session
                    ):
                        return result, used
                argument = ref.content

        try:
            user = await SpecificUserConverter().convert(ctx, argument)
        except Exception:
            pass
        else:
            if not animated:
                return BytesIO(await user.avatar.with_format("png").read()), True
            return BytesIO(await user.avatar.read()), True

        if re.match(URL_REGEX, argument):
            if result := await parse_url(argument, ctx.bot.session):
                return result, True

        try:
            emoji = await commands.PartialEmojiConverter().convert(ctx, argument)
        except Exception:
            pass
        else:
            return BytesIO(await emoji.read()), True

        if len(argument) == 1 and (emoji := is_emoji(argument)):
            url = "https://emojicdn.elk.sh/" + emoji
            if result := await read_url(
                url, ctx.bot.session, params={"style": "twitter"}
            ):
                return result, True

        if fallback:
            if not animated:
                return BytesIO(await ctx.author.avatar.with_format("png").read()), False
            return BytesIO(await ctx.author.avatar.read()), False
        return None, False


async def setup(bot):
    pass
