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
    """
    Creates a new participant and stores it into the database

    Args:
        request: (CreateParticipantRequest) contains participants name
        context: gRPC context used for error handling

    Returns:
        Participant: the created participant 

    Errors:
        INVALID_ARGUMENT: Participant name is blank 
        ALREADY_EXISTS: Participant is already in the database
    """
    def CreateParticipant(self, request, context):
        if not request.name:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Participant name is required")

        try:
            participant_id = write(
                "INSERT INTO participants (name) VALUES (%s)" , (request.name,)
            )
        except mysql.connector.IntegrityError:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "Participant already exists")

        return self.GetParticipant(pb.ParticipantId(participant_id=participant_id), context) 


    # CreateBooking makes bookings for participants for events
    # Input: 
    #   event_id: Id of desired event to be booked 
    #   participant_id: Id of person joining event
    # Output: 
    #   (201, booking): Success returns booking information
    #   (400): Invalid Input (empty input, wrong type, body is not valid)
    #   (404): Participant or Event does not exist
    #   (409): Full event or duplicate booking
    #   
    # Checks participants before event: so if both event and participant id are wrong will flag participant only.
    #
    # error 400 incomplete (use isinstance() probably)   
    # allowing negative id?
    def CreateBooking(self, request, context):        
        participant = self.GetParticipant(pb.ParticipantId(participant_id=request.participant_id), context)

        duplicate = read(
            """
            SELECT booking_id, state 
            FROM bookings 
            WHERE event_id = %s
            AND participant_id = %s
            AND state = "confirmed" 
            """,
            (request.event_id, participant.participant_id,)
        )
        if (duplicate):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Duplicate Registration")
        
        call(self.events.ReserveSeat, event_pb2.EventId(event_id=request.event_id), context)
        
        booking = write(
            """
            INSERT INTO bookings (event_id, participant_id)
            VALUES(%s, %s)
            """,
            (request.event_id, participant.participant_id)
        )
        
        return pb.BookingInformation(booking_id = booking, event_id = request.event_id, participant_id = participant.participant_id, participant_name = participant.name)

    # GetParticipants gets information of desired participant
    # Input: 
    #   participant_id: ID of participant
    # Output: 
    #   (201, participant): Success returns participant ID and name
    #   (404): Participant does not exist
    def GetParticipant(self, request, context):
        participant = read(
            """
            SELECT participant_id, name 
            FROM participants 
            WHERE participant_id = %s
            """,
            (request.participant_id,)
        )
        if not participant:
            context.abort(grpc.StatusCode.NOT_FOUND, "Participant not found")
        return pb.Participant(**participant[0])

events = event_pb2_grpc.EventServiceStub(grpc.insecure_channel(CONFIG["event_service"]))
server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
rpc.add_RegistrationServiceServicer_to_server(RegistrationService(events), server)
server.add_insecure_port(CONFIG["listen"])
server.start()
print(f"Registration service on {CONFIG['listen']}", flush=True)
server.wait_for_termination()
