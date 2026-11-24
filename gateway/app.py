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


@app.before_request
def require_staff_token():
    if request.endpoint in {"add_event", "edit_event", "delete_event"}:
        authorization = request.headers.get("Authorization", "")
        if authorization != f"Bearer {CONFIG['staff_token']}":
            abort(401, "Staff token required")


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
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        abort(400, "Expected a JSON object")
    if "name" not in data or "capacity" not in data:
        abort(400, "Name and capacity are required")
    if not isinstance(data["name"], str):
        abort(400, "Event name must be a string")

    capacity = data["capacity"]
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0:
        abort(400, "Capacity must be a non-negative integer")
    if capacity > 2**31 - 1:
        abort(400, "Capacity is too large")

    event = event_pb2.CreateEventRequest(
        name=data["name"],
        capacity=capacity,
    )

    result = events.CreateEvent(event)

    return jsonify(fields(result)), 201


@app.patch("/api/v1/events/<int:event_id>")
def edit_event(event_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    has_name = "name" in data
    has_capacity = "capacity" in data

    if not has_name and not has_capacity:
        return jsonify({"error": "At least one of 'name' or 'capacity' is required"}), 400

    req_kwargs = {"event_id": event_id}

    if has_name:
        name = data["name"]
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "Event name must be a non-empty string"}), 400
        req_kwargs["name"] = name.strip()

    if has_capacity:
        capacity = data["capacity"]
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            return jsonify({"error": "Event capacity must be a positive integer"}), 400
        req_kwargs["capacity"] = capacity

    updated = events.UpdateEvent(event_pb2.UpdateEventRequest(**req_kwargs))
    return jsonify(fields(updated)), 200


@app.delete("/api/v1/events/<int:event_id>")
def delete_event(event_id):
    abort(501, "TODO task 2: implement DELETE /api/v1/events/<event_id>")


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
