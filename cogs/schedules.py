import json
import logging
from collections import deque
from datetime import datetime, timedelta

import aiohttp
import discord
from discord.ext import commands, tasks

from common.settings import Icons


class Schedules(commands.Cog):
    """Information about courses at NJIT"""

    SCHEDULE_URL = "https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term="
    SEMESTER_CODES = {}
    SEMESTER_DATA = {}
    LATEST_SEMESTER = None
    LAST_UPDATE = {}
    QUEUED_CODES = deque()

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.refresh_cache.start()

    def cog_unload(self):
        self.refresh_cache.cancel()
        Schedules.SEMESTER_DATA = None
        self.log.info("Stopped background task and cleared cached data")

    async def update_schedules(self):
        """Retrieve schedule data from queued operations"""
        while Schedules.QUEUED_CODES:
            semester_code = Schedules.QUEUED_CODES.popleft()
            if semester_code not in Schedules.LAST_UPDATE:
                Schedules.LAST_UPDATE[semester_code] = datetime.fromtimestamp(0)

            time_difference = datetime.utcnow() - Schedules.LAST_UPDATE[semester_code]
            if time_difference >= timedelta(hours=1):
                Schedules.LAST_UPDATE[semester_code] = datetime.utcnow()
                await self.get_semester_data(semester_code)
            else:
                self.log.info(
                    "Not updating '%s' since it was updated %s second(s) ago",
                    semester_code,
                    int(time_difference.total_seconds()),
                )

    @tasks.loop(hours=24)
    async def refresh_cache(self):
        await self.get_semester_data()

    @refresh_cache.before_loop
    async def wait_for_bot(self):
        await self.bot.wait_until_ready()

    async def get_semester_data(self, semester_code: str = None) -> None:
        """Helper function used to update the in-memory cache.

        Passing in a semester code will only get update the data for that semester.
        Passing in None for the semester code will update everything.
        """
        try:
            url_code = "" if not semester_code else semester_code
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(Schedules.SCHEDULE_URL + url_code) as response:
                    if response.status == 200:
                        raw_data = await response.text()
                        # Trim off JSONP and load as dictionary
                        parsed_data = json.loads(raw_data[7:-1])

                        # fmt: off
                        schedule_data = parsed_data["ws"]["WSRESPONSE"]["Subject"]
                        if not semester_code:
                            semester_code_map = parsed_data["ts"]["WSRESPONSE"]["SOAXREF"]
                            # Inconsistent string / integer values from JSON :(
                            Schedules.LATEST_SEMESTER = str(parsed_data["ct"])
                            Schedules.SEMESTER_CODES = {
                                semester["EDIVALUE"]: semester["DESCRIPTION"]
                                for semester in semester_code_map
                            }
                            Schedules.SEMESTER_DATA[Schedules.LATEST_SEMESTER] = schedule_data
                            Schedules.LAST_UPDATE[Schedules.LATEST_SEMESTER] = datetime.utcnow()
                            self.log.info("Latest semester is '%s'", Schedules.LATEST_SEMESTER)
                            self.log.info("Found semester codes: %s", list(Schedules.SEMESTER_CODES.keys()))
                        else:
                            Schedules.SEMESTER_DATA[semester_code] = schedule_data
                        # fmt: on
                        self.log.debug(
                            "Cached semester data: %s",
                            list(Schedules.SEMESTER_DATA.keys()),
                        )
                    else:
                        self.log.error(
                            "Failed to get data for '%s'; server responded with HTTP %s",
                            semester_code,
                            response.status,
                        )
        except Exception as exc:
            self.log.error(
                "Exception occurred while processing '%s' - %s: %s",
                semester_code,
                type(exc).__name__,
                exc,
            )
        else:
            if not semester_code:
                self.log.info("Refreshed all data")
            else:
                self.log.info("Updated '%s' with latest data", semester_code)

    def get_course_sections(self, course_number: str, semester_code: str) -> list:
        """Helper function that gets the sections of a course."""
        # Course number must be capitalized
        prefix = course_number[:-3]
        semester_data = Schedules.SEMESTER_DATA[semester_code]

        # Needlessly complicated JSON structure :(
        matching_course = next(
            (subject["Course"] for subject in semester_data if subject["SUBJ"] == prefix),
            [],
        )
        matching_sections = [course["Section"] for course in matching_course if course["COURSE"] == course_number]

        # Put all sections into a single list
        parsed_sections = []
        for section in matching_sections:
            # The JSON returns single item instead of an array with one item in it
            if isinstance(section, list):
                parsed_sections.extend(section)  # List of sections
            elif isinstance(section, dict):
                parsed_sections.append(section)  # One section
            else:
                self.log.error(
                    "Failed to parse %s - %s (%s)",
                    semester_code,
                    section,
                    type(section),
                )
        return parsed_sections

    def get_meeting_times(self, data, course_num: str, section_num: str) -> str:
        """Helper function that formats the meeting times of a section."""
        output = "• N/A"
        # Format times to standard 12-hour instead of 24-hour
        try:
            if isinstance(data, list):
                meetings = [
                    (
                        meeting["MTG_DAYS"],
                        datetime.strptime(meeting["START_TIME"], "%H%M").strftime("%I:%M %p").lstrip("0"),
                        datetime.strptime(meeting["END_TIME"], "%H%M").strftime("%I:%M %p").lstrip("0"),
                    )
                    for meeting in data
                ]
                output = "\n".join("• {}: {} - {}".format(*meeting) for meeting in meetings)
            elif isinstance(data, dict) and len(data) > 1:
                output = "• {}: {} - {}".format(
                    data["MTG_DAYS"],
                    datetime.strptime(data["START_TIME"], "%H%M").strftime("%I:%M %p").lstrip("0"),
                    datetime.strptime(data["END_TIME"], "%H%M").strftime("%I:%M %p").lstrip("0"),
                )
        except KeyError:
            self.log.error("Missing schedule data for %s - %s", course_num, section_num)
            output = "• Missing Data"

        return output

    def get_schedule_embeds(self, course: str, semester: str, sections: list) -> list:
        """Helper function that allows courses with more than 24 sections to display properly."""
        max_limit = 24

        # Common embed elements
        course_titles = set(section["TITLE"] for section in sections if "honors" not in section["TITLE"].lower())
        header = "{} - {} ({})".format(
            Schedules.SEMESTER_CODES[semester],
            course,
            " / ".join(course_titles),
        )
        if len(sections) <= max_limit:
            schedule_embed = discord.Embed(
                title=header,
                colour=self.bot.embed_colour,
                timestamp=Schedules.LAST_UPDATE[semester],
            )
            schedule_embed.set_footer(text="Last updated")
            for section in sections:
                self.setup_embed(schedule_embed, course, section)

            return [schedule_embed]
        else:
            schedule_embed = discord.Embed(
                title=header,
                colour=self.bot.embed_colour,
            )
            for section in sections[:max_limit]:
                self.setup_embed(schedule_embed, course, section)

            continued_embed = discord.Embed(
                colour=self.bot.embed_colour,
                timestamp=Schedules.LAST_UPDATE[semester],
            )
            continued_embed.set_footer(text="Last updated")
            for section in sections[max_limit:]:
                self.setup_embed(continued_embed, course, section)
            return [schedule_embed, continued_embed]

    def setup_embed(self, embed: discord.Embed, course: str, section: dict) -> None:
        """Helper function to format the schedule information embeds."""
        section_number = section["SECTION"]
        instructor = section["INSTRUCTOR"] if section["INSTRUCTOR"] != ", " else "[Unassigned]"
        filled_seats = section["ENROLLED"]
        max_seats = section["CAPACITY"]
        class_type = section["INSTRUCTIONMETHOD"]
        meeting_times = self.get_meeting_times(
            section["Schedule"] if "Schedule" in section else None,
            course,
            section_number,
        )

        section_title = f"{course}-{section_number}"
        section_info = (
            f"**Instructor:** {instructor}\n"
            + f"**Seats:** {filled_seats}/{max_seats}\n"
            + f"**Meets:** {class_type}\n{meeting_times}"
        )
        embed.add_field(
            name=section_title,
            value=section_info,
            inline=True,
        )

    @commands.command(name="course")
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.member)
    async def course_info(self, ctx, course: str, *, semester: str = None):
        """Get details about a course at NJIT.

        - A specific semester can be chosen with a year and season (e.g. 2017 fall).
        """
        # Ensure that the schedule data has been retrieved and is loaded in memory
        if not Schedules.LATEST_SEMESTER:
            await ctx.send(f"{Icons.WARN} Schedule data not available yet. Try again later.")
            return

        # Validate semester and course
        picked_course = course.upper()
        parsed_semester = semester
        if parsed_semester:
            season_map = {
                "winter": "95",
                "fall": "90",
                "summer": "50",
                "spring": "10",
            }
            parsed_semester = parsed_semester.lower().replace(" ", "")
            year = parsed_semester[:4]
            season = parsed_semester[4:]
            if season not in season_map:
                raise commands.BadArgument("Type the year first and then the season (e.g. 2017 fall).")
            parsed_semester = year + season_map[season]
            self.log.debug("Parsed semester code from user: '%s'", parsed_semester)

        # Default to latest if not specified
        picked_semester = Schedules.LATEST_SEMESTER if not parsed_semester else parsed_semester
        if picked_semester not in Schedules.SEMESTER_CODES:
            raise commands.BadArgument("Semester is not valid or data for this term is unavailable.")

        # Queue for data if it is not cached
        if picked_semester not in Schedules.QUEUED_CODES:
            Schedules.QUEUED_CODES.append(picked_semester)
            info_message = await ctx.send(f"{Icons.ALERT} Getting schedule data...")
            await self.update_schedules()
            await info_message.delete()
        self.log.debug(
            "User requested '%s' (%s)",
            picked_semester,
            Schedules.SEMESTER_CODES[picked_semester],
        )

        # Validate sections for the course
        found_sections = self.get_course_sections(picked_course, picked_semester)
        if not found_sections:
            raise commands.BadArgument("Course number is not valid or unavailable for this semester.")

        # Setup course info embed(s)
        schedule_embeds = self.get_schedule_embeds(picked_course, picked_semester, found_sections)
        for embed in schedule_embeds:
            await ctx.send(embed=embed)

    @course_info.error
    async def course_error_handler(self, ctx: commands.Context, error):
        """Error checking the parameters of the get_course command."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "course":
                await ctx.send(f"{Icons.ERROR} Missing course number.")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}")


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Schedules(bot))
