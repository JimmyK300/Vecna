class HFTextEmbedding(TextEmbedding):
    def __init__(
        self,
        pretrained_model: str,
        name: str = "text_embedding",
        batch_size: int = 64, # Tăng batch_size lên vì text ngắn + FP16 rất nhẹ
        device: str | torch.device = "cpu",
        text_source: str | None = None,
        work_dir: Path | str = ".",
        *args,
        **kwargs,
    ):
        self.name = name
        self._batch_size = batch_size
        self._pretrained_model = pretrained_model
        self._text_source = text_source
        self._work_dir = Path(work_dir)
        
        self._tokenizer = AutoTokenizer.from_pretrained(pretrained_model)
        
        # FIX 2: Bật torch_dtype=torch.float16 để giảm 50% VRAM và tăng tốc độ infer
        self._model = AutoModel.from_pretrained(
            pretrained_model, 
            torch_dtype=torch.float16 
        )
        self._model.eval()
        self.to(device)

    # ... (Giữ nguyên hàm _load_text_for_keyframe) ...
    def _load_text_for_keyframe(self, image_path: Path | str) -> str:
        if self._text_source is None:
            return str(image_path)

        image_path = Path(image_path)
        text_path = self._work_dir.parent / constant.FEATURE_DIR / image_path.parent.stem / image_path.stem / f"{self._text_source}.npy"
        
        if not text_path.exists():
            return ""

        try:
            payload = np.load(text_path, allow_pickle=True)
        except Exception:
            return ""

        if isinstance(payload, np.ndarray):
            if payload.size == 0:
                return ""
            value = payload.reshape(-1)[0]
        else:
            value = payload

        if value is None:
            return ""
        return str(value)

    # BỎ HÀM _mean_pool ĐI VÌ NÓ VÔ DỤNG VỚI BGE

    def _encode_texts(self, texts: list[str]) -> np.ndarray:
        if len(texts) == 0:
            return np.array([])

        # BGE-M3 max length thực tế là 8192, nhưng để an toàn và nhanh thì 512 hoặc 1024 là đủ cho ASR/OCR
        tokenized = self._tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024, # BGE-M3 hỗ trợ context dài, tăng lên 1024 để không bị cắt mất nghĩa
        )
        tokenized = {k: v.to(self._device) for k, v in tokenized.items()}

        with torch.no_grad():
            outputs = self._model(**tokenized)
            
            # FIX 1: Lấy token [CLS] (index 0) thay vì Mean Pooling
            # Đây là chuẩn bài cho dòng BGE / BGE-M3
            cls_embedding = outputs.last_hidden_state[:, 0]
            
            # Normalize vector
            pooled = torch.nn.functional.normalize(cls_embedding, p=2, dim=-1)

        # Chuyển về float32 trước khi xuống CPU để tránh lỗi precision của numpy
        return pooled.float().cpu().numpy()

    # ... (Giữ nguyên get_features và get_text_features) ...
    def get_features(self, images, callback: Optional[Callable] = None):
        if len(images) == 0:
            return np.array([])

        texts = [self._load_text_for_keyframe(image) for image in images]
        num_batches = max(1, (len(texts) + self._batch_size - 1) // self._batch_size)
        features = []

        if callback:
            callback(self, 0, len(texts), [])

        for batch_index in range(num_batches):
            batch_texts = texts[batch_index * self._batch_size : (batch_index + 1) * self._batch_size]
            if not batch_texts:
                continue
            features.append(self._encode_texts(batch_texts))
            if callback:
                completed = min(len(texts), (batch_index + 1) * self._batch_size)
                callback(self, completed, len(texts), features)

        if len(features) == 0:
            return np.array([])

        return np.concatenate(features, axis=0)

    def get_text_features(self, texts: list[str] | str | np.ndarray, callback: Optional[Callable] = None) -> Any:
        if isinstance(texts, np.ndarray):
            texts = list(texts.tolist())
        if isinstance(texts, str):
            texts = [texts]
        return self._encode_texts([str(text) for text in texts])

    def to(self, device):
        self._device = torch.device(device)
        self._model.to(self._device)
