import os
import sys
import time
import threading
import requests
import ssl
import argparse
import psutil
import torch
import torch.nn as nn
import torch.optim as optim
import io, gzip, base64, gc, random, traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
from dotenv import load_dotenv
from model import BrainTumorCNN

# 1. LOAD CONFIGURATION
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOSPITAL_NAME = os.getenv("HOSPITAL_NAME", "mist")
SERVER_URL = os.getenv("SERVER_URL", "https://federated-backend-production.up.railway.app")

# Pathing (Absolute paths so it works from any directory)
CERT_PATH = os.path.join(BASE_DIR, "certs", f"{HOSPITAL_NAME}.crt")
KEY_PATH = os.path.join(BASE_DIR, "certs", f"{HOSPITAL_NAME}.key")
CA_PATH = os.path.join(BASE_DIR, "certs", "server_ca.crt")

# Cloud vs Local TLS Verification
# For public cloud domains (e.g. Railway, Vercel, public HTTPS), use standard root CA (verify=True).
# For internal self-hosted servers with custom private CA, use CA_PATH if it exists.
if "railway.app" in SERVER_URL or "localhost" not in SERVER_URL and not SERVER_URL.startswith("http://"):
    # If CA_PATH does not exist or we are on public cloud domain, use default trusted roots
    VERIFY_SSL = CA_PATH if (os.path.exists(CA_PATH) and ("localhost" in SERVER_URL or "127.0.0.1" in SERVER_URL)) else True
else:
    VERIFY_SSL = CA_PATH if os.path.exists(CA_PATH) else True

app = Flask(__name__)
CORS(app)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Global state for training
client_loader = None
incoming_port = None
CHUNK_SIZE = 500_000 

# --- BACKGROUND HEARTBEAT ---

def start_heartbeat():
    """Tells the server Hospital B is online and sends resource stats."""
    print(f"🛰️ Heartbeat started for {HOSPITAL_NAME}...")
    while True:
        try:
            # interval=1 is critical for Linux/Fedora to get a non-zero reading
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            
            body = {
                "hospital": HOSPITAL_NAME, 
                "cpu": cpu, 
                "ram": ram
            }
            if incoming_port:
                body["port"] = incoming_port

            response = requests.post(
                f"{SERVER_URL}/check-in",
                json=body,
                cert=(CERT_PATH, KEY_PATH) if (os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH)) else None,
                verify=VERIFY_SSL,
                timeout=5
            )
            
            if response.status_code == 200:
                # Optional: uncomment for local debugging
                # print(f"✅ Heartbeat sent: CPU {cpu}%") 
                pass
            else:
                print(f"⚠️ Server rejected heartbeat: {response.status_code}")

        except requests.exceptions.SSLError as e:
            print(f"🔐 Heartbeat SSL Error: Check if server_ca.crt matches the server's cert.")
        except Exception as e:
            print(f"🛰️ Heartbeat failed to connect: {e}")
            
        time.sleep(15) # Check in every 15 seconds for the dashboard
def add_differential_privacy_noise(weights, noise_level=0.01):
    """Adds Gaussian Noise to weights to protect patient privacy (DP)."""
    noisy_weights = {}
    for key, tensor in weights.items():
        noise = torch.randn_like(tensor) * noise_level
        noisy_weights[key] = tensor + noise
    return noisy_weights

def decode_weights_chunks(chunks):
    b64 = ''.join(chunks)
    compressed = base64.b64decode(b64)
    del b64
    raw = gzip.decompress(compressed)
    del compressed
    buffer = io.BytesIO(raw)
    del raw
    state_dict = torch.load(buffer, map_location=device)
    buffer.close()
    del buffer
    gc.collect()
    return state_dict

def encode_weights_chunks(model_state):
    state = model_state.state_dict() if hasattr(model_state, 'state_dict') else model_state
    buffer = io.BytesIO()
    torch.save(state, buffer, _use_new_zipfile_serialization=False)
    raw = buffer.getvalue()
    buffer.close()
    compressed = gzip.compress(raw, compresslevel=1)
    del raw
    b64 = base64.b64encode(compressed).decode('utf-8')
    del compressed
    gc.collect()
    return [b64[i:i+CHUNK_SIZE] for i in range(0, len(b64), CHUNK_SIZE)]

