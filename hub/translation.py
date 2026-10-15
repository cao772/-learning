"""Opt-in, bounded translation of existing title/summary snippets only.

No source fetching or background model calls. Fixed DeepL endpoint, and a
secret only in the server environment, never in browser or GitHub.
"""
import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


MAX_TITLE=500
MAX_SUMMARY=3000


class TranslationError(Exception):
    pass


def original_parts(item):
    title=item.get("title")
    summary=item.get("summary") or ""
    if not isinstance(title,str) or not isinstance(summary,str):
        raise ValueError("invalid source fields")
    if not title.strip() or len(title)>MAX_TITLE or len(summary)>MAX_SUMMARY:
        raise ValueError("source snippet too long")
    return title,summary


def source_fingerprint(title,summary):
    return hashlib.sha256(
        json.dumps([title,summary],ensure_ascii=False,separators=(",",":")).encode()
    ).hexdigest()


def translate_deepl(title,summary,secret,plan="free",opener=urlopen):
    """Translate only already stored text, never fetch the linked full article."""
    if not secret:
        raise TranslationError("翻译服务尚未配置")
    title,summary=original_parts({"title":title,"summary":summary})
    if plan not in ("free","pro"):
        raise TranslationError("翻译服务配置无效")
    endpoint="https://api-free.deepl.com/v2/translate" if plan=="free" else "https://api.deepl.com/v2/translate"
    lines=[title]+([summary] if summary.strip() else [])
    payload=urlencode([("text",v) for v in lines]+[("target_lang","ZH")]).encode("utf-8")
    request=Request(endpoint,data=payload,headers={
        "Authorization":"DeepL-Auth-Key "+secret,
        "Content-Type":"application/x-www-form-urlencoded",
        "User-Agent":"xunxu-learning/translation"
    },method="POST")
    try:
        with opener(request,timeout=12) as response:
            data=json.loads(response.read(16000))
        outputs=data.get("translations")
        if (not isinstance(outputs,list) or len(outputs)!=len(lines)
                or any(not isinstance(o,dict) or not isinstance(o.get("text"),str)
                       or not o["text"].strip() for o in outputs)):
            raise TranslationError("翻译服务返回格式不完整")
        return outputs[0]["text"],outputs[1]["text"] if len(outputs)==2 else ""
    except HTTPError as ex:
        if ex.code==456:
            raise TranslationError("翻译额度已用完，请检查配额") from None
        if ex.code in (401,403):
            raise TranslationError("翻译凭据或套餐配置有误") from None
        raise TranslationError("翻译服务暂时不可用") from None
    except (URLError, TimeoutError, ValueError, UnicodeError, OSError, json.JSONDecodeError):
        raise TranslationError("翻译服务连接或返回异常") from None
