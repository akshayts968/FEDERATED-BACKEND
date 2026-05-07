import torch
import torch.nn as nn
import torch.optim as optim
import gzip, base64, io, os, random, gc, threading, datetime
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from model import BrainTumorCNN
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
from phe import paillier

# -------------------- CONFIG --------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'
CORS(app)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

HOSPITAL_CREDENTIALS = {
    "admin": {"password": "admin_password", "role": "ADMIN"},
    "hospital_a": {"password": "password123", "role": "HOSPITAL"},
    "hospital_b": {"password": "password456", "role": "HOSPITAL"}
}

CLIENT_CONFIG = {
    "hospital_a": "http://10.48.242.137:5001",
    "hospital_b": "http://10.48.242.136:5002",
}
REQUIRED_CLIENTS = ["hospital_a", "hospital_b"]
CLIENTS_PER_ROUND = 2

training_state = {
    "status": "Idle",
    "current_round": 0,
    "total_rounds": 10,
    "accuracy_history": [],
    "loss_history": []
}
connected_clients = set()
global_model = BrainTumorCNN()
CHUNK_SIZE = 500_000
TEST_PATH = "./data/Testing"

# -------------------- DATA --------------------
def get_test_loader(path):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
    ])
    dataset = datasets.ImageFolder(root=path, transform=transform)
    return DataLoader(dataset, batch_size=16, shuffle=False, num_workers=0)

test_loader = get_test_loader(TEST_PATH)

def evaluate_model(model, loader):
    model.eval()
    model.to(device)
    correct, total = 0, 0
    with torch.no_grad():
        for imgs, labels in loader:
            imgs, labels = imgs.to(device), labels.to(device)
            outputs = model(imgs)
            _, predicted = torch.max(outputs.data, 1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)
    return (correct / total) * 100 if total > 0 else 0.0

def encode_weights_chunks(model: nn.Module):
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer, _use_new_zipfile_serialization=False)
    compressed = gzip.compress(buffer.getvalue())
    buffer.close()
    b64 = base64.b64encode(compressed).decode('utf-8')
    return [b64[i:i+CHUNK_SIZE] for i in range(0, len(b64), CHUNK_SIZE)]

def decode_weights_chunks(chunks: list):
    b64 = ''.join(chunks)
    compressed = base64.b64decode(b64)
    buffer = io.BytesIO(gzip.decompress(compressed))
    state_dict = torch.load(buffer, map_location=device)
    buffer.close()
    return state_dict


def encrypt_tensor(tensor: torch.Tensor, public_key: paillier.PaillierPublicKey, scale: int = 1e5):
    """
    Flatten tensor, scale to int, and encrypt each element using Paillier.
    Returns:
        - List of encrypted numbers
        - Original shape of tensor
    """
    flat = tensor.detach().cpu().flatten()
    encrypted_flat = [public_key.encrypt(int(x.item()*scale)) for x in flat]
    return encrypted_flat, tensor.shape

def decrypt_tensor(encrypted_list: list, private_key: paillier.PaillierPrivateKey, shape, scale: int = 1e5):
    """
    Decrypt list of Paillier encrypted numbers and reshape to original tensor.
    """
    decrypted = [private_key.decrypt(x)/scale for x in encrypted_list]
    return torch.tensor(decrypted).reshape(shape)


# -------------------- SECURE AGGREGATION --------------------
def aggregate_encrypted_clients(encrypted_clients: list, shapes: dict, private_key: paillier.PaillierPrivateKey):
    """Decrypt and average encrypted client updates."""
    avg_state = {}
    for name in shapes:
        # sum over clients
        total = None
        for client_enc in encrypted_clients:
            flat_enc = client_enc[name]
            if total is None:
                total = flat_enc
            else:
                total = [x + y for x, y in zip(total, flat_enc)]
        # average and decrypt
        avg_flat = [private_key.decrypt(x)/len(encrypted_clients)/1e5 for x in total]
        avg_tensor = torch.tensor(avg_flat, device=device).reshape(shapes[name])
        avg_state[name] = avg_tensor
    return avg_state

