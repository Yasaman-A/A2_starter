import json

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


@app.errorhandler(grpc.RpcError)
def rpc_error(error):
    return jsonify(error=error.details()), STATUS.get(error.code(), 500)


@app.errorhandler(HTTPException)
def http_error(error):
    return jsonify(error=error.description), error.code

def manyfields(messages):
    return [fields(message) for message in messages]

@app.get("/api/v1/events")
def list_events():
    name = request.args.get("name", "")
    return jsonify(manyfields(events.ListEvents(event_pb2.ListEventsRequest(name=name)).events))



@app.get("/api/v1/events/<int:event_id>")
def get_event(event_id):
    return jsonify(fields(events.GetEvent(event_pb2.EventId(event_id=event_id))))


STAFF_ROUTES = {"add_event", "edit_event", "delete_event"}
MAX = 2**31 - 1

@app.before_request
def require_staff_token():
    if request.endpoint in STAFF_ROUTES:
        if request.headers.get("Authorization") != f"Bearer {CONFIG['staff_token']}":
            abort(401, "Missing or invalid staff token")
        
def valid_capacity(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX


@app.post("/api/v1/events")
def add_event():
    body = request.get_json(silent=True)
    if (not isinstance(body, dict) or not isinstance(body.get("name"), str)
            or not valid_capacity(body.get("capacity"))):
        abort(400, "name must be a string and non negative ")
    reply = events.CreateEvents(event_pb2.CreateEventsRequest(
        name=body["name"], capacity=body["capacity"]))
    return jsonify(fields(reply)), 201


@app.patch("/api/v1/events/<int:event_id>")
def edit_event(event_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not ({"name", "capacity"} & body.keys()):
        abort(400, "send name and/or capacity")
    if "name" in body and not isinstance(body["name"], str):
        abort(400, "name must be a string")
    if "capacity" in body and not valid_capacity(body["capacity"]):
        abort(400, "capacity must be a non-negative integer")
    update = event_pb2.UpdateEventRequest(event_id=event_id)
    if "name" in body:
        update.name = body["name"]
    if "capacity" in body:
        update.capacity = body["capacity"]
    return jsonify(fields(events.UpdateEvent(update)))


@app.delete("/api/v1/events/<int:event_id>")
def delete_event(event_id):
    events.DeleteEvent(event_pb2.EventId(event_id=event_id))
    return "", 204


@app.post("/api/v1/participants")
def add_participant():
    abort(501, "TODO task 3: implement POST /api/v1/participants")


@app.get("/api/v1/participants/<int:participant_id>")
def get_participant(participant_id):
    abort(501, "TODO task 3: implement GET /api/v1/participants/<participant_id>")


@app.get("/api/v1/events/<int:event_id>/registrations")
def list_bookings(event_id):
    abort(501, "TODO task 4: implement GET /api/v1/events/<event_id>/registrations")


@app.post("/api/v1/registrations")
def book():
    abort(501, "TODO task 4: implement POST /api/v1/registrations")


@app.delete("/api/v1/registrations/<int:booking_id>")
def cancel(booking_id):
    registrations.CancelBooking(registration_pb2.BookingId(booking_id=booking_id))
    return "", 204


app.run(host=CONFIG["host"], port=CONFIG["port"])
