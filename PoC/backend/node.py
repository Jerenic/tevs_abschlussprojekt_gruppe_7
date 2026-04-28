from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import sys
import datetime

app = Flask(__name__)
CORS(app)

# In-Memory Speicher: username -> Status-Objekt
statuses = {}
PEER_URL = None
NODE_NAME = "Node"


@app.route('/status', methods=['POST'])
def post_status():
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username erforderlich'}), 400

    if not data.get('uhrzeit'):
        data['uhrzeit'] = datetime.datetime.now().isoformat()

    statuses[username] = data
    print(f"[{NODE_NAME}] Status gespeichert: {username}")

    # Weiterleitung an Peer-Node via REST
    if PEER_URL:
        try:
            resp = requests.post(f'{PEER_URL}/replicate', json=data, timeout=2)
            print(f"[{NODE_NAME}] Repliziert an Peer -> HTTP {resp.status_code}")
        except Exception as e:
            print(f"[{NODE_NAME}] Peer nicht erreichbar: {e}")

    return jsonify({'message': 'Status gespeichert', 'status': data}), 201


@app.route('/replicate', methods=['POST'])
def replicate():
    """Endpunkt für Node-zu-Node Replikation."""
    data = request.get_json(force=True)
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': 'username erforderlich'}), 400
    statuses[username] = data
    print(f"[{NODE_NAME}] Status repliziert von Peer: {username}")
    return jsonify({'message': 'Repliziert'}), 200


@app.route('/status', methods=['GET'])
def get_all():
    return jsonify(list(statuses.values())), 200


@app.route('/status/<username>', methods=['GET'])
def get_one(username):
    if username in statuses:
        return jsonify(statuses[username]), 200
    return jsonify({'error': 'Nicht gefunden'}), 404


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'node': NODE_NAME, 'status': 'ok', 'entries': len(statuses)}), 200


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    PEER_URL = sys.argv[2] if len(sys.argv) > 2 else None
    NODE_NAME = sys.argv[3] if len(sys.argv) > 3 else f"Node-{port}"
    print(f"[{NODE_NAME}] Starte auf Port {port} | Peer: {PEER_URL or 'keiner'}")
    app.run(port=port, debug=False)
