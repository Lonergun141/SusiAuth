#!/bin/bash
# Generate RSA keys for JWT
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -outform PEM -pubout -out keys/public.pem
