import asyncio
import collections
import re
from random import random

from metagpt.actions import Action

STEP_INSTRUCTIONS = {
    # 上帝需要介入的全部步骤和对应指令
    # The 1-st night
    0: {"content": "It’s dark, everyone close your eyes. I will talk with you/your team secretly at night.",
        "send_to": "Moderator",  # for moderator to continuen speaking
        "restricted_to": ""},
    1: {"content": "Guard, please open your eyes!",
        "send_to": "Moderator",  # for moderator to continuen speaking
        "restricted_to": ""},
    2: {"content": """Guard, now tell me who you protect tonight?
                   You only choose one from the following living options please: {living_players}.
                   Or you can pass. For example: Protect ...""",
        "send_to": "Guard",
        "restricted_to": "Moderator,Guard"},
    3: {"content": "Guard, close your eyes",
        "send_to": "Moderator",
        "restricted_to": ""},
    4: {"content": "Werewolves, please open your eyes!",
        "send_to": "Moderator",
        "restricted_to": ""},
    5: {"content": """Werewolves, I secretly tell you that {werewolf_players} are
                   all of the 2 werewolves! Keep in mind you are teammates. The rest players are not werewolves.
                   choose one from the following living options please:
                   {living_players}. For example: Kill ...""",
        "send_to": "Werewolf",
        "restricted_to": "Moderator,Werewolf"},
    6: {"content": "Werewolves, close your eyes",
        "send_to": "Moderator",
        "restricted_to": ""},
    7: {"content": "Witch, please open your eyes!",
        "send_to": "Moderator",
        "restricted_to": ""},
    8: {"content": """Witch, tonight {player_hunted} has been killed by the werewolves.
                   You have a bottle of antidote, would you like to save him/her? If so, say "Save", else, say "Pass".""",
        "send_to": "Witch",
        "restricted_to": "Moderator,Witch"},  # 要先判断女巫是否有解药，再去询问女巫是否使用解药救人
    9: {"content": """Witch, you also have a bottle of poison, would you like to use it to kill one of the living players?
                   Choose one from the following living options: {living_players}.
                   If so, say ONLY "Poison PlayerX", replace PlayerX with the actual player name, else, say "Pass".""",
        "send_to": "Witch",
        "restricted_to": "Moderator,Witch"},  #
    10: {"content": "Witch, close your eyes",
         "send_to": "Moderator",
         "restricted_to": ""},
    11: {"content": "Seer, please open your eyes!",
         "send_to": "Moderator",
         "restricted_to": ""},
    12: {"content": """Seer, you can check one player's identity. Who are you going to verify its identity tonight?
                    Choose only one from the following living options:{living_players}.""",
         "send_to": "Seer",
         "restricted_to": "Moderator,Seer"},
    13: {"content": "Seer, close your eyes",
         "send_to": "Moderator",
         "restricted_to": ""},
    # The 1-st daytime
    14: {"content": """It's daytime. Everyone woke up except those who had been killed.""",
         "send_to": "Moderator",
         "restricted_to": ""},
    15: {"content": "{player_current_dead} was killed last night!",
         "send_to": "Moderator",
         "restricted_to": ""},
    16: {"content": """Living players: {living_players}, now freely talk about the current situation based on your observation and
                    reflection with a few sentences. Decide whether to reveal your identity based on your reflection.""",
         "send_to": "",  # send to all to speak in daytime
         "restricted_to": ""},
    17: {"content": """Now vote and tell me who you think is the werewolf. Don’t mention your role.
                    You only choose one from the following living options please:
                    {living_players}. Say ONLY: I vote to eliminate ...""",
         "send_to": "",
         "restricted_to": ""},
    18: {"content": """{player_current_dead} was eliminated.""",
         "send_to": "Moderator",
         "restricted_to": ""},
}

GAME_RULE = '''
## Game Overview
You're the moderator of a text-based game called Werewolf. Your role is to guide the players, who can be a werewolf, villager, seer, guard, or witch. The game has two phases: night and day.

## PLAYER Night Phase
During the night, conversations are private. Players use their abilities:
- Werewolves vote to kill a player.
- The witch can save a player targeted by werewolves or poison a player (each ability can be used once).
- The seer can verify if a player is a werewolf.
- The guard can protect a player from being killed by werewolves.

## PLAYER Day Phase
During the day, all players discuss and vote to eliminate a suspected werewolf. You'll announce who is killed.

## Roles and Objectives
Werewolves aim to kill all non-werewolves. All other roles aim to eliminate all werewolves. Killed players are out of the game.

## Your Role
As the moderator of the Werewolf game, you'll provide step-by-step instructions to players in this order: 
All(Night) -> Guard -> Werewolf -> Witch -> Seer -> All(Daytime) -> All(Discuss) -> All(Vote). 
Ensure each player understands their instructions before moving on.
'''
# 游戏流程：All(Night) -> Guard -> Werewolf -> Witch -> Seer -> All(Daytime) -> All(Discuss) -> All(Vote).

