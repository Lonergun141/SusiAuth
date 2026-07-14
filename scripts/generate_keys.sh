#!/bin/bash
# Generate RSA keys for JWT.
# Filenames must match JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH defaults in
# config/settings/base.py (keys/jwt_private.pem, keys/jwt_public.pem).
mkdir -p keys
openssl genrsa -out keys/jwt_private.pem 2048
openssl rsa -in keys/jwt_private.pem -outform PEM -pubout -out keys/jwt_public.pem
