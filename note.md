# setup gpu
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

or

pip install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

pip install -e .

# download numpy
pip install numpy==2.5.1

# download whisperx
pip install whisperx --no-deps

pip install faster-whisper "ctranslate2>=4.5.0" pyannote.audio nltk pandas
# RIP milvus
docker rm -f milvus-standalone milvus-etcd milvus-minio

docker volume rm \
  milvus-standalone_milvus-etcd \
  milvus-standalone_milvus-minio \
  milvus-standalone_milvus-standalone

docker compose up -d