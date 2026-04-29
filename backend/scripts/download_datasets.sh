#!/bin/bash
# Download HDFS and BGL datasets from Loghub (Zenodo)
set -e

DATA_DIR="data/raw"
mkdir -p "$DATA_DIR"

echo "[download] Downloading HDFS dataset..."
if [ ! -f "$DATA_DIR/HDFS.log" ]; then
    wget -P "$DATA_DIR" https://zenodo.org/records/8196385/files/HDFS_v1.zip
    unzip "$DATA_DIR/HDFS_v1.zip" -d "$DATA_DIR/hdfs_tmp"
    mv "$DATA_DIR/hdfs_tmp/"* "$DATA_DIR/"
    rm -rf "$DATA_DIR/hdfs_tmp" "$DATA_DIR/HDFS_v1.zip"
    echo "[download] HDFS dataset ready"
else
    echo "[download] HDFS dataset already exists, skipping"
fi

echo "[download] Downloading BGL dataset..."
if [ ! -f "$DATA_DIR/BGL.log" ]; then
    wget -P "$DATA_DIR" https://zenodo.org/records/8196385/files/BGL.zip
    unzip "$DATA_DIR/BGL.zip" -d "$DATA_DIR/bgl_tmp"
    mv "$DATA_DIR/bgl_tmp/"* "$DATA_DIR/"
    rm -rf "$DATA_DIR/bgl_tmp" "$DATA_DIR/BGL.zip"
    echo "[download] BGL dataset ready"
else
    echo "[download] BGL dataset already exists, skipping"
fi

echo "[download] All datasets ready in $DATA_DIR"
