# Campus Events and Workshop Booking

A microservice assignment for COMP 4633. You are given two complete request paths through
the system: one that reads from a single service, and one where a service calls another
service to finish the job. Everything else is yours to build, including the protobuf
messages and service definitions.

```text
curl --HTTP--> gateway (8080) --gRPC--> event_service (8081) --> event_db
                               --gRPC--> registration_service (8082) --> registration_db
                                              |
                                              +--gRPC--> event_service (8081)
```

The gateway is the only process that speaks HTTP. It translates REST calls into gRPC
calls and owns no data. Each service owns one database and nothing else may read it. When
the registration service needs something it does not own, such as a seat, it asks the
event service over gRPC.

## Requirements

- Python 3.9 or newer
- A running MySQL server on port with a username and password
- `make`

If your MySQL uses a host, port, user or password, other than values included edit the `db` section of
`event_service/config.json` and `registration_service/config.json`, and the `MYSQL`
variable at the top of the matching `Makefile`.

## Start

```bash
make install   # create .venv and install the Python packages
make db        # create event_db and registration_db and load the schemas
make dev       # generate the gRPC code and run all three services
```

If `python3` on your machine is older than 3.9, point the first step at a newer one with
`make install PYTHON=python3.12`.

`make dev` keeps running until you press Ctrl+C. In another terminal:

```bash
curl -sS http://127.0.0.1:8080/api/v1/events/1
{"available_seats":9,"capacity":12,"event_id":1,"name":"Git workshop"}
```

Study the two worked examples below before writing anything.

## Make targets

| Target | Root | Service directory |
|---|---|---|
| `make install` | creates `.venv` | — |
| `make gen` | generates gRPC code for all services | generates that service's gRPC code |
| `make db` | loads both schemas | loads that service's schema |
| `make dev` | runs all three services | runs that service (after `make gen`) |

Run `make gen` every time you change a `.proto` file, and `make db` every time you change
a `.sql` file. `make dev` runs `make gen` for you.

## Worked example 1: one service

`GET /api/v1/events/1` touches five files. Read them in this order.

**1. `proto/event.proto`** defines the contract. Two messages and one method:

```proto
service EventService {
  rpc GetEvent(EventId) returns (Event);
}

message EventId { int64 event_id = 1; }
message Event { int64 event_id = 1; string name = 2; int32 capacity = 3; int32 available_seats = 4; }
```

**2. `make gen`** compiles that file into `event_pb2.py` (the messages) and
`event_pb2_grpc.py` (the stub and the servicer base class), inside a `generated/`
directory in each service that needs it. Never edit generated code; change the `.proto`
and regenerate.

**3. `gateway/app.py`** holds a client stub built from an address in `config.json`, turns
the URL into a request message, and turns the reply message into JSON:

```python
events = event_pb2_grpc.EventServiceStub(grpc.insecure_channel(CONFIG["event_service"]))

@app.get("/api/v1/events/<int:event_id>")
def get_event(event_id):
    return jsonify(fields(events.GetEvent(event_pb2.EventId(event_id=event_id))))
```

`fields` copies every field of a protobuf message into a dict, so a message you extend
later shows up in the JSON with no gateway change.

**4. `event_service/server.py`** implements the method by subclassing the generated
servicer, reading its own database, and building a reply message from the row. A missing
row is reported with a gRPC status code, not an exception:

```python
if not found:
    context.abort(grpc.StatusCode.NOT_FOUND, "Event not found")
return pb.Event(**found[0])
```

**5. `gateway/app.py`** maps that status code back to HTTP in its `STATUS` table and its
`grpc.RpcError` handler, which is why `GET /api/v1/events/999` answers 404 with a JSON
body. Keep using this mechanism: services speak gRPC status codes, and only the gateway
knows about HTTP numbers.

Every task below repeats these five steps.

## Worked example 2: one service calling another

`DELETE /api/v1/registrations/1` is the example that matters most, because it is the only
place where a service cannot finish a request on its own. Try it:

```bash
curl -sS http://127.0.0.1:8080/api/v1/events/1     # available_seats 9
curl -sS -i -X DELETE http://127.0.0.1:8080/api/v1/registrations/1   # 204
curl -sS http://127.0.0.1:8080/api/v1/events/1     # available_seats 10
```

