#!/usr/bin/env bash
set -euo pipefail

LAMBDA_DIR="$(cd "$(dirname "$0")/../lambda" && pwd)"
OUTPUT_DIR="$(cd "$(dirname "$0")/../tmp/lambda" && pwd)"
OUTPUT_ZIP="${OUTPUT_DIR}/worker.zip"
VENDOR_DIR="${LAMBDA_DIR}/vendor"

echo "Packaging Lambda function from ${LAMBDA_DIR}..."

cd "${LAMBDA_DIR}"
mkdir -p "${OUTPUT_DIR}"
rm -f "${OUTPUT_ZIP}"
rm -rf "${VENDOR_DIR}"

echo "Installing dependencies..."
pip install -q -t "${VENDOR_DIR}" -r requirements.txt || {
  echo "ERROR: Failed to install Lambda dependencies"
  rm -rf "${VENDOR_DIR}"
  exit 1
}

echo "Creating deployment package..."
zip -r "${OUTPUT_ZIP}" \
  handler.py \
  vendor/ \
  -x "tests/*" "__pycache__/*" "*.pyc"

if [ ! -f "${OUTPUT_ZIP}" ]; then
  echo "ERROR: Failed to create deployment package"
  exit 1
fi

rm -rf "${VENDOR_DIR}"

echo "Lambda deployment package created at ${OUTPUT_ZIP}"
echo "Size: $(du -h "${OUTPUT_ZIP}" | cut -f1)"
