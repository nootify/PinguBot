"""This module houses an alternative to the official NJIT course catalog browser."""
import asyncio
import json
import logging
import os
from datetime import datetime

import aiofiles
import aiohttp
from discord.ext import commands, tasks


class Schedules(commands.Cog):
    """Information about courses at NJIT"""
    def __init__(self, bot):
        self.bot = bot
        self.base_endpoint = "https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term=" # pylint: disable=line-too-long
        self.current_semester = None
        self.schedule_data = None
        self.semester_codes = None
        self.schedule_updater.add_exception_type(FileNotFoundError) # pylint: disable=no-member
        self.schedule_updater.start() # pylint: disable=no-member
        self.log = logging.getLogger(__name__)

    def cog_unload(self):
        self.schedule_updater.cancel() # pylint: disable=no-member
        self.log.info("Cog unloaded; schedule updater no longer running")

    @tasks.loop(minutes=15)
    async def schedule_updater(self):
        """Retrieves schedule data from the current and previous semester."""

        async def update_cache_file(filename: str, endpoint: str) -> None:
            """Updates the requested cache file with the latest response from the endpoint.

            :param str filename: Location of the cache file
            :param str endpoint: URL to request the cache from
            """
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
                            self.log.error(
                                "Could not retrieve data for '%s'; endpoint responded with HTTP %s",
                                filename,
                                response.status)
            except Exception as exc: # pylint: disable=broad-except
                self.log.error("Could not update cache file: %s: %s", type(exc).__name__, exc)
            else:
                self.log.info("Cache file '%s' updated with latest data", filename)

        async def check_cache_file(filename: str, endpoint: str) -> None:
            """Check the state of the cache file on disk, then perform actions as necessary.

            :param str filename: Location of the cache file
            :param str endpoint: URL to request the cache from
            """
            if os.path.exists(filename):
                now = datetime.now()
                cache_file_time = datetime.fromtimestamp(os.path.getmtime(filename))
                last_updated = (now - cache_file_time).total_seconds()
                # print(last_updated)
                # Only send a request if the cached file is an hour old or older (3600+ seconds)
                if last_updated >= 3600:
                    self.log.info("Cache file '%s' is stale; updating schedule data", filename)
                    await update_cache_file(filename, endpoint)
                else:
                    self.log.info("Cache file '%s' is too fresh; keeping current schedule data",
                                  filename)
            else:
                self.log.info("Cache file '%s' not found; downloading schedule data", filename)
                await update_cache_file(filename, endpoint)

        async def update_cache_memory(filename: str, memory_location: str) -> None:
            """Load and parse a cache file into memory.

            :param str filename: Location of the cache file
            :param str memory_location: The key used to store the data in memory
            """
            async with aiofiles.open(filename, "r") as cache_file:
                # json.loads requires bytes/string data
                # json.load requires a file object
                data = await cache_file.read()
                if self.schedule_data is None:
                    self.schedule_data = {memory_location: json.loads(data)}
                else:
                    self.schedule_data[memory_location] = json.loads(data)
                self.log.info("Cache file '%s' loaded into '%s'", filename, memory_location)

        async def update_cache(filename: str, endpoint: str, memory_location: str) -> None:
            """Helper function that combines all of the previous subroutines.
            Also updates the semester code table and moves the "latest" cache file
            to its correct location.

            :param str filename: Location of the cache file
            :param str endpoint: URL to request the cache from
            :param str memory_location: The key specifying where to store the JSON in memory
            """
            await check_cache_file(filename, endpoint)
            await update_cache_memory(filename, memory_location)
            if memory_location == "latest":
                # Refresh the semester code lookup table
                loaded_semesters = self.schedule_data[memory_location]["ts"]["WSRESPONSE"]["SOAXREF"] # pylint: disable=line-too-long
                self.current_semester = str(self.schedule_data[memory_location]["ct"])
                self.semester_codes = {semester["EDIVALUE"]: semester["DESCRIPTION"].lower()
                                       for semester in loaded_semesters}
                self.log.info("Semester code table refreshed (current semester is '%s')",
                              self.current_semester)

                # Replace the "latest" key with the actual current semester code
                self.schedule_data[self.current_semester] = self.schedule_data.pop(memory_location)

        # Retrieve the schedule data for the current semester
        base_dirname, base_filename = "cache", "scheduledata.json"
        latest_semester_code = "latest"
        latest_semester_filename = f"{base_dirname}/{latest_semester_code}-{base_filename}"
        await update_cache(latest_semester_filename, self.base_endpoint, latest_semester_code)

        # Retrieve the schedule data for the previous semester
        loaded_semesters = self.schedule_data[self.current_semester]["ts"]["WSRESPONSE"]["SOAXREF"]
        prev_semester_code = max(sem["EDIVALUE"] for sem in loaded_semesters
                                 if sem["EDIVALUE"] != self.current_semester)
        prev_semester_endpoint = f"{self.base_endpoint}{prev_semester_code}"
        prev_semester_filename = f"{base_dirname}/{prev_semester_code}-{base_filename}"
        await update_cache(prev_semester_filename, prev_semester_endpoint, prev_semester_code)

    @schedule_updater.before_loop
    async def prepare_updater(self):
        """Delay schedule updater until the bot is in the ready state."""
        await self.bot.wait_until_ready()

    # .after_loop only runs after the task is completely finished (and not looping)
    @schedule_updater.after_loop
    async def cleanup_updater(self):
        """Unload cached data from memory when the tasks ends."""
        if self.schedule_updater.is_being_cancelled(): # pylint: disable=no-member
            self.current_semester = None
            self.schedule_data = None
            self.semester_codes = None
            self.log.info("Cleared cached data from memory")

    @commands.command(name="course")
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.member)
    async def get_course(self, ctx, req_course: str, req_display: str = "full", *, req_semester: str = None):
        """Retrieves information about a course based on the semester"""

        # TODO: Breakup command into submodules
        display_types = ["less", "full"]
        if req_display.lower() not in display_types:
            raise commands.BadArgument(f"Invalid display format.\n"
                                       f"Command usage: `{self.bot.command_prefix}course less/full <course_number>`")

        if len(self.schedule_data) == 0:
            raise commands.BadArgument("Course data was not retrieved yet. Try again later.")

        # Check if a semester other than the latest was specified
        if req_semester is not None:
            selected_semester = req_semester.lower()

            # Reversed the key and values of the original lookup table
            semester_descriptions = dict((desc, code) for code, desc in self.semester_codes.items())
            if selected_semester not in semester_descriptions:
                raise commands.BadArgument("Specified semester does not exist.")

            selected_semester = semester_descriptions[selected_semester]
        else:
            selected_semester = self.current_semester
        self.log.info("'%s' was selected", selected_semester)


        # Match all sections with the given course number
        matches = []
        req_course = req_course.upper()
        course_prefix = req_course[:-3]  # e.g. CS, HIST, YWCC, etc.
        course_data = self.schedule_data[selected_semester]["ws"]["WSRESPONSE"]["Subject"]
        for subject in course_data:
            current_subject = subject["SUBJ"]
            if course_prefix == current_subject:
                all_courses = subject["Course"]
                for course in all_courses:
                    course_number = course["COURSE"]
                    if req_course == course_number:
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
        if req_display == "full":
            course_titles = set(match["TITLE"] for match in matches)
            output = f":calendar_spiral: {selected_semester} - {req_course} ({' / '.join(course_titles)})\n"
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
                if isinstance(schedule_data, list):
                    # Format times to standard 12-hour instead of 24-hour
                    schedule_output = ", ".join(f"{schedule['MTG_DAYS']}:"
                                                f" {datetime.strptime(schedule['START_TIME'], '%H%M').strftime('%I:%M %p')}"
                                                f" - {datetime.strptime(schedule['END_TIME'], '%H%M').strftime('%I:%M %p')}"
                                                for schedule in schedule_data)
                elif isinstance(schedule_data, dict) and len(schedule_data) > 1:
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
        elif req_display == "less":
            course_title = list(set(match["TITLE"] for match in matches if "honors" not in match["TITLE"].lower()))
            output = f":calendar_spiral: {selected_semester} - {req_course}\n({course_title[0]})\n"

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
            if error.param.name == "req_display":
                await ctx.send(f"{self.bot.icons['fail']} No display format was specified.\n"
                               f"Command usage: `{self.bot.command_prefix}course less/full <course_number>`")
            else:
                await ctx.send(f"{self.bot.icons['fail']} No course was specified.")


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Schedules(bot))
