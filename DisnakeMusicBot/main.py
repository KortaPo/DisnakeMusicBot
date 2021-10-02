import json
import os
from MusicBot import Bot

with open("./bot_utils/config.json") as f:
    config = json.load(f)

if __name__ == "__main__":

    bot = Bot()
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            bot.load_extension(f"cogs.{filename[:-3]}")
            print(f'{filename} cog loaded')
    bot.load_extension("jishaku")
    print("All cogs have been successfully loaded")

    bot.run(config["TOKEN"],
            reconnect=True)
