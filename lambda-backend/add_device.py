from mosquitto_api import pub_settings, add_device
import mosquitto_api
from config import supabase 
from get_devices import get_devices
from build_binary import build_binary
import uuid
from utils import error_response, success_response
import base64
import json
import binascii
import boto3
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.x509 import load_pem_x509_certificate
import time

def encrypt_group_key(group_key: bytes, cert_pem: str) -> bytes:
    cert = load_pem_x509_certificate(cert_pem.encode())
    pubkey = cert.public_key()
    encrypted = pubkey.encrypt(
        group_key,
        padding.OAEP(
            mgf=padding.MGF1(hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return encrypted

def add_device(uid, platform):
    # Add device to mosquitto
    res = mosquitto_api.add_device(uid)
    
    if res["status_code"] != 200:
        return error_response("Failed to add device", res)

    # Get cert and key for user
    cert = res["json"].get("cert")
    key = res["json"].get("key")

    if not cert or not key:
        return error_response("Cert or key missing in response")

    # Get group key for the user
    query = supabase.table("user_keys").select("group_key").eq("user_id", uid).execute()

    group_key_data = query.data
    if not group_key_data or "group_key" not in group_key_data[0]:
        return error_response("No group_key found for user", query)

    group_key_hex = group_key_data[0]["group_key"]
    if group_key_hex.startswith("\\x"):
        group_key = binascii.unhexlify(group_key_hex[2:])
    else:
        return error_response("group_key format invalid", group_key_hex)
        
    # Encrypt group key for user
    try:
        encrypted_group_key = encrypt_group_key(group_key, cert)
    except Exception as e:
        return error_response("Failed to encrypt group key with device cert")
    
    # Create a unique device_id to embed into binary
    device_id = str(uuid.uuid4())

    # Add device to DB
    data = {
        "deviceid": device_id,
        "uid": uid,
        "settings": {
            "nickname": "Unnamed Device",
            "enabled": True,
            "auto_copy": False,
            "auto_paste": False,
            "cache_time": 30,
            "hotkey": "",
            "enable_hotkey": False,
            "notification_vol": 1.0,
            "muted": False,
            "send_to_self": True,
            "ble_always_off": False,
            "startup": True,
            "destroy": False
        }, 
        "cert": cert
    }

    try:
        insert_res = supabase.table("device").insert(data).execute()
    except Exception as e:
        return error_response("Failed to insert device into database")
    
    # Fetch existing settings
    query = get_devices(uid)
    
    if query.get("status_code") != 200:
        return error_response("Failed to set up device settings")
    
    settings = query.get("json", {}).get("devices", [])

    # Set up settings
    res = pub_settings(settings, uid)

    if res.get("status_code")!= 200:
        return error_response("Failed to set up device settings")

    # Build binary and return it
    binary, enc_key_b64 = build_binary(platform, device_id, cert, key, encrypted_group_key)
    if binary is None or enc_key_b64 is None:
        return error_response("Failed to build device binary")

    try:
        supabase.table("encryption_keys").insert({"deviceid": device_id, "encryption_key": enc_key_b64}).execute()
    except  Exception as e:
        return error_response("Could not insert encryption_key into supabase")
    
    try:
        output_bucket = "hoppyshare-binaries"
        output_key = f"outputs/{device_id}_{int(time.time())}.bin"

        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=output_bucket,
            Key=output_key,
            Body=binary,
            ContentType="application/octet-stream"
        )

        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": output_bucket, "Key": output_key},
            ExpiresIn=300  # 5 minutes
        )

        return success_response({"download_url": url})
    except Exception as e:
        return error_response(str(e))

