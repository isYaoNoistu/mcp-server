# -*- coding: utf-8 -*-

def jsonrpc_response(request_id, result):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }


def jsonrpc_error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message
        }
    }
