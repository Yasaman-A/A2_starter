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


server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
rpc.add_EventServiceServicer_to_server(EventService(), server)
server.add_insecure_port(CONFIG["listen"])
server.start()
print(f"Event service on {CONFIG['listen']}", flush=True)
server.wait_for_termination()
