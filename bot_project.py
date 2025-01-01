import discord
import datetime
import json
from typing import Tuple

# TGBot works as follows:
# Only pay attention to the tele-godella chat
# When a message is sent in this channel, it must have 2 things
# - A photo
# - An @someone_else
# When this happens, watch that message
# If the person who is @ in the message reacts to it, the other person gets points
# Consider inverse of above (variable?)

# Describes a snipe made by a player
class Snipe:
    # Snipes have a lot of information connected to them
    def __init__(self, load: discord.Message | list, mult: float = 1.0):
        if isinstance(load, discord.Message):
            # Time taken (can't be edited)
            self._time = load.created_at
            # ID of the author of the snipe (can't be edited)
            self._sniper = load.author.id
            # IDs of the players who got sniped (can't be edited)
            self._targets = list(set(map(lambda n: n.id, load.mentions)))
            # Number of points per player (P3) (can be edited)
            self._p3 = mult
            # Link to the message (can't be edited)
            self._link = load.jump_url
            # ID of the message (can't be edited)
            self._id = load.id
            # Shows which targets listed are awarding points (can be edited)
            self._validity = [True for _ in range(len(self._targets))]
        else:
            self._time = datetime.datetime.fromisoformat(load[0])
            self._sniper = load[1]
            self._targets = load[2]
            self._p3 = load[3]
            self._link = load[4]
            self._id = load[5]
            self._validity = load[6]

    def get_time(self) -> datetime.datetime:
        return self._time

    def get_sniper(self) -> int:
        return self._sniper

    def get_targets(self) -> list:
        return self._targets

    def get_p3(self) -> float:
        return self._p3

    def inverse_p3(self):
        self._p3 = -self._p3

    def get_link(self) -> str:
        return self._link

    def get_id(self) -> int:
        return self._id

    def get_validity(self) -> list:
        return self._validity

    # Marks a user with the given id as not valid
    # If the person is not a target, does nothing
    def set_validity(self, id, value: bool):
        for i, t_id in enumerate(self._targets):
            if t_id == id:
                self._validity[i] = value
                break

    # JSON serializeable list
    def listify(self):
        return [
            self._time.isoformat(),
            self._sniper,
            self._targets,
            self._p3,
            self._link,
            self._id,
            self._validity,
        ]

    def __str__(self):
        return str(self.listify())

