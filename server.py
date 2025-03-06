import argparse
import socket
import sys
import openai
from openai import OpenAI
from http import HTTPStatus
from flask import Request, Response

class VsockServer:
    """A VSOCK server that listens for requests and interacts with OpenAI's API."""

    def __init__(self, port, conn_backlog=128):
        self.port = port
        self.conn_backlog = conn_backlog
        self.sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        self.bind()

    def bind(self):
        """Bind and listen for connections on the specified port."""
        self.sock.bind((socket.VMADDR_CID_ANY, self.port))
        self.sock.listen(self.conn_backlog)
        print(f"Server listening on port {self.port}...")

    def handle_client(self, client_socket):
        """Handle communication with a connected client."""
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                return
            print(f"Received: {data}")
            
            request = self.parse_request(data)
            response = self.post(request)
            client_socket.sendall(response.get_data(as_text=True).encode())
        except socket.error as e:
            print(f"Socket error: {e}")
        finally:
            client_socket.close()
    
    def parse_request(self, data):
        """Parse raw request data into a Flask-like request object."""
        lines = data.split("|")
        if len(lines) < 2:
            return None
        
        headers = {"Authorization": f"Bearer {lines[0].strip()}"}
        request_data = {"message": lines[1].strip()}
        if len(lines) > 2:
            request_data["model"] = lines[2].strip()
        
        return Request(environ={}, headers=headers, data=request_data)

    def post(self, request):
        query = request.data.get("message")
        model_name = request.data.get("model", "gpt-3.5-turbo")

        api_key = request.headers.get("Authorization")
        # Validate API key format (should be "Bearer <KEY>")
        if not api_key or not api_key.startswith("Bearer "):
            return Response(
                {"error": "Invalid or missing API key"},
                status=HTTPStatus.UNAUTHORIZED,
            )

        # Extract API key (remove "Bearer " prefix)
        api_key = api_key.split("Bearer ")[1]

        if not query:
            return Response(
                {"error": "Message field is required"},
                status=HTTPStatus.BAD_REQUEST,
            )
        try:
            if model_name in ["gpt-3.5-turbo", "gpt-4"]:
                # OpenAI GPT-3.5/GPT-4
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model_name, messages=[{"role": "user", "content": query}]
                )
                reply = response.choices[0].message.content.strip()
            else:
                reply = "Model not supported."

            return Response({"response": reply})

        except Exception as e:
            return Response({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def start(self):
        """Start the server to accept and process requests."""
        while True:
            client_socket, _ = self.sock.accept()
            self.handle_client(client_socket)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VSOCK OpenAI Server")
    parser.add_argument("port", type=int, help="The local port to listen on.")
    args = parser.parse_args()
    
    server = VsockServer(args.port)
    server.start()
