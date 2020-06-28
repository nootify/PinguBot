import json
import logging

import aiohttp
from discord.ext import commands, tasks


class Schedules(commands.Cog):
    """Information about courses at NJIT"""
    def __init__(self, bot):
        self.bot = bot
        self.current_semester = None
        self.selected_semester = None
        self.semester_terms = None
        self.course_url = "https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term="
        self.schedule_updater.start()
        self.log = logging.getLogger(__name__)

    def cog_unload(self):
        self.log.info("Cog and course schedule data unloaded from memory; course schedule updater no longer running")
        self.schedule_updater.cancel()

    @tasks.loop(minutes=30)
    async def schedule_updater(self):
        self.log.info("Running course schedule updater...")
        try:
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.course_url) as response:
                    if response.status == 200:
                        data = await response.text()
                        data = data[7:-1]  # Trims off the call to "define()" that surrounds the JSON
                        self.bot.njit_course_schedules = json.loads(data)
                        self.log.info("Latest course schedule data successfully loaded into memory")
                    else:
                        self.log.error(f"NJIT endpoint responded with HTTP {response.status}")
        except Exception as err:
            self.log.error(f"{type(err).__name__}: {err}")

    @schedule_updater.before_loop
    async def prepare_updater(self):
        await self.bot.wait_until_ready()

    # .after_loop only runs after the task is completely finished (and not looping)
    @schedule_updater.after_loop
    async def check_updater(self):
        if self.schedule_updater.is_being_cancelled():
            self.current_semester = None
            self.selected_semester = None
            self.semester_terms = None
            self.bot.njit_course_schedules = {}

    @commands.command(name="course")
    async def get_course(self, ctx, course_number: str, *, requested_semester=None):
        if len(self.bot.njit_course_schedules) == 0:
            raise commands.CommandError("Course data was not retrieved. Please try again later.")

        # Get the current semester in human-readable form (only runs once per module load)
        if self.current_semester is None:
            self.current_semester = str(self.bot.njit_course_schedules["ct"])
            self.semester_terms = self.bot.njit_course_schedules["ts"]["WSRESPONSE"]["SOAXREF"]
            for term in self.semester_terms:
                if term["EDIVALUE"] == self.current_semester:
                    self.current_semester = term["DESCRIPTION"]
                    break

        # Check if a semester other than the latest was specified
        if requested_semester is not None:
            self.selected_semester = None
            for term in self.semester_terms:
                if term["DESCRIPTION"].lower() == requested_semester.lower():
                    self.selected_semester = term["DESCRIPTION"]
                    self.log.info(f"{self.selected_semester} selected")
                    break
            if self.selected_semester is None:
                raise commands.CommandError("Specified semester does not exist.")
        else:
            self.selected_semester = self.current_semester

        # Match all sections with the given course number
        matches = []
        course_number = course_number.upper()
        course_prefix = course_number[:-3]
        course_data = self.bot.njit_course_schedules["ws"]["WSRESPONSE"]["Subject"]
        for subject in course_data:
            current_subject = subject["SUBJ"]
            if course_prefix == current_subject:
                all_courses = subject["Course"]
                for course in all_courses:
                    if course_number == course["COURSE"]:
                        all_sections = course["Section"]
                        if type(all_sections) == list:
                            for section in all_sections:
                                matches.append(section)
                        elif type(all_sections) == dict:
                            matches.append(all_sections)

        if len(matches) == 0:
            raise commands.CommandError("Specified course was not found.")

        # Semester info (header)
        output = f":calendar_spiral: {self.selected_semester} - {course_number}\n"
        # Course schedules (body)
        SECTION_PADDING = 9
        INSTRUCTOR_PADDING = max(len(section["INSTRUCTOR"]) for section in matches) + 2
        STATUS_PADDING = 8
        METHOD_PADDING = 3
        output += "```"
        output += (f"{'SECTION'.ljust(SECTION_PADDING)}"
                   f"{'INSTRUCTOR'.ljust(INSTRUCTOR_PADDING)}"
                   f"{'STATUS'.ljust(STATUS_PADDING)}"
                   f"METHOD\n")
        for section in matches:
            if section['INSTRUCTOR'] == ', ':
                output += (f"{section['SECTION'].ljust(SECTION_PADDING)}"
                           f"{'<No Instructor>'.ljust(INSTRUCTOR_PADDING)}"
                           f"{int(section['ENROLLED']):02d}/{int(section['CAPACITY']):02d}{''.ljust(METHOD_PADDING)}"
                           f"{section['INSTRUCTIONMETHOD']}\n")
            else:
                output += (f"{section['SECTION'].ljust(SECTION_PADDING)}"
                           f"{section['INSTRUCTOR'].ljust(INSTRUCTOR_PADDING)}"
                           f"{int(section['ENROLLED']):02d}/{int(section['CAPACITY']):02d}{''.ljust(METHOD_PADDING)}"
                           f"{section['INSTRUCTIONMETHOD']}\n")
        output += "```"
        await ctx.send(output)


def setup(bot):
    bot.add_cog(Schedules(bot))
