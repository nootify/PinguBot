"""This module houses an alternative to the official NJIT course catalog browser."""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import aiofiles
import aiohttp
from discord.ext import commands, tasks


class Schedules(commands.Cog):
    """Information about courses at NJIT"""
    def __init__(self, bot):
        self.bot = bot
        self.available_semesters = None
        self.current_semester = None
        self.base_dirname = "cache"
        self.base_endpoint = "https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term=" # pylint: disable=line-too-long
        self.base_filename = "scheduledata.json"
        self.schedule_data = None
        self.schedule_updater.add_exception_type(FileNotFoundError) # pylint: disable=no-member
        self.schedule_updater.start() # pylint: disable=no-member
        self.log = logging.getLogger(__name__)

    def cog_unload(self):
        self.schedule_updater.cancel() # pylint: disable=no-member
        self.log.info("Cog unloaded; schedule updater no longer running")

    @tasks.loop(minutes=60)
    async def schedule_updater(self):
        """Retrieves schedule data from the current and previous semester."""
        async def update_cache_file(filename: str, endpoint: str):
            """Updates the main cache file with the latest response from the endpoint."""
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(endpoint) as response:
                        if response.status == 200:
                            data = await response.text()
                            data = data[7:-1]  # Trim off "define( ... )" that surrounds the JSON
                            async with aiofiles.open(filename, "w") as cache_file:
                                await cache_file.write(data)
                        else:
                            self.log.error("Could not retrieve data for cache file '%s'; NJIT endpoint responded with HTTP %s", filename, response.status)
            except Exception as exc:
                self.log.error("%s: %s", type(exc).__name__, exc)
            else:
                self.log.info("Cache file '%s' updated with latest data", filename)

        async def check_cache_file(filename: str, endpoint: str):
            """Check the state of the cache file on disk, then perform actions as necessary."""
            if os.path.exists(filename):
                self.log.info("Cache file '%s' found", filename)
                now = datetime.now()
                cache_file_timestamp = os.path.getmtime(filename)
                cache_file_datetime = datetime.utcfromtimestamp(cache_file_timestamp)
                # Only send a request if the cache is an hour old or older
                if (cache_file_datetime + timedelta(hours=1)) <= now:
                    self.log.info("Cache file '%s' is stale; updating schedule data", filename)
                    await update_cache_file(filename, endpoint)
                else:
                    self.log.info("Cache file '%s' is too fresh; not updating schedule data", filename)
            else:
                self.log.info("Cache file '%s' not found; downloading schedule data", filename)
                await update_cache_file(filename, endpoint)

        # Retrieve the schedule data for the current semester
        reference_filename = f"{self.base_dirname}/latest-{self.base_filename}"
        await check_cache_file(reference_filename, self.base_endpoint)

        # Load and parse the cached response
        async with aiofiles.open(reference_filename, "r") as cache_file:
            # json.loads requires bytes/string data
            # json.load requires a file object
            data = await cache_file.read()
            self.schedule_data = json.loads(data)
            self.log.info("Schedule data for the current semester loaded into memory")

        # Create the semester code lookup table
        retrieved_semesters = self.schedule_data["ts"]["WSRESPONSE"]["SOAXREF"]
        self.current_semester = str(self.schedule_data["ct"])
        self.available_semesters = {sem["EDIVALUE"]: sem["DESCRIPTION"].lower() for sem in retrieved_semesters}
        self.log.info("Semester codes and description names loaded into memory")

        # Retrieve the schedule data for the previous semester
        prev_semester_code = max(sem["EDIVALUE"] for sem in retrieved_semesters if sem["EDIVALUE"] != self.current_semester)
        prev_semester_endpoint = f"{self.base_endpoint}{prev_semester_code}"
        prev_semester_filename = f"{self.base_dirname}/{prev_semester_code}-{self.base_filename}"
        await check_cache_file(prev_semester_filename, prev_semester_endpoint)

    @schedule_updater.before_loop
    async def prepare_updater(self):
        await self.bot.wait_until_ready()

    # .after_loop only runs after the task is completely finished (and not looping)
    @schedule_updater.after_loop
    async def cleanup_updater(self):
        """Unload cached data from memory when the tasks ends."""
        if self.schedule_updater.is_being_cancelled(): # pylint: disable=no-member
            self.available_semesters = None
            self.current_semester = None
            self.schedule_data = None
            self.log.info("Clearing cached data from memory")

    @commands.command(name="course")
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.member)
    async def get_course(self, ctx, requested_display: str, requested_course: str, *, requested_semester=None):
        """Retrieves information about a course based on the semester"""

        # TODO: Breakup command into submodules
        display_types = ["less", "full"]
        if requested_display.lower() not in display_types:
            raise commands.BadArgument(f"Invalid display format.\n"
                                       f"Command usage: `{self.bot.command_prefix}course less/full <course_number>`")

        if len(self.bot.njit_course_schedules) == 0:
            raise commands.BadArgument("Course data was not retrieved. Try again later.")

        # Get the current semester in human-readable form (only runs once per module load)
        if self.current_semester is None:
            self.current_semester = str(self.bot.njit_course_schedules["latest"]["ct"])
            for desc, code in self.available_semesters.items():
                if code == self.current_semester:
                    self.current_semester = desc
                    break

        # Check if a semester other than the latest was specified
        if requested_semester is not None:
            self.selected_semester = None
            for desc, code in self.available_semesters.items():
                if desc.lower() == requested_semester.lower():
                    self.selected_semester = desc
                    break
            if self.selected_semester is None:
                raise commands.BadArgument("Specified semester does not exist.")
        else:
            self.selected_semester = self.current_semester
        self.log.info(f"{self.selected_semester} selected")

        if self.selected_semester not in self.bot.njit_course_schedules:
            raise commands.BadArgument("Course data for this semester was not retrieved. Try again later.")

        # Match all sections with the given course number
        matches = []
        requested_course = requested_course.upper()
        course_prefix = requested_course[:-3]  # e.g. CS, HIST, YWCC, etc.
        course_data = self.bot.njit_course_schedules[self.selected_semester]["ws"]["WSRESPONSE"]["Subject"]
        for subject in course_data:
            current_subject = subject["SUBJ"]
            if course_prefix == current_subject:
                all_courses = subject["Course"]
                for course in all_courses:
                    course_number = course["COURSE"]
                    if requested_course == course_number:
                        all_sections = course["Section"]
                        # The NJIT endpoint does not have consistent structure of data
                        if isinstance(all_sections, list):
                            matches.extend(all_sections)  # List of sections
                        elif isinstance(all_sections, dict):
                            matches.append(all_sections)  # Single section
                        else:
                            self.log.error("An unknown data structure was parsed for %s - %s", course_number, all_sections)

        if len(matches) == 0:
            raise commands.BadArgument("Specified course was not found.")

        # Format to desktop users (shows complete information)
        # Semester info (header)
        if requested_display == "full":
            course_titles = set(match["TITLE"] for match in matches)
            output = f":calendar_spiral: {self.selected_semester} - {requested_course} ({' / '.join(course_titles)})\n"
            # Course schedules (body header)
            SECTION_PADDING = 9
            INSTRUCTOR_PADDING = max(len(section["INSTRUCTOR"]) for section in matches) + 2
            SEATS_PADDING = 7
            TYPE_PADDING = max(len(section["INSTRUCTIONMETHOD"]) for section in matches) + 2
            if INSTRUCTOR_PADDING < (len("<No Instructor>") + 2):  # Fixes rare formatting issue
                INSTRUCTOR_PADDING = len("<No Instructor>") + 2
            output += "```"
            output += (f"{'SECTION'.ljust(SECTION_PADDING)}"
                       f"{'INSTRUCTOR'.ljust(INSTRUCTOR_PADDING)}"
                       f"{'SEATS'.ljust(SEATS_PADDING)}"
                       f"{'TYPE'.ljust(TYPE_PADDING)}"
                       f"MEETING TIMES\n")
            # Course schedules (body content)
            for section in matches:
                # If there is too much data stored, empty buffer and split into multiple messages
                if len(output) >= 1800:
                    output += "```"  # End previous code block
                    await ctx.send(output)
                    await asyncio.sleep(1.0)
                    output = "```"  # Create new code block

                # Catch sections without an assigned instructor and replace it with a placeholder name
                if section["INSTRUCTOR"] == ", ":
                    section["INSTRUCTOR"] = "<No Instructor>"

                # Get meeting times of a particular section
                if "Schedule" in section:
                    schedule_data = section["Schedule"]
                else:
                    schedule_data = None  # Special high-school only sections sometimes appear in the course list
                if type(schedule_data) == list:
                    # Format times to standard 12-hour instead of 24-hour
                    schedule_output = ", ".join(f"{schedule['MTG_DAYS']}:"
                                                f" {datetime.strptime(schedule['START_TIME'], '%H%M').strftime('%I:%M %p')}"
                                                f" - {datetime.strptime(schedule['END_TIME'], '%H%M').strftime('%I:%M %p')}"
                                                for schedule in schedule_data)
                elif type(schedule_data) == dict and len(schedule_data) > 1:
                    schedule_output = (f"{schedule_data['MTG_DAYS']}:"
                                       f" {datetime.strptime(schedule_data['START_TIME'], '%H%M').strftime('%I:%M %p')}"
                                       f" - {datetime.strptime(schedule_data['END_TIME'], '%H%M').strftime('%I:%M %p')}")
                else:
                    # If no meeting times are found, replace with a placeholder line
                    schedule_output = "-------------"

                # Format retrieved information into human readable form
                output += (f"{section['SECTION'].ljust(SECTION_PADDING)}"
                           f"{section['INSTRUCTOR'].ljust(INSTRUCTOR_PADDING)}"
                           f"{int(section['ENROLLED']):02d}/{int(section['CAPACITY']):02d}  "
                           f"{section['INSTRUCTIONMETHOD'].ljust(TYPE_PADDING)}"
                           f"{schedule_output}\n")
            output += "```"
            await ctx.send(output)
        # Format to mobile users (shows compacted information)
        # Semester info (header)
        elif requested_display == "less":
            course_title = list(set(match["TITLE"] for match in matches if "honors" not in match["TITLE"].lower()))
            output = f":calendar_spiral: {self.selected_semester} - {requested_course}\n({course_title[0]})\n"

            def squeeze_name(name: str) -> str:
                """Used to condense the first name to its initial."""
                if name == "<No Instructor>" or name == ", ":
                    return name
                else:
                    last_name, first_name = name.split(", ")
                    compacted_name = f"{last_name}, {first_name[0]}."
                    return compacted_name[:19]

            # Course schedules (body header)
            SECTION_PADDING = 5
            INSTRUCTOR_PADDING = max(len(squeeze_name(section["INSTRUCTOR"])) for section in matches) + 1
            if INSTRUCTOR_PADDING < (len("<No Instructor>") + 1):  # Fixes rare formatting issues
                INSTRUCTOR_PADDING = len("<No Instructor>") + 1
            output += "```"
            output += (f"{'SEC.'.ljust(SECTION_PADDING)}"
                       f"{'INSTRUCTOR'.ljust(INSTRUCTOR_PADDING)}"
                       f"SEATS\n")
            # Course schedules (body content)
            for section in matches:
                # If there is too much data stored, empty buffer and split into multiple messages
                if len(output) >= 1800:
                    output += "```"  # End previous code block
                    await ctx.send(output)
                    await asyncio.sleep(1.0)
                    output = "```"  # Create new code block

                # Catch sections without an assigned instructor and replace it with a placeholder name
                if section["INSTRUCTOR"] == ", ":
                    section["INSTRUCTOR"] = "<No Instructor>"

                # Format retrieved information into human readable form
                output += (f"{section['SECTION'].ljust(SECTION_PADDING)}"
                           f"{squeeze_name(section['INSTRUCTOR']).ljust(INSTRUCTOR_PADDING)}"
                           f"{int(section['ENROLLED']):02d}/{int(section['CAPACITY']):02d}\n")
            output += "```"
            await ctx.send(output)

    @get_course.error
    async def get_course_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "requested_display":
                await ctx.send(f"{self.bot.icons['fail']} No display format was specified.\n"
                               f"Command usage: `{self.bot.command_prefix}course less/full <course_number>`")
            else:
                await ctx.send(f"{self.bot.icons['fail']} No course was specified.")


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Schedules(bot))
