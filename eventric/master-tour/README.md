# master-tour: Master Tour from Claude Code

A Claude Code skill and two small clients for [Master Tour](https://www.eventric.com), the tour management software. Read tours, days and guest lists, write day notes, and insert or edit the tables the app itself syncs: days, show events, venues and their production fields, schedule items, hotels and guest lists.

Master Tour has two APIs and you need both:

- **The official REST API** (`scripts/mt_official.py`) sees every tour you can view, including orgs where you are only a viewer, and writes day notes, itinerary items and guest list adds. It cannot delete and cannot reach venue production data.
- **The desktop sync API** (`scripts/mt_desktop.py`) is what the desktop app uses. It reads and writes every table in orgs where you are a full member, including deletes. It has no docs; `references/desktop-api.md` is what we worked out.

You ask in plain words ("put the parking note on Tuesday's day sheet", "add two will-call comps for the Denver show", "fill in the venue's dock and power from this tech pack") and Claude runs the clients.

## Requirements

- Python 3.8 or later with `requests`.
- For the official API: the API Key and Secret from your Master Tour account's API Keys page, in `$MT_API_KEY` and `$MT_API_SECRET`.
- For the desktop API: a desktop token and account id in `$MT_DESKTOP_TOKEN` and `$MT_ACCOUNT_ID`, captured with mitmproxy (`references/token-capture.md`).

## Install

```
cp -R show-file-skills/eventric/master-tour ~/.claude/skills/
```

## Status

- Proven in daily use on a full touring season: official reads (`tours`, `tour`, `day`, events, guest lists), day-note writes with `syncId`, guest list adds; desktop retrieve with pagination, inserts of days, show events, venues, hotels, hotel assignments, schedule items and guest list rows, venue XML edits, deletes by `isDeleted`.
- Desktop header set captured from Master Tour 3.9.2 on Electron 34.5.8.
- In this release: `mt_official.py tours` and `get` were run against the live API. The desktop client's `orgs` subcommand and the `mt_capture.py` addon are new and have not run against a live session yet.

This project is not affiliated with or endorsed by Eventric. The desktop API is not a public API and can change with any app update. Use your own account and your own data. No warranty.

## Credits

Master Tour API work in this folder is by [latouring](https://github.com/latouring). Full list: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, Master Tour version, what you found.`*
