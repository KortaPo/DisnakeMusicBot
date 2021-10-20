import json

from MusicBot import Bot

with open("./bot_utils/config.json") as f:
    config = json.load(f)

if __name__ == "__main__":

    bot = Bot()
    bot.load_cogs('cogs')
    print("All cogs have been successfully loaded")

    bot.run(config["TOKEN"],
            reconnect=True)
