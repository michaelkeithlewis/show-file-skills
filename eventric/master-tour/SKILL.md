---
name: master-tour
description: Read and write Master Tour (Eventric) tour data from the command line - tours, days, show events, venues and their production fields, schedule items, hotels, guest lists, day notes. Two paths - the official REST API (OAuth 1.0, sees every org you can view, writes day notes, itinerary items and guest lists) and the Desktop sync API the Master Tour app itself uses (every table, full insert and update, the only way into venue production XML, hotel assignments and deletes). Trigger on "Master Tour", "MT", "Eventric", "day notes", "guest list in Master Tour", "venue production", "facilitiesXml", "productionXml", "voType", "VenueVO", "DayVO", "DayEventVO", "HotelVO", "GuestListVO", "Desktop API", "my MT token expired". NOT for RoadOps or other tour software.
---

# Master Tour from the command line

Master Tour has two APIs. Pick by what you need:

| Need | Use |
| --- | --- |
| Read any tour you can see, including view-only orgs | Official: `scripts/mt_official.py` |
| Day notes (general, travel, hotel), itinerary items, guest list adds | Official |
| Venue production, facilities, equipment, crew, contacts XML | Desktop: `scripts/mt_desktop.py` |
| Insert days, show events, venues, hotels, hotel assignments | Desktop |
| Delete anything (`isDeleted: 1`) | Desktop |
| Anything in an org where you are only a viewer | Official (the desktop token only reaches orgs you are a full member of) |

Full notes: `references/official-api.md`, `references/desktop-api.md`, `references/token-capture.md`.

## Credentials

- Official: `$MT_API_KEY` and `$MT_API_SECRET` from the API Keys page of your Master Tour account.
- Desktop: `$MT_DESKTOP_TOKEN` and `$MT_ACCOUNT_ID`, captured from the desktop app (`references/token-capture.md`). Set `$MT_ORG_ID` or pass `--org`.

Never print a token or secret, and keep them out of files you commit.

## Quick start

```
python3 scripts/mt_official.py tours
python3 scripts/mt_official.py get tour/<tourId> numPastDays=0
python3 scripts/mt_official.py get day/<dayId>
python3 scripts/mt_desktop.py orgs
python3 scripts/mt_desktop.py --org <orgId> retrieve --voType DayVO --out days.json
python3 scripts/mt_desktop.py --org <orgId> update --voType DayVO --data '[{...}]'
```

## Rules that bite

1. Every official call needs `version=7` in the query and in the signature, or it returns 426. The client adds it.
2. An official day-note write is `PUT day/{id}` with all three note fields and the current `syncId`. GET the day first, change one field, send the rest back unchanged. `syncId` goes up by one on every write.
3. The official API has no delete. A wrong guest list add on someone else's list has to be removed by hand on their side.
4. Neither API takes file attachments. Host the file and put the link in the day's general notes.
5. The desktop API returns 401 unless the request carries the Master Tour Electron User-Agent. The client sends the full header set.
6. A desktop insert needs `"isNew": true` on each object and a client-made `id`. Without it you get HTTP 206 "primary key ... not found". Sending the same insert twice makes two rows.
7. Desktop ids are 40 hex characters for Tour, Day, DayEvent and Venue, and 32 for GuestList.
8. Desktop JSON-blob fields (`metadata`, `guestListAllotmentData`, `localCrewData`) come back as objects but must go up as JSON strings.
9. A new Day needs at least one DayEvent and its id in the Day's `metadata.eventIdOrder`, or the day shows empty.
10. Before you build a Venue's XML fields, retrieve a venue in the same org and copy its structure.
11. Confirm the org before every write. One account often belongs to many orgs.

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, Master Tour version, what you found.`*
