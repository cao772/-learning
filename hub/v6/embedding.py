"""Optional local CPU encoder. No remote inference, remote code or silent fallback."""
import hashlib
import json
from pathlib import Path

MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


def encode(items,model_path,revision,cache):
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    texts=[x.get('title','')+'\n'+x.get('summary','') for x in items]
    digest=hashlib.sha256(json.dumps([revision,texts],ensure_ascii=False).encode()).hexdigest()
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    path=cache/(digest+'.npy')
    if path.exists():
        vectors=np.load(path,allow_pickle=False)
        if vectors.shape==(len(items),384) and np.isfinite(vectors).all():return vectors,True
        raise ValueError('Invalid cached embeddings')
    model=SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False,
                              model_kwargs={'use_safetensors':True})
    vectors=model.encode(texts,batch_size=16,normalize_embeddings=True,show_progress_bar=True,convert_to_numpy=True)
    if vectors.shape!=(len(items),384) or not np.isfinite(vectors).all():raise ValueError('Invalid model output')
    np.save(path,vectors,allow_pickle=False)
    return vectors,False