# Class forward definitions in python might not be a thing, idk
class TeleBot(discord.Client):
    # If you do not set up the bot, nothing will work
    def set_up(
        self,
        submission_channel="tele-godella",
        leaderboard_channel="bread-board",
        role_name="tele-godeller",
        snipe_file="snipes.json",
    ):
        self.submission_channel = submission_channel
        self.leaderboard_channel = leaderboard_channel
        self.role_name = role_name
        self.snipe_file = snipe_file
        self.load_from_file()

    # Load the snipes file directly into snipes
    # If the file does not exist, load an empty list
    def load_from_file(self):
        self.snipes = []
        self.scores = {}
        self.multiplier = 1.0

        try:
            with open(self.snipe_file, "r") as file:
                for element in json.loads(file.read()):
                    snipe = Snipe(element)
                    self.snipes.append(snipe)
                    self.update_scoreboard(snipe)

                # TODO when you have guild-specific stuff this can work
                # self.print_scoreboard()

                # Default multiplier to most recently used p3
                self.multiplier = self.snipes[-1].get_p3()
        except FileNotFoundError:
            pass
        except IndexError:
            pass

    # Essentially just show that the bot is ready
    async def on_ready(self):
        print(f"Logged on as {self.user}!")

    # This is where most of the game is played
    async def on_message(self, message: discord.Message):
        # Check if this is in a dm, and ignore if it is
        if isinstance(message.channel, discord.DMChannel):
            return

        # If this is not in the TG channel
        if message.channel.name != self.submission_channel:
            return

        # If this message was sent by the bot itself ignore it
        if message.author.id == self.user.id:
            return

        # Check if author has the "Manage Messages permission"
        if message.author.guild_permissions.manage_messages:
            # Run commands
            if message.content.startswith("!TG"):
                # Commands are deleted
                cmd_args = message.content.split(" ")
                if cmd_args[1] == "mult":
                    try:
                        new_mult = float(cmd_args[2])
                        self.multiplier = new_mult
                        await self.print_scoreboard(message.guild)
                    except ValueError:
                        await message.author.send("You must give a valid multiplier.")
                elif cmd_args[1] == "reload":
                    self.load_from_file()
                    await self.print_scoreboard(message.guild)
                else:
                    await message.author.send("That is not a command.")

                await message.delete()
                return

        validation = self.validate_submission(message)

        if validation[0]:
            await self.record_snipe(message)
        else:
            # Send validation[1] as a DM to the author of the message
            await message.author.send(validation[1])
            await message.delete()

    def validate_submission(self, message: discord.Message) -> Tuple[bool, str]:
        # If this was not sent by a player
        if not self.is_player(message.author):
            return (False, "You must be a TG player to send messages here!")

        # If there is an attachment with the message
        if len(message.attachments) == 0:
            return (False, "You must send the picture you took!")

        # Return whatever the result of the mention check is
        return self.validate_mentions(message)

    # Takaes a Member object and returns if they have the player role
    def is_player(self, member: discord.Member) -> bool:
        return self.role_name in list(map(str, member.roles))

    # Takes a message and returns if it is all valid mentions
    # Also returns an error message to print if bool is False
    def validate_mentions(self, message: discord.Message) -> Tuple[bool, str]:
        # There must be at least one mention
        if len(message.mentions) > 0:
            # The author of the mention must not be mentioned
            if message.author not in message.mentions:
                # All members mentioned must be players
                if all(map(self.is_player, message.mentions)):
                    return (True, "")
                else:
                    return (False, "All mentioned people must be players!")
            else:
                return (False, "You cannot mention yourself in a submission!")
        else:
            return (False, "You must mention the person or people you sniped!")

    # Locally and permanently saves a snipe
    # Assumes that the snipe message has already been validated
    async def record_snipe(self, message: discord.Message):
        # Step 1: Create a Snipe object that has all important info marked
        snipe = Snipe(message, self.multiplier)

        print("Snipe made:", str(snipe))

        # Step 2: Locally record it
        self.snipes.append(snipe)
        self.update_scoreboard(snipe)
        await self.print_scoreboard(message.guild)

        self.save_snipes()

    # Updates the scoreboard variable and message with the given snipe
    def update_scoreboard(self, snipe: Snipe):
        sniper = snipe.get_sniper()
        if sniper not in self.scores:
            self.scores[sniper] = 0

        targets = snipe.get_targets()

        # Give the sniper a positive score if needed
        self.scores[sniper] = max(self.scores[sniper], 0)

        # Add to the sniper's score
        self.scores[sniper] += snipe.get_validity().count(True) * snipe.get_p3()

        if sniper == 692145004348571739:
            print(self.scores[sniper])

        # Take away from the targets' scores, and create board names for them
        for target in targets:
            if target not in self.scores:
                self.scores[target] = 0

            self.scores[target] -= 0.25 * snipe.get_p3()
            if target == 692145004348571739:
                print(self.scores[target])

    async def print_scoreboard(self, guild: discord.Guild):
        # Create list of names first
        longest_row = 0
        player_profiles = []
        for player_id in self.scores.keys():
            user = guild.get_member(player_id)
            try:
                player_profiles.append((user.display_name, max(0, self.scores[player_id])))
            except:
                continue
            longest_row = max(
                longest_row, len(f" {user.display_name}: {self.scores[player_id]} ")
            )

        # Sort by score, descending order
        player_profiles.sort(key=lambda n: n[1], reverse=True)

        # Top row is roughly the same always
        ascii_board = "# The Bread Board\n```"
        ascii_board += "╔════╦" + "═" * longest_row + "╗\n"
        inbetween_line = "╠════╬" + "═" * longest_row + "╣\n"
        for i, entry in enumerate(player_profiles):
            ascii_board += "║ {rank: <2} ║ {name: <{width}} ║\n".format(
                rank=i + 1, name=f"{entry[0]}: {entry[1]}", width=longest_row - 2
            )

            if i == len(player_profiles) - 1:
                ascii_board += "╚════╩" + "═" * longest_row + "╝\n"
            else:
                ascii_board += inbetween_line

        ascii_board += f"```\n**Current Multiplier: {self.multiplier}**"

        # Check the last message sent in the leaderboard_channel
        for channel in guild.channels:
            if channel.name == self.leaderboard_channel:
                leader_channel = channel
                break
        else:
            print("The leaderboard channel can not been found")
            return

        if not isinstance(leader_channel, discord.TextChannel):
            print("The leaderboard channel is not a text channel")
            return

        if leader_channel.last_message_id is not None:
            try:
                last_message = await leader_channel.fetch_message(
                    leader_channel.last_message_id
                )
                # If it was sent by the bot, edit it to ascii_board
                if last_message.author.id == self.user.id:
                   await last_message.edit(content=ascii_board)
                   return
            except:
                pass
            # Otherwise, send a new message with the content of ascii_board
            await leader_channel.send(content=ascii_board)
        else:
            await leader_channel.send(content=ascii_board)

    def save_snipes(self):
        with open(self.snipe_file, "w") as file:
            snipes_serializable = list(map(lambda snipe: snipe.listify(), self.snipes))
            file.write(json.dumps(snipes_serializable))

    # BUG Any time that someone loses points by being sniped, then gets points,
    # then the original snipe goes away, improperly gains points for not being
    # sniped any more. This is in contrast with what would happen otherwise,
    # With people who do not take a photo between these being 0.25 points down.
    # But consider: who cares.
    async def on_raw_message_delete(self, payload):
        # TODO speed this up
        # TODO add channel check
        deleted_id = payload.message_id
        for i in range(len(self.snipes)):
            if self.snipes[i].get_id() == deleted_id:
                print("Removing: ", deleted_id)
                # Adding inverse p3 is the same as deleting
                self.snipes[i].inverse_p3()
                self.update_scoreboard(self.snipes[i])
                self.snipes.pop(i)
                self.save_snipes()
                await self.print_scoreboard(self.get_guild(payload.guild_id))
                break

    async def on_raw_reaction_add(self, payload):
        await self.handle_reaction(payload, False)

    async def on_raw_reaction_remove(self, payload):
        await self.handle_reaction(payload, True)

    async def handle_reaction(self, payload, is_remove: bool):
        # Check if the removed reaction is a thumbs down on a message in the records
        # If it was, remove that person from the targets list if they are mentioned in the message
        # Then, save to the file
        if payload.emoji.name != "\U0001f44e":
            return

        reacted_id = payload.message_id
        for i in range(len(self.snipes)):
            if self.snipes[i].get_id() == reacted_id:
                # Remove, potentially change, then add
                # CONS redoing this
                self.snipes[i].inverse_p3()
                self.update_scoreboard(self.snipes[i])

                self.snipes[i].set_validity(payload.user_id, is_remove)

                self.snipes[i].inverse_p3()
                self.update_scoreboard(self.snipes[i])

                self.save_snipes()
                await self.print_scoreboard(self.get_guild(payload.guild_id))
                break




intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

client = TeleBot(command_prefix="!TG", intents=intents)
client.set_up()

client.run("<BOT TOKEN>")
