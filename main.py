from __future__ import annotations

from twitchio.ext import commands
from config import config

from cogs.requests import Requests

class Bot(commands.Bot):
    def __init__(self) -> Bot:
        super().__init__(
            token=config["twitch"]["access_token"], 
            prefix=config["twitch"]["command_prefix"], 
            initial_channels=['henryosu'] 
            # TODO: maybe initially load linked channels once we get twitch/akat account linking sorted?
        )

    async def event_ready(self):
        # print(f"ahoy spongebob i've overdosed on ketamine and im going to die arghargharghargh")
        # print(f"We have logged in as {self.nick}")
        # print(f"User ID: {self.user_id}")
        pass

def main() -> None:
    bot = Bot()
    bot.add_cog(Requests(bot))
    bot.run() 

if __name__ == "__main__":
    main()