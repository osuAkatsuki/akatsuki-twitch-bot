import twitchio
import re

from twitchio.ext import commands


class Requests(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.event()
    async def event_message(self, message: twitchio.Message):
        if message.echo:
            return

        links = re.finditer(
            r"https:\/\/osu.ppy.sh\/(beatmapsets\b|b\b|s\b)\/[0-9]+(#[^ ]+\/[0-9]+)?",
            message.content,
        )
        # TODO: improve this regex

        for match in links:
            pass


def prepare(bot: commands.Bot):
    bot.add_cog(Requests(bot))
