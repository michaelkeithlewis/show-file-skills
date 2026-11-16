# Desktop sync API

The API the Master Tour desktop app (Electron) uses to sync. It is not documented. Everything here comes from watching the app's own traffic and from live reads and writes.

## Connection

- `POST https://my.eventric.com/portal/api/v1/desktop/retrieve` reads one table (a "voType").
- `POST https://my.eventric.com/portal/api/v1/desktop/update` inserts or updates rows in one table.
- `POST https://my.eventric.com/portal/api/v1/desktop/updatedtables` lists what changed since a sync point (body `{"lastSyncedData": {}}`).
- The token goes in the JSON body, not a header. Base body: `accountId`, `token`, `clientVersion`, `tzOffset`, and for org data `orgId` plus `selectedOrganizationId`.
- **The User-Agent is the gate.** Without the `MasterTour/3.9.2 ... Electron/34.5.8` substring the API returns 401 "Bad credentials", even with a good token. No Origin, Referer or cookie is needed, and there is no IP binding or TLS fingerprint check. `scripts/mt_desktop.py` sends the full header set the app sends. Update the version strings in it if a newer app version is needed.
- The token is a bcrypt-looking string (`$2y$10$...`). It changes when you log out and back in to the desktop app. A 401 with the right User-Agent means the token is stale.
- The token only reaches orgs where you are a full member. For view-only orgs use the official API.

## Reading

- `/retrieve` is paginated. While the response has `isTableRetrieved: false`, send the returned `primaryKey` and `newSyncTime` back as `lastPrimaryKey` and `lastSyncTime`. New rows land on later pages, so one unpaginated call misses them. The client loops for you.
- `voType: "Organization"` lists the orgs on the account.

## Writing

- `/update` is update-only unless each object carries `"isNew": true` (or `"isInsert": true`). Without it an insert returns HTTP 206 and "... with primary key of ... not found". With it: `success: true`, "Sync Insert OK".
- Make the `id` yourself: `secrets.token_hex(20)` (40 hex) for Tour, Day, DayEvent and Venue; `secrets.token_hex(16)` (32 hex) for GuestList.
- There is no idempotency. The same insert sent twice makes two rows.
- Delete by updating the row with `isDeleted: 1`.
- JSON-blob fields (`metadata`, `guestListAllotmentData`, `localCrewData`) come back from `/retrieve` as objects but must be sent as `json.dumps(...)` strings. A real object returns 206 "value could not be converted to string".
- Errors come back as HTTP 206 with the message in the body, including raw MySQL foreign-key errors.

## Tables

### TourVO
- `tourName` is always empty. The label is `legName`.
- Each leg in the app is its own TourVO row; there is no leg table. Legs of one artist share `artistId`.
- The key is `id`. There is no `tourId` field. Match by `legName`, chain by `id`.

### DayVO, DayEventVO, VenueVO
- A Day is a date and an address. The show is a DayEvent (`dayId` to the Day, `venueId` to the Venue).
- Day `metadata` is a JSON string `{"eventIdOrder": ["<dayEventId>", ...]}`. It tells the app which events to show under the day. Insert a Day, insert at least one DayEvent, and put its id in `eventIdOrder`, or the day shows empty.
- DayEvent defaults that insert cleanly:

```python
guest_list_allotment_data = json.dumps({
    "allotments": [{"enforcementLevel": "", "enforcementType": "", "ident": "default", "limit": 0}],
    "cutoffTime": "", "isLocked": False,
})
local_crew_data = json.dumps({
    "costAtSettlement": 0, "costAtSettlementCurrencyValue": "",
    "crewComments": "", "laborCall": [], "localUnion": "",
    "minimumIn": 0, "minimumOut": 0, "penalties": "",
})
```

  `promoterId: "0"` is fine when there is no promoter row.
- `venueTypeId` is a foreign key. Values seen: `Arena`, `Nightclub`, `Theatre` (British spelling), `Hall`, `Amphitheatre`, `Bar`, `Festival`, `Other`, `Ballroom`, `Restaurant`, `FairGround`, `Field`, `ConferenceRooms`, `Rehearsal Studio`, `Shed`, `Coffeehouse`. Any other value returns a 206 FK error.
- Venue XML fields: `productionXml`, `facilitiesXml`, `phoneXml` and `logisticsXml` use a `<dataStore>` root; `equipmentXml` and `localCrewXml` use `<xml>`. `phoneXml` contacts use `<contactName>` (not `<name>`), plus `<public>` (0 or 1) and `<url>`.
- Retrieve an existing venue in the same org and build the new XML from its structure. Do not trust a field list written from memory.

### ScheduleItemVO
- Filter by `parentDayId` to get one day.
- Insert shape that works: `scheduleItemTypeId: "Day"`, `calendarName: "Day"`, `startTimeZone` and `endTimeZone` empty, `startDatetime` as UTC ISO, `paulStartTime` as the local wall-clock time with a `+00:00` suffix, 40-hex `id`, `isNew: true`.

### HotelVO and DayHotelAssign
- Hotels belong to the org (`organizationId`), not the tour. A DayHotelAssign row (`dayId`, `hotelId`, `assignLabel`, `assignPriority` 1, `travelGroup`, `dayNotes`) puts a hotel on a day.
- `hotelTypeId: "Hotel"`. Check-in and check-out are ISO datetimes. For a time with no date the app uses the sentinel date `1999-09-09T<HH:MM>:00+00:00`.

### GuestList
- 32-hex `id`.
- `passTypeRequested` is a comma list: `"AA=2,VIP=1,"`. The trailing comma is the app's convention. Empty is fine.
- `pickupMethod: "Will Call"` (keep the case). `passApproved: 0` on insert; it flips to 1 at check-in.
- For a comp: `paymentStatusCode: "Approved"`, `notificationStatusCode: "Ready"`, `deliveryStatusCode: "Skipped"`.
- Leave every card and billing field empty.

## Geocoding

When a venue or hotel needs coordinates, OpenStreetMap Nominatim resolves most US addresses for free. Send a real User-Agent, keep to one request per second, and fall back by dropping the ZIP, then the state, then searching the name alone. A branded name often resolves when a bare street address does not.