One HTTP call changed rows in two databases owned by two processes. The registration
service owns the booking and cancels it in `registration_db`. It does not own seats, so it
asks the event service to give one back, and that write happens in `event_db`.

**The caller side**, in `registration_service/server.py`. The service builds a client stub
exactly the way the gateway does, from an address in its own `config.json`, and holds it
for the lifetime of the process:

```python
events = event_pb2_grpc.EventServiceStub(grpc.insecure_channel(CONFIG["event_service"]))
rpc.add_RegistrationServiceServicer_to_server(RegistrationService(events), server)
```

The method updates its own table first, then calls the other service:

```python
def CancelBooking(self, request, context):
    found = read("SELECT event_id, state FROM bookings WHERE booking_id = %s", (request.booking_id,))
    if not found:
        context.abort(grpc.StatusCode.NOT_FOUND, "Booking not found")
    if found[0]["state"] == "confirmed":
        write("UPDATE bookings SET state = 'cancelled' WHERE booking_id = %s", (request.booking_id,))
        call(self.events.ReleaseSeat, event_pb2.EventId(event_id=found[0]["event_id"]), context)
    return pb.Empty()
```

Three decisions in there are worth copying:

- The booking is marked `cancelled`, not deleted. The row is history, and the state is
  what makes cancelling twice safe: the second call finds a row that is already cancelled,
  skips the release, and still answers 204. Releasing the same seat twice would corrupt
  the count.
- Note that `event_id` is stored as a plain number. The registration service never joins
  to the events table, because that table lives in another database it has no access to.
  Crossing that line is the thing microservices forbid.
- The `call` helper forwards the other service's failure instead of hiding it:

```python
def call(method, request, context):
    try:
        return method(request)
    except grpc.RpcError as error:
        context.abort(error.code(), error.details())
```

Without it, a `NOT_FOUND` raised inside the event service would surface to the client as a
generic 500. With it, the status code survives both hops and the gateway still answers
404. Prove it to yourself: `DELETE /api/v1/registrations/1` with a booking row that points
at an event id that does not exist.

**The callee side**, in `event_service/server.py`, is an ordinary method. It has no idea a
service called it rather than the gateway, and that is the point: a service exposes one
interface to everybody.

```python
def ReleaseSeat(self, request, context):
    self.GetEvent(request, context)
    write("UPDATE events SET seats_taken = seats_taken - 1 WHERE event_id = %s", (request.event_id,))
    return pb.Empty()
```

Task 4 asks you to build the mirror image of this flow.

## What you must build

Your finished system must serve this API. All paths are under `/api/v1`. The two rows
marked **given** already work; the rest is your assignment.

| Method and path | Request body | Success | Errors |
|---|---|---|---|
| `GET /events/{id}` **given** | — | 200, event | 404 unknown event |
| `DELETE /registrations/{id}` **given** | — | 204, also when already cancelled | 404 |
| `GET /events` | — | 200, array of events, optional `?name=` substring filter | — |
| `POST /events` | `name`, `capacity` | 201, event | 400 bad input, 401 no staff token |
| `PATCH /events/{id}` | `name` and/or `capacity` | 200, updated event | 400, 401, 404, 409 capacity below booked seats |
| `DELETE /events/{id}` | — | 204 | 401, 404, 409 event has bookings |
| `POST /participants` | `name` | 201, participant | 400 bad input |
| `GET /participants/{id}` | — | 200, participant | 404 |
| `POST /registrations` | `event_id`, `participant_id` | 201, booking | 400, 404 unknown event or participant, 409 full or duplicate |
| `GET /events/{id}/registrations` | — | 200, array of confirmed bookings | — |

Response shapes:

```json
{"event_id":1,"name":"Git workshop","capacity":12,"available_seats":9}
{"participant_id":4,"name":"Dana"}
{"booking_id":4,"event_id":2,"participant_id":4,"participant_name":"Dana"}
```

Writing to events requires the staff token from `gateway/config.json`:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/events \
  -H 'Authorization: Bearer campus-staff-token' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Design review","capacity":8}'