# --- BACKGROUND HEARTBEAT (The Missing Link) ---

@app.route('/train', methods=['POST'])
def train_model():
    global client_loader
    if client_loader is None:
        return jsonify({'error': 'Data loader not initialized'}), 500

    try:
        data = request.json
        weights = decode_weights_chunks(data['weights_chunks'])
        
        # Initialize and Train
        model = BrainTumorCNN().to(device)
        model.load_state_dict(weights, strict=False)
        model.train()

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        # Local training loop (2 epochs)
        for _ in range(2):
            for imgs, labels in client_loader:
                imgs, labels = imgs.to(device), labels.to(device)
                optimizer.zero_grad()
                outputs = model(imgs)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

        # 🔐 APPLY PRIVACY PROTECTION
        clean_weights = model.state_dict()
        protected_weights = add_differential_privacy_noise(clean_weights, noise_level=0.01)

        # Encode the NOISY weights to send back
        encoded_chunks = encode_weights_chunks(protected_weights)

        # Cleanup
        del model, weights, clean_weights, protected_weights
        torch.cuda.empty_cache()
        gc.collect()

        return jsonify({'weights_chunks': encoded_chunks, 'status': 'success'})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def train_and_submit_now():
    """Trains locally on private hospital data and pushes update directly to central server."""
    global client_loader
    print(f"🔄 [ANY-TIME FL] Fetching latest global model from {SERVER_URL}...")
    try:
        client_cert = (CERT_PATH, KEY_PATH) if (os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH)) else None
        res = requests.get(
            f"{SERVER_URL}/get-global-model",
            cert=client_cert,
            verify=VERIFY_SSL,
            timeout=180,
            stream=True
        )
        if res.status_code != 200:
            print(f"❌ Failed to get global model: {res.status_code}")
            return

        content_type = res.headers.get("content-type", "")
        if "application/json" in content_type:
            data = res.json()
            weights = decode_weights_chunks(data['weights_chunks'])
        else:
            buffer = io.BytesIO(res.content)
            weights = torch.load(buffer, map_location=device)
            buffer.close()
            del buffer

        print(f"🧠 Training locally on private hospital data (raw images never leave)...")
        model = BrainTumorCNN().to(device)
        model.load_state_dict(weights, strict=False)
        model.train()

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        total_loss = 0.0
        correct, total = 0, 0
        total_batches = len(client_loader)
        last_progress_time = time.time()
        start_time = time.time()

        for epoch in range(2):
            print(f"\n🚀 [EPOCH {epoch+1}/2] Starting local training across {total_batches} batches...")
            for b_idx, (imgs, labels) in enumerate(client_loader, 1):
                imgs, labels = imgs.to(device), labels.to(device)
                optimizer.zero_grad()
                outputs = model(imgs)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                _, preds = torch.max(outputs, 1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)

                # Periodic progress output (every 60 seconds or every 50 batches)
                now = time.time()
                if now - last_progress_time >= 60 or b_idx == total_batches or b_idx % 50 == 0:
                    curr_loss = total_loss / max(1, (epoch * total_batches + b_idx))
                    curr_acc = (correct / max(1, total)) * 100
                    elapsed = now - start_time
                    percent = ((epoch * total_batches + b_idx) / (2 * total_batches)) * 100
                    print(f"⏱️ [PROGRESS] Epoch {epoch+1}/2 | Batch {b_idx}/{total_batches} ({percent:.1f}%) | Loss: {curr_loss:.4f} | Acc: {curr_acc:.2f}% | Elapsed: {int(elapsed)}s")
                    last_progress_time = now

        epoch_loss = total_loss / max(1, len(client_loader) * 2)
        epoch_acc = (correct / max(1, total)) * 100

        print(f"🔐 Adding Differential Privacy noise to trained weights...")
        clean_weights = model.state_dict()
        protected_weights = add_differential_privacy_noise(clean_weights, noise_level=0.01)

        print(f"📡 Submitting local update to {SERVER_URL}/submit-update...")
        fp16_weights = {k: v.half() if v.is_floating_point() else v for k, v in protected_weights.items()}
        buf = io.BytesIO()
        torch.save(fp16_weights, buf, _use_new_zipfile_serialization=False)
        buf.seek(0)

        del model, weights, clean_weights, protected_weights, fp16_weights
        torch.cuda.empty_cache()
        gc.collect()

        client_cert = (CERT_PATH, KEY_PATH) if (os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH)) else None
        files = {
            'weights_file': ('weights.pth', buf, 'application/octet-stream')
        }
        form_data = {
            "hospital": HOSPITAL_NAME,
            "loss": str(epoch_loss),
            "accuracy": str(epoch_acc)
        }
        submit_res = requests.post(
            f"{SERVER_URL}/submit-update",
            data=form_data,
            files=files,
            cert=client_cert,
            verify=VERIFY_SSL,
            timeout=180
        )
        buf.close()
        del buf
        if submit_res.status_code == 200:
            msg = submit_res.json().get('message', 'Update submitted successfully')
            print(f"✅ Success: {msg}")
        else:
            print(f"⚠️ Submission response: {submit_res.status_code} - {submit_res.text}")
    except Exception as e:
        print(f"❌ Train and submit error: {e}")

