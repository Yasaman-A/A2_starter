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
        if(request.name):
            found = read("""SELECT event_id, name, capacity, (capacity-seats_taken) AS available_seats FROM events WHERE name LIKE %s ORDER BY event_id ASC; """,(f"%{request.name}%",),)
        else:
            found = read("""SELECT event_id, name, capacity, (capacity-seats_taken) AS available_seats FROM events ORDER BY event_id ASC""")
        return pb.ListEventsResponse(events=found)
    def CreateEvents(self, request, context):
        name = request.name.strip()
        if not name:
            context.about(grpc.StatusCode.INVALID_ARGUMENT, "Event name is required")
        new_id = write("INSERT INTO events (name,capacity,seats_taken) VALUES (%s,%s,0)", (name, request.capacity))
        return self.GetEvent(pb.EventId(event_id=new_id), context)

    
    def UpdateEvent(self, request, context):
        current = self.GetEvent(pb.EventId(event_id=request.event_id), context)
        taken = current.capacity - current.available_seats
        sets, args = [], []
        if request.HasField("name"):
            if not request.name.strip():
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Event name is reqiured")
            sets.append("name = %s")
            args.append(request.name.strip())
        if request.HasField("capacity"):
            if request.capacity < taken:
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Capacity is below booked seats")
            sets.append("capacity = %s")
            args.append(request.capacity)
        if sets:
            write(f"UPDATE events SET {', '.join(sets)} WHERE event_id = %s",
                  (*args, request.event_id))
        return self.GetEvent(pb.EventId(event_id = request.event_id), context)





server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
rpc.add_EventServiceServicer_to_server(EventService(), server)
server.add_insecure_port(CONFIG["listen"])
server.start()
print(f"Event service on {CONFIG['listen']}", flush=True)
server.wait_for_termination()
