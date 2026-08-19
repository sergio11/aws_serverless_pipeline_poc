#!/usr/bin/env bash
set -euo pipefail

LAMBDA_DIR="$(cd "$(dirname "$0")/../lambda" && pwd)"
OUTPUT_DIR="$(cd "$(dirname "$0")/../terraform" && pwd)"
OUTPUT_ZIP="${OUTPUT_DIR}/lambda-deployment.zip"

echo "Packaging Lambda function from ${LAMBDA_DIR}..."

cd "${LAMBDA_DIR}"
rm -f "${OUTPUT_ZIP}"

zip -r "${OUTPUT_ZIP}" \
  handler.py \
  requirements.txt \
  -x "tests/*" "__pycache__/*" "*.pyc"

echo "Lambda deployment package created at ${OUTPUT_ZIP}"
echo "Size: $(du -h "${OUTPUT_ZIP}" | cut -f1)"
