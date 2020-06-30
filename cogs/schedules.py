import asyncio
import json
import logging
from datetime import datetime

import aiohttp
from discord.ext import commands, tasks


class Schedules(commands.Cog):
    """Information about courses at NJIT"""
    def __init__(self, bot):
        self.bot = bot
        self.available_semesters = {}
        self.current_semester = None
        self.selected_semester = None
        self.default_endpoint = "https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term="
        self.schedule_updater.start()
        self.log = logging.getLogger(__name__)

    def cog_unload(self):
        self.log.info("Cog and course schedule data unloaded from memory; course schedule updater no longer running")
        self.schedule_updater.cancel()

    @tasks.loop(minutes=60)
    async def schedule_updater(self):
        filtered_years = ["2019", "2020"]
        self.log.info(f"Running course schedule updater for year(s) {', '.join(filtered_years)}...")
        try:
            timeout = aiohttp.ClientTimeout(total=60.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.default_endpoint) as response:
                    if response.status == 200:
                        data = await response.text()
                        data = data[7:-1]  # Trims off the call to "define()" that surrounds the JSON
                        self.bot.njit_course_schedules["latest"] = json.loads(data)
                        self.log.info("Latest course schedule data successfully loaded into memory")

                        # Get all available semesters and parse it into an easier data structure
                        loaded_semesters = self.bot.njit_course_schedules["latest"]["ts"]["WSRESPONSE"]["SOAXREF"]
                        for semester in loaded_semesters:
                            # Filter only to recent years (to prevent long loading/starting up times
                            semester_year = semester["DESCRIPTION"][:4]
                            if semester_year in filtered_years:
                                self.available_semesters[semester["DESCRIPTION"]] = semester["EDIVALUE"]
                        self.log.info("Semester codes successfully loaded into memory")
                    else:
                        self.log.error(f"NJIT endpoint responded with HTTP {response.status}")

                if len(self.available_semesters) > 0:
                    # Encode requests to NJIT using the EDIVALUE of each semester extracted from the first request
                    endpoints = {}
                    for desc, code in self.available_semesters.items():
                        endpoints[f"{self.default_endpoint}{code}"] = desc

                    for endpoint, desc in endpoints.items():
                        async with session.get(endpoint) as response:
                            if response.status == 200:
                                data = await response.text()
                                data = data[7:-1]  # Trims off the call to "define()" that surrounds the JSON
                                self.bot.njit_course_schedules[desc] = json.loads(data)
                                self.log.info(f"{desc} schedule data successfully loaded into memory")
                            else:
                                self.log.error(f"Failed to retrieve {desc}:"
                                               f" NJIT endpoint responded with HTTP {response.status}")
                    self.log.info("Previous semester data loaded into memory")
        except Exception as err:
            self.log.error(f"{type(err).__name__}: {err}")
            raise commands.BadArgument("Something went wrong while getting course information.")

    @schedule_updater.before_loop
    async def prepare_updater(self):
        await self.bot.wait_until_ready()

    # .after_loop only runs after the task is completely finished (and not looping)
    @schedule_updater.after_loop
    async def check_updater(self):
        if self.schedule_updater.is_being_cancelled():
            self.available_semesters = {}
            self.current_semester = None
            self.selected_semester = None
            self.bot.njit_course_schedules = {}

    @commands.command(name="course")
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.member)
    async def get_course(self, ctx, requested_course: str, *, requested_semester=None):
        """Retrieves information about a course based on the semester"""
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
                        if type(all_sections) == list:
                            matches.extend(all_sections)  # List of sections
                        elif type(all_sections) == dict:
                            matches.append(all_sections)  # Single section

        if len(matches) == 0:
            raise commands.BadArgument("Specified course was not found.")

        # Semester info (header)
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

    @get_course.error
    async def get_course_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{self.bot.icons['fail']} No course was specified.")


def setup(bot):
    bot.add_cog(Schedules(bot))
