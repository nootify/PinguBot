"""This module houses an alternative to the official NJIT course catalog browser."""
import asyncio
import json
import logging
import os
from datetime import datetime

import aiofiles
import aiohttp
from discord.ext import commands, tasks
from prettytable import PrettyTable, PLAIN_COLUMNS


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
                self.log.debug("Cache file '%s' loaded into '%s'", filename, memory_location)

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
                self.log.debug("Semester code table refreshed (current semester is '%s')",
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
            self.log.debug("Cleared cached data from memory")

    @commands.command(name="course")
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.member)
    async def get_course(self, ctx, req_course: str, *, req_semester: str = None):
        """Retrieves information about a course based on the semester"""
        # Ensure that the schedule data has been retrieved and is loaded in memory
        if not self.schedule_data or len(self.schedule_data) == 0:
            raise commands.BadArgument("Schedule data not available. Try again later.")

        # Check the requested semester is valid
        # If not specified, default to current semester
        selected_course = req_course.upper()
        if req_semester is not None:
            selected_semester = req_semester.lower()
            codes_reversed = dict((desc, code) for code, desc in self.semester_codes.items())
            if selected_semester not in codes_reversed:
                raise commands.BadArgument("Requested semester does not exist.")
            selected_semester = codes_reversed[selected_semester]
        else:
            selected_semester = self.current_semester
        self.log.debug("'%s' (%s) was selected",
                       self.semester_codes[selected_semester],
                       selected_semester)

        def get_sections(semester_code: str, selected_course: str):
            """Retrieves all of the matching sections for a given course in a single list

            :param str semester_code: The semester to retrieve the schedule data from
            :param str selected_course: The course to look for in the semester data
            :return: All of the matching sections of a course in that semester
            :rtype: list
            """
            selected_prefix = selected_course[:-3]
            semester_data = self.schedule_data[semester_code]["ws"]["WSRESPONSE"]["Subject"]

            # Unpack the inner list from the outer list
            # If the course does not exist, return an empty list
            [matching_courses] = [subject["Course"] for subject in semester_data
                                  if selected_prefix == subject["SUBJ"]] or [[]]
            matching_sections = [course["Section"] for course in matching_courses
                                 if selected_course == course["COURSE"]]

            # Reformat all matches into a single list
            matches = []
            for section in matching_sections:
                if isinstance(section, list):
                    matches.extend(section)  # List of sections
                elif isinstance(section, dict):
                    matches.append(section)  # Single section
                else:
                    self.log.error("An unknown data structure was parsed for %s - %s",
                                   selected_course,
                                   section)
            return matches

        # Error check if the course exists for that semester
        course_sections = get_sections(selected_semester, selected_course)
        if len(course_sections) == 0:
            raise commands.BadArgument("Specified course was not found.")

        # Create and format the table
        unknown = "<Unassigned>"
        instructor_column_size = max(len(section["INSTRUCTOR"].split(",", 1)[0])
                                     for section in course_sections) + 1
        schedule_display = PrettyTable()
        schedule_display.set_style(PLAIN_COLUMNS)
        schedule_display.field_names = ["SEC", "INSTRUCTOR", "SEATS", "TYPE", "MEETING TIMES"]
        schedule_display.align["SEATS"] = "l"
        schedule_display.align["MEETING TIMES"] = "r"
        schedule_display.left_padding_width = 1
        schedule_display.right_padding_width = 1
        schedule_display._max_width = {"INSTRUCTOR": instructor_column_size # pylint: disable=protected-access
                                                     if instructor_column_size >= len(unknown)
                                                     else len(unknown)}

        # Create the table header
        course_titles = set(section["TITLE"] for section in course_sections
                            if "honors" not in section["TITLE"].lower())
        header = ":calendar_spiral: {} - {} ({})\n".format(
            self.semester_codes[selected_semester].title(),
            selected_course,
            " / ".join(course_titles))

        def process_meeting_times(data, course_num: str, section_num: str):
            """Helper function that formats the meeting time hours of a section."""
            output = "-------------"
            # Format times to standard 12-hour instead of 24-hour
            try:
                if isinstance(data, list):
                    meetings = [(data["MTG_DAYS"],
                                 datetime.strptime(data["START_TIME"], "%H%M").strftime("%I:%M %p"),
                                 datetime.strptime(data["END_TIME"], "%H%M").strftime("%I:%M %p"))
                                 for meeting in data]
                    output = "\n".join("{}: {} - {}".format(*meeting) for meeting in meetings)
                elif isinstance(data, dict) and len(data) > 1:
                    output = "{}: {} - {}".format(
                        data["MTG_DAYS"],
                        datetime.strptime(data["START_TIME"], "%H%M").strftime("%I:%M %p"),
                        datetime.strptime(data["END_TIME"], "%H%M").strftime("%I:%M %p"))
            except KeyError:
                self.log.error("Missing schedule data for %s - %s", course_num, section_num)
                output = "MISSING DATA"

            return output

        # Process each section and add it to the table
        for section in course_sections:
            instructor = section["INSTRUCTOR"] if section["INSTRUCTOR"] != ", " else unknown
            seats = f"{section['ENROLLED']}/{section['CAPACITY']}"
            meeting_times = process_meeting_times(
                section["Schedule"] if "Schedule" in section else None,
                selected_course,
                section["SECTION"])
            schedule_display.add_row([section["SECTION"],
                                      instructor,
                                      seats,
                                      section["INSTRUCTIONMETHOD"].replace(" ", "\n"),
                                      meeting_times])

        # In a future version of discord.py (v1.5 or v2.0), this will be replaced
        # with the library's built-in paginator
        def shrink_output(table: PrettyTable, start: int, lines: int, is_header: bool):
            """Shrink the text to be under Discord's max message length of 2000 characters"""
            output = f"```{table.get_string(start=start, end=start+lines, header=is_header)}```"
            while len(output) > 2000:
                lines -= 1
                output = f"```{table.get_string(start=start, end=start+lines, header=is_header)}```"
            return output, lines

        # Paginate table output
        await ctx.send(header)
        max_lines = 20
        counter = 0
        output, max_lines = shrink_output(schedule_display, counter, max_lines, True)
        while len(output) > 6:
            await ctx.send(output)
            await asyncio.sleep(1)
            counter += max_lines
            output, max_lines = shrink_output(schedule_display, counter, max_lines, False)

    @get_course.error
    async def get_course_error(self, ctx, error):
        """Error checking the parameters of the get_course command."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{self.bot.icons['fail']} No course number was specified.")


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Schedules(bot))
