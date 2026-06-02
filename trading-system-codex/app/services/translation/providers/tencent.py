from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.core.config import settings


class TencentTmtTranslationProvider:
    provider_key = "tencent_tmt"
    service = "tmt"
    action = "TextTranslate"
    version = "2018-03-21"

    async def translate_many(
        self,
        texts: list[str],
        *,
        source_language: str,
        target_language: str,
        client: httpx.AsyncClient,
    ) -> list[str]:
        if not settings.tencent_tmt_secret_id or not settings.tencent_tmt_secret_key:
            raise RuntimeError("tencent_tmt_auth_missing")
        translated: list[str] = []
        for text in texts:
            translated.append(
                await self._translate_one(
                    text,
                    source_language=source_language,
                    target_language=target_language,
                    client=client,
                )
            )
        return translated

    async def _translate_one(
        self,
        text: str,
        *,
        source_language: str,
        target_language: str,
        client: httpx.AsyncClient,
    ) -> str:
        payload = {
            "SourceText": text,
            "Source": self._language_code(source_language),
            "Target": self._language_code(target_language),
            "ProjectId": settings.tencent_tmt_project_id,
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        endpoint = settings.tencent_tmt_endpoint
        headers = self._signed_headers(body)
        response = await client.post(endpoint, content=body.encode("utf-8"), headers=headers)
        response.raise_for_status()
        data = response.json()
        result = data.get("Response", {})
        if "Error" in result:
            code = str(result["Error"].get("Code") or "tencent_tmt_error")
            raise RuntimeError(code)
        translated = str(result.get("TargetText") or "").strip()
        return translated or text

    def _signed_headers(self, body: str) -> dict[str, str]:
        endpoint = settings.tencent_tmt_endpoint
        parsed = urlparse(endpoint)
        host = parsed.netloc or "tmt.tencentcloudapi.com"
        timestamp = int(datetime.now(tz=UTC).timestamp())
        date = datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d")
        content_type = "application/json; charset=utf-8"
        hashed_payload = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical_headers = f"content-type:{content_type}\nhost:{host}\n"
        signed_headers = "content-type;host"
        canonical_request = "\n".join(
            [
                "POST",
                "/",
                "",
                canonical_headers,
                signed_headers,
                hashed_payload,
            ]
        )
        credential_scope = f"{date}/{self.service}/tc3_request"
        string_to_sign = "\n".join(
            [
                "TC3-HMAC-SHA256",
                str(timestamp),
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        secret_date = self._hmac_sha256(
            ("TC3" + settings.tencent_tmt_secret_key).encode("utf-8"), date
        )
        secret_service = self._hmac_sha256(secret_date, self.service)
        secret_signing = self._hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        authorization = (
            "TC3-HMAC-SHA256 "
            f"Credential={settings.tencent_tmt_secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": host,
            "X-TC-Action": self.action,
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": settings.tencent_tmt_region,
        }

    @staticmethod
    def _hmac_sha256(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    @staticmethod
    def _language_code(language: str) -> str:
        key = (language or "").lower()
        if key in {"zh", "zh-cn", "zh_cn", "chinese"}:
            return "zh"
        if key in {"en", "en-us", "en_us", "english"}:
            return "en"
        return key or "auto"
