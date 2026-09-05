# Vecna - HCMC AI Challenge

## Contributors

- Lê Tuấn Kiệt ([@ProfK602170](https://github.com/ProfK602170))
- Nguyễn Lê Minh Hoàng ([@nlmhoagn](https://github.com/nlmhoagn))
- Cao Chí Minh ([@JimmyK300](https://github.com/JimmyK300))
- Ngô Đắc Minh ([@kinus-is-coding](https://github.com/kinus-is-coding))
- Phan Hiếu Minh ([@PhanHieuMinh](https://github.com/PhanHieuMinh))

## Dependencies

1. Install [ffmpeg](https://ffmpeg.org/)

2. Install [tesseract](https://github.com/tesseract-ocr/tesseract)

3. Install [Docker](https://www.docker.com/) (running for Milvus Vector Database)

## Guideline

1. Install the repository

```bash
git clone https://github.com/nlmhoagn/Vecna.git
cd Vecna/aic51-src
pip install -e .
```

or directly via pip:

```bash
pip install git+https://github.com/nlmhoagn/Vecna.git#subdirectory=aic51-src
```

2. Initialize workspace

```bash
mkdir workspace
cd workspace
aic51-cli init
```
- Change configuration in `config.yaml` (Optional)

3. Add videos to workspace

```bash
aic51-cli add <path/to/videos> -d -kc
```

4. Analyse videos

```bash
aic51-cli analyse
```

5. Index videos

```bash
aic51-cli index
```

6. Run webui

```bash
aic51-cli serve
```
