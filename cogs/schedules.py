import json
import logging

import aiohttp
from discord.ext import commands, tasks


class Schedules(commands.Cog):
    """Specifically, NJIT course schedules"""
    def __init__(self, bot):
        self.bot = bot
        self.course_url = 'https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term='
        self.schedule_updater.start()
        self.log = logging.getLogger(__name__)

    def cog_unload(self):
        self.log.info('Cog unloaded from memory; course schedule updater no longer running')
        self.schedule_updater.cancel()

    @tasks.loop(minutes=30)
    async def schedule_updater(self):
        self.log.info('Running course schedule updater...')
        try:
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.course_url) as response:
                    if response.status == 200:
                        data = await response.text()
                        data = data[7:-1]  # Trims off the call to 'define()' that surrounds the JSON
                        self.bot.njit_course_schedules = json.loads(data)
                        self.log.info('Latest course schedule data successfully loaded into memory')
                    else:
                        self.log.error(f"NJIT endpoint responded with HTTP {response.status}")
        except Exception as err:
            self.log.error(f"{type(err).__name__}: {err}")

    @schedule_updater.before_loop
    async def prepare_updater(self):
        await self.bot.wait_until_ready()

    # @schedule_updater.after_loop
    # async def check_updater(self):
    #     if self.schedule_updater.failed():
    #

    @commands.command(name='course')
    async def get_course(self, ctx):
        if len(self.bot.njit_course_schedules) == 0:
            await ctx.send(f"{self.bot.icons['fail']} Course data was not retrieved. Please try again later.")
        else:
            semester_terms = self.bot.njit_course_schedules['ts']['WSRESPONSE']['SOAXREF']

            for term in semester_terms:
                if str(term['EDIVALUE']) == str(self.bot.njit_course_schedules['ct']):
                    await ctx.send(f"Current Semester: {term['DESCRIPTION']}")
                print(term)


def setup(bot):
    bot.add_cog(Schedules(bot))
