import json
from concurrent import futures

import grpc
import mysql.connector
import event_pb2
import event_pb2_grpc
import registration_pb2 as pb
import registration_pb2_grpc as rpc

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


def call(method, request, context):
    try:
        return method(request)
    except grpc.RpcError as error:
        context.abort(error.code(), error.details())


class RegistrationService(rpc.RegistrationServiceServicer):
    def __init__(self, events):
        self.events = events

    def CancelBooking(self, request, context):
        found = read("SELECT event_id, state FROM bookings WHERE booking_id = %s", (request.booking_id,))
        if not found:
            context.abort(grpc.StatusCode.NOT_FOUND, "Booking not found")
        if found[0]["state"] == "confirmed":
            write("UPDATE bookings SET state = 'cancelled' WHERE booking_id = %s", (request.booking_id,))
            call(self.events.ReleaseSeat, event_pb2.EventId(event_id=found[0]["event_id"]), context)
        return pb.Empty()


events = event_pb2_grpc.EventServiceStub(grpc.insecure_channel(CONFIG["event_service"]))
server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
rpc.add_RegistrationServiceServicer_to_server(RegistrationService(events), server)
server.add_insecure_port(CONFIG["listen"])
server.start()
print(f"Registration service on {CONFIG['listen']}", flush=True)
server.wait_for_termination()