```

Every route in that table already exists in `gateway/app.py`, so the shape of the finished
system is visible from the start. The ones you have not built yet answer 501 and name the
task they belong to:

```bash
curl -sS http://127.0.0.1:8080/api/v1/events
{"error":"TODO task 1: implement GET /api/v1/events"}
```

List all of them at once:

```bash
grep -n TODO gateway/app.py
```

The gateway is only ever the translation layer. Replacing one of those stubs means
building the protobuf message, the service method behind it, and the route, which is why
each task below names all three.

## Task 1 — Finish the event queries

Add `GET /api/v1/events`, returning every event, and `GET /api/v1/events?name=lab`,
returning only events whose name contains that text.

1. Add a request message and a `ListEvents` method to `proto/event.proto`.
2. Run `make gen`.
3. Implement the method in `event_service/server.py` using the `read` helper and SQL
   `LIKE`. Sort by `event_id` so the output is stable.
4. Replace the `list_events` stub in `gateway/app.py`.

Decide whether the method returns one message holding a repeated field or a `stream` of
events, and justify the choice in your submission. If you choose a stream, the server
method `yield`s messages and the gateway iterates over the call result.

## Task 2 — Event writes

Replace the `add_event`, `edit_event` and `delete_event` stubs, and implement the service
methods behind them.

The protobuf work is the interesting part here. You need a message for creating, a
message for updating and a reply type for delete. For update, a client may send only
`name`, only `capacity`, or both, so the message must distinguish "not sent" from "sent
as empty". Mark those fields `optional` in proto3 and read them with
`request.HasField("name")`. For delete, define your own empty message or import
`google/protobuf/empty.proto`.

Rules to enforce, each in the layer that owns the knowledge:

| Rule | Where | Result |
|---|---|---|
| Body is not valid JSON, a field has the wrong type, or `capacity` is negative | gateway | 400 |
| Missing or wrong staff token on these three routes | gateway | 401 |
| Event name is blank | event service, `INVALID_ARGUMENT` | 400 |
| New capacity is below the number of seats already booked | event service, `FAILED_PRECONDITION` | 409 |
| Deleting an event that has bookings | event service, `FAILED_PRECONDITION` | 409 |

The gateway checks the shape of the request; the service checks the rules of the
business. Keep them apart.

The `write` helper already in `event_service/server.py` returns `cursor.lastrowid`, the id
MySQL assigned to a new row, so you can build the reply after an insert or update by
calling your own `GetEvent` with that id.

For the staff token, add a `before_request` function in the gateway that compares the
`Authorization` header with `CONFIG["staff_token"]` for exactly those three endpoints.

## Task 3 — Participants

Replace the `add_participant` and `get_participant` stubs. The `participants` table is
already in `registration_service/schema.sql`, seeded with Alex, Bao, Casey, Dana and Eli,
so `participant_id` 4 is Dana.

1. Define the participant messages and the two methods in `proto/registration.proto`.
2. Implement them in `registration_service/server.py` with the `read` and `write` helpers
   that are already there.
3. Fill in the two gateway stubs. The client stub they call through already exists.

A blank name is 400, and an unknown participant is 404.

This is the task to use for getting comfortable with changing a `.proto` and regenerating
before Task 4 asks for something harder.

## Task 4 — Bookings across two services

This is the real assignment. Replace the `list_bookings` and `book` stubs, building the
mirror image of the cancel flow you already have.

Cancelling releases a seat the system had already given out. Booking has to take one that
might not be there, so it can fail in ways cancelling cannot, and that is what makes it
harder.

1. Define the booking messages and the two methods in `proto/registration.proto`. The
   booking reply includes `participant_name`, which the registration service reads from
   its own `participants` table with a join. The `bookings` table is already in
   `schema.sql`, seeded with three confirmed bookings for event 1, matching the 3 of 12
   seats the event seed says are taken. Nothing keeps those two databases in agreement
   for you: there is no foreign key between them, and there cannot be.
2. Add `ReserveSeat` to `proto/event.proto` and implement it next to `ReleaseSeat`. It
   must refuse with `RESOURCE_EXHAUSTED` when no seat is free, which the gateway already
   maps to 409.
3. Implement the two methods in the registration service. The event stub and the `call`
   helper are already wired up; `CreateBooking` uses them the same way `CancelBooking`
   does.
4. Fill in the two gateway stubs.

Failures you must produce:

| Situation | Answer |
|---|---|
| Participant does not exist | 404 |
| Event does not exist | 404 |
| Event is full | 409 |
| Participant already has a confirmed booking for that event | 409 |

One design question to answer in your submission. A booking means writing a row in
`registration_db` and incrementing a counter in `event_db`, and you cannot put those two
writes in one transaction because they are in different databases on different services.
Choose the order and defend it: what does the system look like if the process dies
between the two steps, or if the event service answers "full" after you have already
written the booking row? `CancelBooking` faces the same question and answers it one way;
say whether booking should answer it the same way or the opposite way, and why.

## How to work

1. Keep `make dev` running in its own terminal and watch it for errors.
2. Change one `.proto`, one service method and one gateway route at a time.
3. Restart `make dev` with Ctrl+C and run it again. Python does not reload edited code,
   and a changed `.proto` needs regenerating, which `make dev` does on start.
4. Check the endpoint with `curl -sS`, and add `-i` to see the status code.
5. Run `make db` whenever you change a schema or want the seed data back.

A stack trace in the `make dev` terminal is a bug in your code. A clean JSON error in the
curl output usually means your code is behaving as designed. If a call returns 503, one of
the three processes is not running. If results contradict your code, check for a leftover
process from an earlier run with `lsof -nP -iTCP:8081 -sTCP:LISTEN`; gRPC lets two servers
share a port, and you will get answers from both.

When everything is implemented, this sequence should work from freshly seeded data:

```bash
base=http://127.0.0.1:8080/api/v1
curl -sS "$base/events?name=lab"
curl -sS -X POST -H 'Content-Type: application/json' -d '{"name":"Fay"}' $base/participants
curl -sS -X POST -H 'Content-Type: application/json' -d '{"event_id":2,"participant_id":4}' $base/registrations
curl -sS $base/events/2
curl -sS $base/events/2/registrations
curl -sS -X POST -H 'Content-Type: application/json' -d '{"event_id":3,"participant_id":1}' $base/registrations
curl -sS -X POST -H 'Content-Type: application/json' -d '{"event_id":3,"participant_id":2}' $base/registrations
curl -sS -i -X DELETE $base/registrations/4
curl -sS $base/events/2
```

Booking Dana into event 2 must drop its `available_seats` from 4 to 3 and show her in the
registration list. Event 3 has one seat: the first booking must succeed and the second
must fail with 409 without changing `seats_taken`. Cancelling Dana's booking with the
cancel flow you were given must put event 2 back to 4 available seats, which is the proof
that your booking path and the given cancel path agree about seats.

## Going further

- Your duplicate-booking check reads and then inserts. Two simultaneous requests can both
  pass the check. Add a `UNIQUE` constraint that makes MySQL enforce it and handle the
  resulting error.
- The same race exists between checking capacity and incrementing `seats_taken`. Find the
  SQL that closes it.
- `GET /events/99999999999999999999` crashes because the number does not fit in an
  `int64`. Reject it in the gateway with 400.
- The cancel flow you were given is not perfect. It marks the booking cancelled and then
  releases the seat, so if the event service is unreachable at that moment the booking is
  cancelled while the seat stays taken, and the two databases disagree. Reproduce it by
  stopping the event service and cancelling a booking. Describe how you would detect and
  repair the mismatch later, and explain why no single database transaction can prevent
  it.
- Stop the event service with Ctrl+C while the other two keep running, then call
  `GET /events/1` and `GET /events/1/registrations`. Explain why one fails and the other
  does not, and what that says about coupling between services.

## Layout

```text
campus-booking/
  Makefile                   install, gen, db, dev for the whole system
  requirements.txt
  proto/                     event.proto, registration.proto
  gateway/                   app.py, config.json, Makefile
  event_service/             server.py, config.json, schema.sql, Makefile
  registration_service/      server.py, config.json, schema.sql, Makefile
```

Every service reads a `config.json` next to its code, holding its own listen address, the
addresses of the services it calls, and its database connection. No environment variables
are used. `make gen` writes generated code into a `generated/` directory inside each
service; those are not checked in.
