import json
import logging

import aiohttp
from discord.ext import commands, tasks


class Schedules(commands.Cog):
    log = logging.getLogger(__name__)

    def __init__(self, bot):
        self.bot = bot
        self.course_url = 'https://uisnetpr01.njit.edu/courseschedule/alltitlecourselist.aspx?term='
        self.schedule_updater.start()

    def cog_unload(self):
        self.schedule_updater.cancel()

    @tasks.loop(minutes=30)
    async def schedule_updater(self):
        logging.info('Running course schedule updater...')
        async with aiohttp.ClientSession() as session:
            async with session.get(self.course_url) as response:
                if response.status == 200:
                    data = await response.text()
                    data = data[7:-1]  # Trims off the call to 'define()' that surrounds the JSON
                    self.bot.njit_course_schedules = json.loads(data)
                    logging.info('Latest course schedule data successfully loaded into memory!')
                else:
                    logging.error('Course data failed to update.')

    @schedule_updater.before_loop
    async def prepare_updater(self):
        await self.bot.wait_until_ready()

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
