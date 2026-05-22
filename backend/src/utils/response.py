"""Standard JSON response helpers"""
from flask import jsonify


def success(data=None, message="Success", status=200, **kwargs):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    body.update(kwargs)
    return jsonify(body), status


def error(message="Error", status=400, errors=None):
    body = {"success": False, "message": message}
    if errors:
        body["errors"] = errors
    return jsonify(body), status