def verify_node_status():
    """The 'Kill Switch': Checks if the Admin has approved this node."""
    print(f"🔒 Verifying mTLS identity with {SERVER_URL}...")
    try:
        client_cert = (CERT_PATH, KEY_PATH) if (os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH)) else None
        response = requests.get(
            f"{SERVER_URL}/verify-node/{HOSPITAL_NAME}", 
            cert=client_cert,
            verify=VERIFY_SSL,
            timeout=15
        )
        if response.status_code != 200:
            print("❌ NODE REVOKED: This node is not authorized to join the federation.")
            sys.exit(1)
        print("✅ Node Verified.")
    except Exception as e:
        print(f"❌ CONNECTION ERROR: Could not reach central server. {e}")
        sys.exit(1)

# --- BOOT LOGIC ---

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Federated Learning Hospital Node")
    parser.add_argument('--port', type=int, default=int(os.getenv("PORT", 5001)), help='Port for node server (defaults to 5001 or PORT env)')
    parser.add_argument('--data-path', type=str, default=os.getenv("DATA_PATH", "./data/Train"), help='Path to local MRI images (defaults to ./data/Train)')
    parser.add_argument('--train-now', action='store_true', help='Train and submit model update immediately (any-time participation)')
    args = parser.parse_args()

    incoming_port = args.port

    # Verify data folder exists before trying to load
    if not os.path.exists(args.data_path):
        os.makedirs(args.data_path, exist_ok=True)
        print(f"⚠️ Warning: Dataset folder '{args.data_path}' was empty or not found. Created directory.")
        print(f"👉 Please place your MRI class folders inside '{args.data_path}' and restart.")

    # 1. Load Data
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
    ])
    try:
        dataset = datasets.ImageFolder(root=args.data_path, transform=transform)
        client_loader = DataLoader(dataset, batch_size=16, shuffle=True)
        print(f"📊 Successfully loaded {len(dataset)} MRI images from '{args.data_path}'.")
    except Exception as data_err:
        print(f"⚠️ Could not load images from '{args.data_path}': {data_err}")
        print("ℹ️ Node will stay online for heartbeats, but cannot train until MRI images are placed.")

    # 2. Security Check (Kill Switch)
    verify_node_status()

    # 3. Start Heartbeat Thread
    threading.Thread(target=start_heartbeat, daemon=True).start()

    # 3.5 Any-Time Participation Mode
    if args.train_now:
        threading.Thread(target=train_and_submit_now, daemon=True).start()

    # 4. Prepare SSL Context for Flask
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(CA_PATH)
    context.load_cert_chain(certfile=CERT_PATH, keyfile=KEY_PATH)

    print(f"🏥 Hospital {HOSPITAL_NAME} online at https://0.0.0.0:{args.port}")
    app.run(host='0.0.0.0', port=args.port, ssl_context=context, debug=False)