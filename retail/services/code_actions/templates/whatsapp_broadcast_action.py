import requests
import json


def Run(engine):
    """
    Code Action to send a WhatsApp Broadcast message.
    """

    # Getting the request body
    try:
        request_body = engine.body
        data = json.loads(request_body)
    except Exception as e:
        engine.log.error(f"Error processing request body: {e}")
        engine.result.set(
            {"error": "Invalid request body"}, status_code=400, content_type="json"
        )
        return

    # Extracting required parameters from the client's structure
    message_payload = data.get(
        "message_payload", {}
    )  # This contains the payload for Flows
    extra_data = data.get("extra_data", {})  # Additional data for custom processing
    token = data.get("token")
    flows_url = data.get("flows_url")

    # Validating required parameters
    if not message_payload or not token or not flows_url:
        engine.log.error("Missing required parameters.")
        engine.result.set(
            {"error": "Missing required parameters"},
            status_code=400,
            content_type="json",
        )
        return

    # Process extra_data if needed (example of how it could be used)
    if extra_data:
        engine.log.info(f"Processing extra data: {extra_data}")
        # Custom processing logic can be added here
        # For example, modifying the message based on extra_data

    # Sending the message via WhatsApp API
    response = send_whatsapp_broadcast(message_payload, token, flows_url)

    # Returning the result to the engine
    if response.get("status") == 200:
        engine.result.set(response, status_code=200, content_type="json")
    else:
        engine.result.set(
            {"error": "Failed to send message", "details": response},
            status_code=500,
            content_type="json",
        )


def send_whatsapp_broadcast(message_payload: dict, token: str, flows_url: str) -> dict:
    """
    Sends a WhatsApp message via the internal API.

    Args:
        payload (dict): Message data from the 'message' field.
        token (str): Authentication token.
        flows_url (str): Base URL for the Flows API.

    Returns:
        dict: API response.
    """

    url = f"{flows_url}/api/v2/internals/whatsapp_broadcasts"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=message_payload, headers=headers)
        return {
            "status": response.status_code,
            "response": response.json(),
        }
    except requests.RequestException as e:
        return {"status": 500, "error": str(e)}
