# classy

Classy is a discord bot for taking attendance, registering for classes on Discord, and sending reminders.

Note, this is currently in alpha stage, and pretty much only works for a very specific Discord/Class configuration.

The way it's currently set up, all classes live inside the same server/guild.  Different roles have access to different channels.  

The bot gives roles if they register for the class.  This can be password protected.

Once users are registered, they can run !checkin in their class channel.  

To run classy, you need to create a config.json file in the root with the following:

```json
{
    "key":"YOURBOTKEYFROMDISCORDDEVELOPERPAGE",
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
