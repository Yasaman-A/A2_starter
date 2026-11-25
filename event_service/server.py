import json
from concurrent import futures

import grpc
import mysql.connector
import event_pb2 as pb
import event_pb2_grpc as rpc

CONFIG = json.load(open("config.json"))


def read(sql, args=()):
    with mysql.connector.connect(**CONFIG["db"]) as db, db.cursor(dictionary=True) as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def write(sql, args=()):
    with mysql.connector.connect(**CONFIG["db"]) as db, db.cursor() as cursor:
        cursor.execute(sql, args)
        db.commit()
        return cursor.lastrowid


class EventService(rpc.EventServiceServicer):
    def GetEvent(self, request, context):
        found = read("""SELECT event_id, name, capacity, capacity - seats_taken AS available_seats
                        FROM events WHERE event_id = %s""", (request.event_id,))
        if not found:
            context.abort(grpc.StatusCode.NOT_FOUND, "Event not found")
        return pb.Event(**found[0])

    def ReleaseSeat(self, request, context):
        self.GetEvent(request, context)
        write("UPDATE events SET seats_taken = seats_taken - 1 WHERE event_id = %s", (request.event_id,))
        return pb.Empty()
    def ListEvents(self, request, context):
        if request.HasField("name") and request.name:
            found = read("""SELECT event_id, name, capacity,
                            capacity - seats_taken AS available_seats
                            FROM events WHERE name LIKE %s""",
                         (f"%{request.name}%",))
        else:
            found = read("""SELECT event_id, name, capacity,
                            capacity - seats_taken AS available_seats
                            FROM events""")

        return pb.ListEventsResponse(
            events=found
        )
    def CreateEvent(self, request, context):
        if not request.name.strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Event name is required")

        if request.capacity <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Event capacity must be positive")

        try:
            event_id = write(
                "INSERT INTO events (name, capacity) VALUES (%s, %s)",
                (request.name, request.capacity)
            )
        except mysql.connector.IntegrityError:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "Event already exists")

        return self.GetEvent(pb.EventId(event_id=event_id), context)
    """
    Updates the specified event data

    Args:
    request (UpdateEventRequest): contains event name, capacity, and event ID
    context: gRPC context used for error handling 

    Returns:
        Event: Updated data values for the event

    Errors:
        INVALID_ARGUMENT: Invalid event ID (<=0)
        INVALID_ARGUMENT: No provided fields
        INVALID_ARGUMENT: Leaving Event name blank
        INVALID_ARGUMENT: Event capacity has to be positive
        NOT_FOUND: Event ID was not found 
        FAILED_PRECONDITION: Changed capacity lower than booked seats

    """
    def UpdateEvent(self, request, context):
        if request.event_id <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid event ID")

        has_name = request.HasField("name")
        has_capacity = request.HasField("capacity")

        if not has_name and not has_capacity:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "At least one field (name or capacity) is required")

        if has_name and not request.name.strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Event name cannot be blank")

        if has_capacity and request.capacity <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Event capacity must be positive")

        found = read(
            "SELECT name, capacity, seats_taken FROM events WHERE event_id = %s",
            (request.event_id,)
        )
        if not found:
            context.abort(grpc.StatusCode.NOT_FOUND, "Event not found")

        event = found[0]

        if has_capacity and request.capacity < event["seats_taken"]:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Capacity cannot be less than booked seats")

        new_name = request.name.strip() if has_name else event["name"]
        new_capacity = request.capacity if has_capacity else event["capacity"]

        try:
            write(
                "UPDATE events SET name = %s, capacity = %s WHERE event_id = %s",
                (new_name, new_capacity, request.event_id)
            )
        except mysql.connector.IntegrityError:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "Event already exists")

        return self.GetEvent(pb.EventId(event_id=request.event_id), context)

server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
rpc.add_EventServiceServicer_to_server(EventService(), server)
server.add_insecure_port(CONFIG["listen"])
server.start()
print(f"Event service on {CONFIG['listen']}", flush=True)
server.wait_for_termination()
