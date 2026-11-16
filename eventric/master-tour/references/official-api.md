# Official REST API

Eventric's public API. The v5 docs only survive in a 2021 Wayback Machine copy of `my.eventric.com/portal/apidocs`; the live page is gone.

## Connection

- Base URL: `https://my.eventric.com/portal/api/v5/`. The path stays v5.
- Every request needs `version=7` as a query parameter, inside the OAuth signature base string. Without it: `426 Upgrade Required`.
- Auth: OAuth 1.0, HMAC-SHA1, 2-legged. Consumer key and secret are the API Key and Secret from your account's API Keys page. Token and token secret are empty, so the signing key is `<secret>&`.
- The OAuth parameters can go in the `Authorization` header or in the query string. The signature is the same either way. Some serverless runtimes strip a custom `Authorization` header (Convex's default `fetch` does), so the client sends them in the query string.
- Responses are JSON `{success, message, data}`. 200 is OK, 400 is a validation error, 500 or non-JSON is a server bug.

## Reads

| Call | Returns |
| --- | --- |
| `GET tours` | Every tour you can see, with `organizationName`, `artistName`, `tourName`, `legName`, `tourId` |
| `GET tour/{tourId}` | The tour and its days. Add `numPastDays=0` for every day; the default is only the last 5 past days |
| `GET day/{dayId}` | `{data:{day:{...}}}`: city, state, `dayDate`, `dayType`, `timeZone`, `generalNotes`, `travelNotes`, `hotelNotes`, `syncId` |
| `GET day/{dayId}/events` | Show events on the day |
| `GET event/{eventId}/guestlist` | The event's guest list |
| `GET event/{eventId}/setlist` | Set list |
| `GET day/{dayId}/hotels` | Hotels |
| `GET company/{id}/contacts` | Contacts |
| `GET tour/{tourId}/crew` | Crew |

The official API sees every org you can view, including orgs where you are only a viewer. The desktop token cannot reach those.

## Writes

- **Day notes:** `PUT day/{dayId}` with `{generalNotes, travelNotes, hotelNotes, syncId}`. The v5 docs leave out two things: the body must include `syncId` (400 `Undefined property syncId` without it), and `syncId` is an optimistic-concurrency counter that goes up on every write. GET the day fresh, send the current `syncId`, and send the other two note fields back unchanged.
- **Itinerary items:** `POST`, `PUT` and `DELETE itinerary`. Standard items only.
- **Guest list:** `POST guestlist` needs the full guest object, including empty `contact*` fields, or it returns 400. `PUT guestlist/{id}` edits. If you are a submitter on another artist's event (`isAcceptingSubmissions` true, `hasManagerPermission` false), your adds land as pending.

## Gaps

- No delete for guest list entries.
- No file or attachment upload. `day/{id}/attachments`, `/files` and `/media` return 200, but they are false positives: the router ignores an unknown trailing segment and returns the plain day, the same as `day/{id}/anything`. Only `day/{id}/events` is a real sub-resource.
- `GET day/{id}` returns 500 `TravelId_Equals required` on a day that has a travel-leg schedule item. Read those days' schedule items through the desktop API (`ScheduleItemVO` filtered by `parentDayId`).