# -------------------- AUTH --------------------
def token_required(f):
    from functools import wraps
    import jwt
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token:
            return jsonify({'message': 'Token missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except Exception as e:
            return jsonify({'message': f'Invalid token: {e}'}), 401
        return f(data, *args, **kwargs)
    return decorated

@app.route('/login', methods=['POST'])
def login():
    import jwt
    auth = request.json
    username, password = auth.get('username'), auth.get('password')
    user_info = HOSPITAL_CREDENTIALS.get(username)
    if user_info and user_info['password'] == password:
        token = jwt.encode({
            'user': username,
            'role': user_info['role'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token, 'role': user_info['role']})
    return jsonify({'message': 'Invalid credentials'}), 403

@app.route('/check-in', methods=['POST'])
@token_required
def check_in(token_data):
    user, role = token_data['user'], token_data['role']
    if role != 'HOSPITAL' or user not in REQUIRED_CLIENTS:
        return jsonify({"message": "Unauthorized"}), 403
    connected_clients.add(user)
    print(f"Hospital '{user}' checked in. Waiting room: {list(connected_clients)}")
    if set(REQUIRED_CLIENTS).issubset(connected_clients) and training_state["status"] == "WAITING_FOR_CLIENTS":
        threading.Thread(target=run_federated_training).start()
    return jsonify({"message": f"Check-in successful. {len(connected_clients)}/{len(REQUIRED_CLIENTS)} clients ready."})


@app.route('/training-status', methods=['GET'])
def training_status():
    status_data = training_state.copy()
    status_data['connected_clients'] = list(connected_clients)
    status_data['required_clients_count'] = len(REQUIRED_CLIENTS)
    return jsonify(status_data)



def start_training_route(token_data):
    if token_data['role'] != 'ADMIN':
        return jsonify({"message": "Only an admin can start training!"}), 403
    params = request.json or {}
    total_rounds = params.get('total_rounds', 10)
    clients_per_round = params.get('clients_per_round', 2)
    global CLIENTS_PER_ROUND
    CLIENTS_PER_ROUND = clients_per_round
    training_state.update({
        "status": "WAITING_FOR_CLIENTS",
        "current_round": 0,
        "total_rounds": total_rounds,
        "accuracy_history": [],
        "loss_history": []
    })
    print(f"Admin initiated training: {total_rounds} rounds, {clients_per_round} clients/round.")
    if set(REQUIRED_CLIENTS).issubset(connected_clients):
        threading.Thread(target=run_federated_training).start()
    return jsonify({"message": "Training initiated. Waiting for hospitals."})

@app.route('/start-training', methods=['POST'])
@token_required
def start_training_route(token_data):
    if token_data['role'] != 'ADMIN':
        return jsonify({"message": "Only an admin can start training!"}), 403
    params = request.json or {}
    total_rounds = params.get('total_rounds', 10)
    clients_per_round = params.get('clients_per_round', 2)
    global CLIENTS_PER_ROUND
    CLIENTS_PER_ROUND = clients_per_round
    training_state.update({
        "status": "WAITING_FOR_CLIENTS",
        "current_round": 0,
        "total_rounds": total_rounds,
        "accuracy_history": [],
        "loss_history": []
    })
    print(f"Admin initiated training: {total_rounds} rounds, {clients_per_round} clients/round.")
    if set(REQUIRED_CLIENTS).issubset(connected_clients):
        threading.Thread(target=run_federated_training).start()
    return jsonify({"message": "Training initiated. Waiting for hospitals."})

# -------------------- TRAINING --------------------
def run_federated_training():
    global training_state, global_model
    print("✅ All clients connected! Starting federated training...")
    training_state['status'] = 'TRAINING'
    os.makedirs("model", exist_ok=True)

    # Generate Paillier keypair for this round
    public_key, private_key = paillier.generate_paillier_keypair()

    for r in range(training_state["total_rounds"]):
        training_state['current_round'] = r + 1
        print(f"\n--- Round {r+1}/{training_state['total_rounds']} ---")
        if len(connected_clients) < CLIENTS_PER_ROUND:
            print("Not enough clients connected. Skipping round.")
            continue

        selected_clients = random.sample(list(connected_clients), CLIENTS_PER_ROUND)
        encoded_chunks = encode_weights_chunks(global_model)

        client_encrypted_updates = []
        client_shapes = None
        client_losses = []
        client_accuracies = []

        for client_user in selected_clients:
            client_url = CLIENT_CONFIG.get(client_user)
            try:
                print(f"Sending model to {client_user}...")
                response = requests.post(
                    f"{client_url}/train",
                    json={'weights_chunks': encoded_chunks},
                    timeout=1800
                )
                if response.status_code == 200:
                    resp_data = response.json()
                    # Decode and store encrypted updates (simulate)
                    client_weights = decode_weights_chunks(resp_data['weights_chunks'])
                    encrypted_state = {}
                    shapes = {}
                    for name, param in client_weights.items():
                        enc, shape = encrypt_tensor(param, public_key)
                        encrypted_state[name] = enc
                        shapes[name] = shape
                    client_encrypted_updates.append(encrypted_state)
                    client_shapes = shapes
                    client_losses.append(resp_data.get('loss', 0))
                    client_accuracies.append(resp_data.get('accuracy', 0))
                    print(f"✅ Received update from {client_user} | Loss: {resp_data.get('loss'):.4f} | Acc: {resp_data.get('accuracy', 0.0):.2f}")
                else:
                    print(f"⚠️ Error from {client_user}: {response.status_code} {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"❌ Could not connect to {client_user}. Error: {e}")

        if not client_encrypted_updates:
            print("⚠️ No client updates received. Skipping model update.")
            continue

        # -------------------- SECURE AGGREGATION --------------------
        avg_weights = aggregate_encrypted_clients(client_encrypted_updates, client_shapes, private_key)
        global_model.load_state_dict(avg_weights)

        # Update training stats
        avg_loss = sum(client_losses) / len(client_losses)
        avg_accuracy = sum(client_accuracies) / len(client_accuracies)
        training_state["loss_history"].append(avg_loss)
        training_state["accuracy_history"].append(avg_accuracy)

        # Evaluate on test set
        test_acc = evaluate_model(global_model, test_loader)
        print(f"📊 Round {r+1} Test Accuracy: {test_acc:.2f}%")
        training_state["accuracy_history"][-1] = test_acc

        del client_encrypted_updates, avg_weights, client_losses, client_accuracies
        torch.cuda.empty_cache()
        gc.collect()

    # Save final global model
    final_accuracy = round(test_acc, 2)
    model_version = f"v{training_state['current_round']}"
    model_filename = f"model/global_model_{model_version}_acc_{final_accuracy:.2f}.pth"
    torch.save(global_model.state_dict(), model_filename)
    print(f"✅ Global model saved after final round: {model_filename}")
    connected_clients.clear()
    training_state['status'] = 'Completed'

# -------------------- MAIN --------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
