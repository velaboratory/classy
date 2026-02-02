# classy

Classy is a discord bot for taking attendance, registering for classes on Discord, and sending reminders.

Note, this is currently in alpha stage, and pretty much only works for a very specific Discord/Class configuration.

The way it's currently set up, all classes live inside the same server/guild.  Different roles have access to different channels.  

The bot gives roles if they register for the class.  This can be password protected.

## User Guide

### Student Commands
*   **/register**: Opens a menu to register for a class. You may need a class password. This assigns you the correct role and nickname.
*   **/checkin**: Checks you into the current class session. Must be done inside the class channel during class time.
*   **/attendance**: View your own attendance record.
*   **/queue join**: Join the help queue for the current channel.
*   **/queue leave**: Leave the help queue.
*   **/queue list**: View the current queue.
*   **/ask [question]**: Submit an anonymous question to the channel.

### Instructor/Admin Commands
*   **/poll [question] [options]**: Create a poll.
    *   `question`: The question to ask.
    *   `options`: Comma-separated list of choices (default: Yes, No).
    *   `open_ended`: Set to True for text responses instead of buttons.
*   **/coldcall**: Randomly selects a student who has checked in.
*   **/queue next**: Call the next student in the queue.
*   **/queue clear**: Clear the entire queue.
*   **/attendance**: (Admin only) View the list of students checked in for the current session.

To run classy, you need to create a config.json file in the root with the following:

```json
{
    "key":"YOURBOTKEYFROMDISCORDDEVELOPERPAGE",
    "gemini_api_key": "YOUR_GEMINI_API_KEY (Optional, for AI poll summaries)",
    "classes":
     [
        {
            "name":"INFO2000 Fall 2022",
            "channel":"info2000fa22",
            "role":"INFO2000FA22",
            "password":"",
            "start_date":"8/10/2022",
            "end_date":"12/1/2022",
            "tz":"America/New_York",
            "periods":[{"day":"tuesday","start":"9:35 am","end":"10:50 pm"},{"day":"thursday","start":"9:35 am","end":"10:50 pm"}],
            "exceptions":["11/24/2022"]
        },
        ...
     ]
}
```

Checkins will update a database (classes.db) with the checkin information.  
