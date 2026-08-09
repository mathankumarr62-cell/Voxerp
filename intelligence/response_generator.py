from typing import Any, Dict


def generate_response(result: Dict[str, Any]) -> str:
    """Convert adapter or RBAC results into a concise spoken response."""

    if not isinstance(result, dict):
        return "I couldn't understand that response."

    status = result.get("status")
    message = result.get("message") or ""

    if status == "ok":
        if message:
            return message
        return "I found the requested information."

    if status == "no_data":
        return "You have no recorded data for that request."

    if status == "not_found":
        return "I couldn't find that student or subject."

    if status == "unauthorized":
        return "You are not authorized to access that data."

    if status == "unchanged":
        return "It was already marked that way."

    if status == "created":
        return "The attendance entry was marked successfully."

    if status == "updated":
        return "The attendance entry was updated successfully."

    if status == "unsupported":
        return "I can't help with that request."

    if status == "error":
        return "Something went wrong while processing that request."

    if isinstance(message, str) and message:
        return message

    return "I couldn't process that request."


__all__ = ["generate_response"]