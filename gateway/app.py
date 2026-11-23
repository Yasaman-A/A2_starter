import json
from unicodedata import name

import grpc
from flask import Flask, abort, jsonify, request
from werkzeug.exceptions import HTTPException
import event_pb2
import event_pb2_grpc
import registration_pb2
import registration_pb2_grpc

CONFIG = json.load(open("config.json"))
STATUS = {
    grpc.StatusCode.INVALID_ARGUMENT: 400,
    grpc.StatusCode.UNAUTHENTICATED: 401, ## <-- New
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.ALREADY_EXISTS: 409,
    grpc.StatusCode.RESOURCE_EXHAUSTED: 409,
    grpc.StatusCode.FAILED_PRECONDITION: 409,
    grpc.StatusCode.UNIMPLEMENTED: 501,
    grpc.StatusCode.UNAVAILABLE: 503,
}

app = Flask(__name__)
events = event_pb2_grpc.EventServiceStub(grpc.insecure_channel(CONFIG["event_service"]))
registrations = registration_pb2_grpc.RegistrationServiceStub(
    grpc.insecure_channel(CONFIG["registration_service"]))


def fields(message):
    return {field.name: getattr(message, field.name) for field in message.DESCRIPTOR.fields}


def manyfields(messages):
    return [fields(message) for message in messages]


@app.errorhandler(grpc.RpcError)
def rpc_error(error):
    return jsonify(error=error.details()), STATUS.get(error.code(), 500)


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code


@app.get("/api/v1/events")
def list_events():
    name = request.args.get("name", "")
    return jsonify(manyfields(events.ListEvents(event_pb2.ListEventsRequest(name=name)).events))


@app.get("/api/v1/events/<int:event_id>")
def get_event(event_id):
    return jsonify(fields(events.GetEvent(event_pb2.EventId(event_id=event_id))))


@app.post("/api/v1/events")
def add_event():
    data = request.get_json()

    event = event_pb2.CreateEventRequest(**data)

    result = events.CreateEvent(event)

    return jsonify(fields(result)), 201


@app.patch("/api/v1/events/<int:event_id>")
def edit_event(event_id):
    abort(501, "TODO task 2: implement PATCH /api/v1/events/<event_id>")


@app.delete("/api/v1/events/<int:event_id>")
def delete_event(event_id):
    abort(501, "TODO task 2: implement DELETE /api/v1/events/<event_id>")


@app.post("/api/v1/participants")
def add_participant():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Participant name must be a non-empty string"}), 400

    created = registrations.CreateParticipant(
        registration_pb2.CreateParticipantRequest(name=name.strip())
    )

    return jsonify(fields(created)), 201

@app.get("/api/v1/participants/<int:participant_id>")
def get_participant(participant_id):
    #if not isinstance(participant_id, int):
    #    context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid Participant ID")
    return jsonify(fields(registrations.GetParticipant(registration_pb2.ParticipantId(participant_id = participant_id)))), 200


@app.get("/api/v1/events/<int:event_id>/registrations")
def list_bookings(event_id):
    abort(501, "TODO task 4: implement GET /api/v1/events/<event_id>/registrations")

#make it not return in alphabetical order this one is fine but what about other functions?
@app.post("/api/v1/registrations")
def book():
    eventParticipantPair = request.get_json(silent = False)
    event = eventParticipantPair.get("event_id")
    participant = eventParticipantPair.get("participant_id")
    return jsonify(fields(registrations.CreateBooking(registration_pb2.Booking(event_id = event, participant_id = participant)))), 201

@app.delete("/api/v1/registrations/<int:booking_id>")
def cancel(booking_id):
    registrations.CancelBooking(registration_pb2.BookingId(booking_id=booking_id))
    return "", 204


app.run(host=CONFIG["host"], port=CONFIG["port"])
