import urllib3
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

# Suppress warnings for self-signed certificates during internal requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. Load Environment Variables
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOSPITAL_NAME = os.getenv("HOSPITAL_NAME")
# --- HOSPITAL B CONFIGURATION ---
HOSPITAL_NAME = "hospital_a"
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
    return DataLoader(dataset, batch_size=16, shuffle=True, num_workers=0)

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
    print(f"🛰️ Heartbeat started for {HOSPITAL_NAME}...")
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
            verify=CA_PATH, # No more verify=False!
            timeout=5
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
import traceback # Add this at the top of your file if it's not there

@app.route('/train', methods=['POST'])
def train_model():
    global client_loader
    if client_loader is None:
        return jsonify({'error': 'Data loader not initialized'}), 500

    try:
        print("📥 Received global model weights. Starting local training...")
        data = request.json
        weights_chunks = data['weights_chunks']
        model_version = data.get('version', f'v{random.randint(1000,9999)}')
        weights = decode_weights_chunks(weights_chunks)

        model = BrainTumorCNN().to(device)
        model.load_state_dict(weights, strict=False)
        model.train()

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        # --- CORRECTED PYTORCH LOOP ---
        for epoch in range(2): # Local Epochs
            epoch_loss = 0.0
            for imgs, labels in client_loader:
                imgs, labels = imgs.to(device), labels.to(device)
                
                optimizer.zero_grad()                  # 1. Clear old gradients
                outputs = model(imgs)                  # 2. Forward pass
                loss = criterion(outputs, labels)      # 3. Calculate loss
                loss.backward()                        # 4. Backward pass (calculate new gradients)
                optimizer.step()                       # 5. Update weights
                
                epoch_loss += loss.item()
            print(f"   -> Epoch {epoch+1}/2 Complete. Loss: {epoch_loss/len(client_loader):.4f}")

        # Differential Privacy & Encoding
        clean_weights = model.state_dict()
        protected_weights = add_differential_privacy_noise(clean_weights)
        
        model.load_state_dict(protected_weights)
        encoded_chunks = encode_weights_chunks(model.state_dict())
        
        # Cleanup
        del model, clean_weights, protected_weights
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        print("📤 Local training complete. Sending updated weights back.")
        return jsonify({'weights_chunks': encoded_chunks, 'loss': epoch_loss})

    except Exception as e:
        print("\n❌ FATAL ERROR IN TRAINING ROUTINE:")
        traceback.print_exc() # This prints the exact line that crashed in the terminal
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

    print(f"🏥 Hospital A Online | Listening on https://0.0.0.0:{args.port}")
    app.run(host='0.0.0.0', port=args.port, ssl_context=context, debug=False)