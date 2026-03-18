# Import ZeroMQ
import zmq


def run():

    # Define Variables
    server_public, server_secret = zmq.curve_keypair()
    client_public, client_secret = zmq.curve_keypair()

    # Ask password for Studio
    print("\n*******************************")
    print("\n*** KEYGEN ***")
    print("*******************************")
    studio_pass = input("\nEnter Password for OST Studio: ")

    # Print resuts
    print("\n--- Paste this into your settings.ini ---\n")
    print("[Security]")
    print(f"server_public = {server_public.decode('ascii')}")
    print(f"server_secret = {server_secret.decode('ascii')}")
    print(f"client_public = {client_public.decode('ascii')}")
    print(f"client_secret = {client_secret.decode('ascii')}")
    print(f"studio_password = {studio_pass}")