GENERATE_POSSIBLE_ANSWER = '''
Given the game rules and conversations above, as moderator, ensure each player understands their instruction before moving on.
Generate a correct instruction based on the context. The instruction should use no more than 2 sentences.

The current player status is as follows:
living players:{living_players}, for Werewolf to choose to kill, and for Seer to verify, and for Guard to protect, and for Witch to poison
werewolf players:{werewolf_players}, for Werewolf to know who is the other werewolf
player hunted:{player_hunted}, for Witch to know who is hunted, then decide to save
player current dead:{player_current_dead}, for all players to know who is dead

Response should have the following format(split by ## ):
## Instruction
The 'Instruction' is the instruction from the moderator. It contains the valuable information that the player needs to know. Such as living players, werewolf players, player hunted, player current dead etc.

## Send To
'Send To' specifies the player(s) who need to process and respond to a message.
Using 'Moderator' to send the message to all players and let moderator to process the message.
Using empty string '' to let all players to process the message.
Otherwise, specify the player profile to let the player to process the message. 
But don't reveal the player's name! For example, 'Moderator' or '' or 'Werewolf' or 'Seer' or 'Guard' or 'Witch' etc.

## Day Or Night
'Day Or Night' specifies the time when the message is sent. It should be 'Day' or 'Night'.
'''


class InstructSpeak(Action):
    def __init__(self, name="InstructSpeak", context=None, llm=None):
        super().__init__(name, context, llm)

    async def run(self, mode, living_players, werewolf_players, player_hunted, player_current_dead, **kwargs):
        if mode == "manual":
            return await self.run_manual(living_players, werewolf_players, player_hunted, player_current_dead, **kwargs)
        elif mode == "llm":
            return await self.run_llm(living_players, werewolf_players, player_hunted, player_current_dead, **kwargs)

    async def run_manual(self, living_players, werewolf_players, player_hunted, player_current_dead, **kwargs):
        step_idx = kwargs.get("step_idx", 0)
        instruction_info = STEP_INSTRUCTIONS.get(step_idx, {
            "content": "Unknown instruction.",
            "send_to": "",
            "restricted_to": ""
        })
        content = instruction_info["content"]
        if "{living_players}" in content and "{werewolf_players}" in content:
            content = content.format(living_players=living_players,
                                     werewolf_players=werewolf_players)
        if "{living_players}" in content:
            content = content.format(living_players=living_players)
        if "{werewolf_players}" in content:
            content = content.format(werewolf_players=werewolf_players)
        if "{player_hunted}" in content:
            content = content.format(player_hunted=player_hunted)
        if "{player_current_dead}" in content:
            player_current_dead = "No one" if not player_current_dead else player_current_dead
            content = content.format(player_current_dead=player_current_dead)

        return content, instruction_info["send_to"], instruction_info["restricted_to"]

    # 若是llm模式，将多返回一个flag字段
    async def run_llm(self, living_players, werewolf_players, player_hunted, player_current_dead, **kwargs):
        conversation = kwargs.get("conversation", "")
        pre_flag_info = kwargs.get("pre_flag_info", "")
        pre_day_or_night = pre_flag_info.get("day_or_night", "") if pre_flag_info else ""
        prompt = GAME_RULE + str(conversation)[:4000] + GENERATE_POSSIBLE_ANSWER.format(
            living_players=",".join(living_players),
            werewolf_players=",".join(werewolf_players),
            player_hunted=player_hunted,
            player_current_dead=player_current_dead,
        )
        rsp = await self._aask(prompt)
        # 提取content, send_to, restricted_to
        content = re.search(r"## Instruction\n(.*?)##", rsp, re.DOTALL).group(1).strip()
        # 将内部的单引号去掉
        send_to = re.search(r"## Send To\n(.*?)##", rsp, re.DOTALL).group(1).strip().replace("'", "")
        # restricted_to = re.search(r"## Restricted To\n(.*?)##", rsp, re.DOTALL).group(1).strip()
        restricted_to = ""
        day_or_night = re.search(r"## Day Or Night\n(.*)", rsp, re.DOTALL).group(1).strip()
        flag = False
        if day_or_night != pre_day_or_night and pre_day_or_night != "":
            flag = True
        flag_info = {"flag": flag, "day_or_night": day_or_night}
        if day_or_night == "Night":
            if send_to == "Moderator":
                restricted_to = ""
            elif send_to in ["Werewolf", "Seer", "Guard", "Witch"]:
                restricted_to = "Moderator," + send_to
        elif day_or_night == "Day":
            restricted_to = ""

        return content, send_to, restricted_to, flag_info


class ParseSpeak(Action):
    def __init__(self, name="ParseSpeak", context=None, llm=None):
        super().__init__(name, context, llm)

    async def run(self):
        pass


class SummarizeDay(Action):
    """consider all votes at day, conclude which player dies"""

    def __init__(self, name="SummarizeDay", context=None, llm=None):
        super().__init__(name, context, llm)

    async def run(self, votes):
        # 假设votes是一个字典，代表白天投票的结果，key是被投票的玩家，value是得票数
        # 例如：{"Player1": 2, "Player2": 1, "Player3": 1, "Player4": 0}
        # 表示Player1得到2票，Player2和Player3各得到1票，Player4得到0票
        # 若平票，则随机选一个人出局
        if not votes:
            return "No votes were cast. No one was killed."

        max_votes = max(votes.values())
        players_with_max_votes = [player for player, vote_count in votes.items() if vote_count == max_votes]

        if len(players_with_max_votes) == 1:
            eliminated_player = players_with_max_votes[0]
            return f"{eliminated_player} was voted out and eliminated."
        else:
            # 若平票，则随机选一个人出局
            eliminated_player = players_with_max_votes[int(random() * len(players_with_max_votes))]
            return f"There was a tie in the votes. {eliminated_player} was randomly chosen and eliminated."


class AnnounceGameResult(Action):

    async def run(self, winner: str, win_reason: str):
        return f"Game over! {win_reason}. The winner is the {winner}"

async def main():
    rst1 = await SummarizeDay().run({"Player1": 0, "Player2": 0, "Player3": 0, "Player4": 0})
    print(rst1)

if __name__ == '__main__':
    asyncio.run(main())
