import os, sys, requests, ssl, argparse, random, io, gzip, base64, gc, traceback, psutil, time, threading
import torch
import torch.nn as nn
import torch.optim as optim
from flask import Flask, request, jsonify
from flask_cors import CORS
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
from dotenv import load_dotenv
from model import BrainTumorCNN

# 1. Load Environment Variables
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOSPITAL_NAME = os.getenv("HOSPITAL_NAME")
HOSPITAL_NAME = "hospital_b"
# Use the Tailscale hostname we set in the SAN certificates
SERVER_URL = os.getenv("SERVER_URL", "https://laptop-3hb2ene1:5000") 
CHUNK_SIZE = 500_000 # Optimized for network stability

# Unifying paths to the standard /certs folder
CERT_PATH = os.path.join(BASE_DIR, "client_certs", f"{HOSPITAL_NAME}.crt")
KEY_PATH = os.path.join(BASE_DIR, "client_certs", f"{HOSPITAL_NAME}.key")
CA_PATH = os.path.join(BASE_DIR, "certs", "server_ca.crt")

app = Flask(__name__)
CORS(app)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
client_loader = None

# --- UTILITY FUNCTIONS ---

def get_dataloader(path):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    dataset = datasets.ImageFolder(root=path, transform=transform)
    return DataLoader(dataset, batch_size=16, shuffle=True)

def decode_weights_chunks(chunks):
    b64 = ''.join(chunks)
    compressed = base64.b64decode(b64)
    buffer = io.BytesIO(gzip.decompress(compressed))
    return torch.load(buffer, map_location=device)

def encode_weights_chunks(model_state):
    buffer = io.BytesIO()
    torch.save(model_state, buffer, _use_new_zipfile_serialization=False)
    compressed = gzip.compress(buffer.getvalue())
    b64 = base64.b64encode(compressed).decode('utf-8')
    return [b64[i:i+CHUNK_SIZE] for i in range(0, len(b64), CHUNK_SIZE)]

def add_differential_privacy_noise(weights, noise_level=0.01):
    noisy_weights = {}
    print(f"🔐 Adding {noise_level} Differential Privacy noise...")
    for key, tensor in weights.items():
        noise = torch.randn_like(tensor) * noise_level
        noisy_weights[key] = tensor + noise
    return noisy_weights

# --- BACKGROUND HEARTBEAT ---

def start_heartbeat():
    """Tells the server Hospital B is online and sends resource stats."""
    print(f"🛰 Heartbeat started for {HOSPITAL_NAME}...")
    while True:
        try:
            # interval=1 is critical for Linux/Fedora to get a non-zero reading
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            response = requests.post(
                f"{SERVER_URL}/check-in",
                json={
                    "hospital": HOSPITAL_NAME, 
                    "cpu": cpu, 
                    "ram": ram
                },
                cert=(CERT_PATH, KEY_PATH),
                verify=CA_PATH,
                timeout=15
            )
            
            if response.status_code == 200:
                pass
            else:
                print(f"⚠️ Server rejected heartbeat: {response.status_code}")

        except requests.exceptions.SSLError as e:
            print(f"🔐 Heartbeat SSL Error: Check if server_ca.crt matches the server's cert.")
        except Exception as e:
            print(f"🛰 Heartbeat failed to connect: {e}")
            
        time.sleep(15) # Check in every 15 seconds for the dashboard

def verify_node_status():
    """Kill-switch check: Is Hospital B still approved by Admin?"""
    print(f"🔒 Authenticating '{HOSPITAL_NAME}' via Tailscale...")
    if not os.path.exists(CERT_PATH):
        print(f"❌ CRITICAL: Certificate missing at {CERT_PATH}")
        sys.exit(1)
    try:
        response = requests.get(
            f"{SERVER_URL}/verify-node/{HOSPITAL_NAME}",
            cert=(CERT_PATH, KEY_PATH),
            verify=CA_PATH, 
            timeout=15
        )
        if response.status_code == 200:
            print(f"✅ Authorization Granted for {HOSPITAL_NAME}.")
        else:
            print(f"❌ ACCESS REVOKED: Check the Admin Dashboard.")
            sys.exit(1)
    except Exception as e:
        print(f"⚠️ Handshake Failed: {e}")
        sys.exit(1)

# --- FLASK ROUTES ---

@app.route('/train', methods=['POST'])
def train_model():
    try:
        print("\n📥 Round Started: Downloading global model...")
        data = request.json
        weights = decode_weights_chunks(data['weights_chunks'])
        
        model = BrainTumorCNN().to(device)
        model.load_state_dict(weights, strict=False)
        model.train()

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        # Local Epochs - UPDATED WITH DETAILED LOGGING
        for epoch in range(2):
            epoch_loss = 0.0
            correct = 0
            total = 0
            
            print(f"\n   🟢 Starting Epoch {epoch+1}/2...")
            for batch_idx, (imgs, labels) in enumerate(client_loader):
                imgs, labels = imgs.to(device), labels.to(device)
                optimizer.zero_grad()
                
                outputs = model(imgs)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
                
                epoch_loss += loss.item()
                
                # Calculate batch accuracy for logging purposes
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()
                
                # Print batch details
                batch_acc = 100 * correct / total
                print(f"      ↳ Batch {batch_idx+1:02d}/{len(client_loader):02d} | Loss: {loss.item():.4f} | Rolling Acc: {batch_acc:.2f}%")

            # Epoch summary
            avg_loss = epoch_loss / len(client_loader)
            epoch_acc = 100 * correct / total
            print(f"   ✅ Epoch {epoch+1} Complete | Avg Loss: {avg_loss:.4f} | Final Acc: {epoch_acc:.2f}%")

        # Differential Privacy Protection
        clean_weights = model.state_dict()
        protected_weights = add_differential_privacy_noise(clean_weights, noise_level=0.01)
        
        # Encode noisy weights to send back
        encoded_chunks = encode_weights_chunks(protected_weights)
        
        # Cleanup memory
        del model, weights, clean_weights, protected_weights
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()

        print("\n📤 Sending encrypted updates back to Central Server.")
        return jsonify({'weights_chunks': encoded_chunks, 'loss': epoch_loss})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--data-path', type=str, required=True)
    args = parser.parse_args()

    client_loader = get_dataloader(args.data_path)

    # 1. Kill-switch check
    verify_node_status()
    
    # 2. Start Background Heartbeat
    threading.Thread(target=start_heartbeat, daemon=True).start()

    # 3. Secure mTLS listener for Flask
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(CA_PATH)
    context.load_cert_chain(certfile=CERT_PATH, keyfile=KEY_PATH)

    print(f"🏥 {HOSPITAL_NAME} Online | Listening on https://0.0.0.0:{args.port}")
    app.run(host='0.0.0.0', port=args.port, ssl_context=context, debug=False)